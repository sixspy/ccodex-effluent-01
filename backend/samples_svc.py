"""采样批次入库与超标裁定。"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from locks import claim, release, require_lock
from models import SampleIn
from validators import (
    adjudicate_exceed,
    metric_summary,
    validate_flow_cap,
    validate_metrics_nonneg,
    validate_outfall_open,
)

router = APIRouter(tags=["samples"])

# 检修禁采口径：厂态非「运行」即禁采；检修厂新建采样当场拒写并封存草稿。
MAINTENANCE_DRAFT_STATUS = "拒收封存"


def _next_sample_code(conn, outfall_id: int) -> str:
    outfall = conn.execute(
        "SELECT outfall_code FROM outfalls WHERE id=?", (outfall_id,)
    ).fetchone()
    prefix = outfall["outfall_code"] if outfall else f"OF-{outfall_id}"
    n = conn.execute(
        "SELECT COUNT(*) c FROM sample_batches WHERE outfall_id=?", (outfall_id,)
    ).fetchone()["c"]
    return f"SM-{prefix}-{n + 1:03d}"


def _draft_code(conn, code: str | None, outfall_id: int) -> str:
    if code:
        return code
    n = conn.execute(
        "SELECT COUNT(*) c FROM sample_drafts WHERE outfall_id=?", (outfall_id,)
    ).fetchone()["c"]
    return f"DR-{outfall_id}-{n + 1:03d}"


def _refuse_sampling(conn, user: str, outfall: dict, body: SampleIn, code: str) -> None:
    """厂态非运行：正式册零增，写口当场拒写，草稿当日封死并记偏航。"""
    plant_status = outfall["plant_status"]
    metrics = body.metrics.model_dump()
    reason = f"检修禁采：厂态={plant_status}，正式册拒写并封存待检草稿"
    audit_action = "检修禁采偏航" if plant_status == "检修" else "非运行禁采偏航"
    conn.execute(
        """INSERT INTO sample_drafts(sample_code,outfall_id,permit_ref,metrics,flow_m3h,
           status,reason,created_at) VALUES (?,?,?,?,?,?,?,?)""",
        (
            _draft_code(conn, code, body.outfall_id),
            body.outfall_id,
            body.permit_ref,
            json.dumps(metrics, ensure_ascii=False),
            body.flow_m3h,
            MAINTENANCE_DRAFT_STATUS,
            reason,
            now_iso(),
        ),
    )
    write_audit(
        conn,
        user,
        audit_action,
        outfall["outfall_code"],
        {
            "plant_code": outfall["plant_code"],
            "plant_status": plant_status,
            "sample_code": code,
            "decision": reason,
            "formal_rows_added": 0,
        },
    )
    conn.commit()


@router.get("/api/samples")
def list_samples(authorization: AuthHeader = None, status: str | None = None):
    require_user(authorization)
    with connect() as conn:
        q = """SELECT s.*, o.outfall_code, p.plant_code, p.status plant_status
               FROM sample_batches s
               JOIN outfalls o ON o.id=s.outfall_id
               JOIN plants p ON p.id=o.plant_id"""
        if status:
            rows = conn.execute(
                q + " WHERE s.status=? ORDER BY s.id DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute(q + " ORDER BY s.id DESC").fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(d["metrics"] or "{}")
            d["is_maintenance"] = d["plant_status"] == "检修"
            items.append(d)
        return {"items": items}


@router.get("/api/samples/{sample_id}")
def get_sample(sample_id: int, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        row = conn.execute(
            """SELECT s.*, o.outfall_code, o.cod_limit, o.nh3n_limit, o.tp_limit,
                      p.name plant_name, p.status plant_status
               FROM sample_batches s
               JOIN outfalls o ON o.id=s.outfall_id
               JOIN plants p ON p.id=o.plant_id
               WHERE s.id=?""",
            (sample_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "采样批次不存在")
        data = dict(row)
        data["metrics"] = json.loads(data["metrics"] or "{}")
        data["is_maintenance"] = data["plant_status"] == "检修"
        holds = conn.execute(
            "SELECT * FROM exceed_holds WHERE sample_id=? ORDER BY id DESC",
            (sample_id,),
        ).fetchall()
        seals = conn.execute(
            "SELECT * FROM discharge_seals WHERE sample_id=? ORDER BY id DESC",
            (sample_id,),
        ).fetchall()
        releases = conn.execute(
            "SELECT * FROM discharge_releases WHERE sample_id=? ORDER BY id DESC",
            (sample_id,),
        ).fetchall()
        return {
            "sample": data,
            "exceed_holds": [dict(h) for h in holds],
            "discharge_seals": [dict(s) for s in seals],
            "discharge_releases": [dict(r) for r in releases],
        }


@router.post("/api/samples")
def create_sample(body: SampleIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        outfall = conn.execute(
            """SELECT o.*, p.id plant_id, p.plant_code, p.status plant_status,
                      p.design_cap_m3d
               FROM outfalls o JOIN plants p ON p.id=o.plant_id WHERE o.id=?""",
            (body.outfall_id,),
        ).fetchone()
        if not outfall:
            raise HTTPException(404, "排放口不存在")

        # 厂锁持有人按「会话请求」唯一化：同账号两路会话也必须互斥，不可当重入。
        handle = f"{user}#{uuid.uuid4().hex[:12]}"
        lock_key = f"plant:{outfall['plant_id']}"
        ok, current = claim(conn, lock_key, handle)
        if not ok:
            # 争用核销与命运取舍分两段写：败方只留痕，不落采样行。
            conn.execute(
                """INSERT INTO contention_log(lock_key,actor,action,detail,created_at)
                   VALUES (?,?,?,?,?)""",
                (lock_key, user, "争用失败", f"持有人={current}", now_iso()),
            )
            write_audit(
                conn,
                user,
                "争用核销",
                lock_key,
                {"holder": current, "result": "本路未取得厂锁"},
            )
            write_audit(
                conn,
                user,
                "命运取舍",
                lock_key,
                {"decision": "败方只留痕不落采样行", "formal_rows_added": 0},
            )
            conn.commit()
            raise HTTPException(409, f"同厂采样争用：{lock_key} 持有人 {current}")
        try:
            # 厂态闸先于排口闸：检修厂一律当场拒写并留偏航痕，不受排口状态影响。
            if outfall["plant_status"] != "运行":
                code = body.sample_code or _next_sample_code(conn, body.outfall_id)
                _refuse_sampling(conn, user, outfall, body, code)
                raise HTTPException(
                    403,
                    f"检修禁采：{outfall['plant_code']} 厂态={outfall['plant_status']}，"
                    "正式排放册拒写并当场封存",
                )
            validate_outfall_open(outfall["status"])
            metrics = body.metrics.model_dump()
            validate_metrics_nonneg(metrics)
            validate_flow_cap(body.flow_m3h, float(outfall["design_cap_m3d"]))
            permit = conn.execute(
                "SELECT * FROM discharge_permits WHERE permit_code=?",
                (body.permit_ref,),
            ).fetchone()
            if not permit:
                raise HTTPException(400, "排放许可不存在")
            if permit["status"] != "有效":
                raise HTTPException(400, "排放许可未生效")
            exceeded, metric, measured, limit = adjudicate_exceed(
                metrics,
                {
                    "cod": outfall["cod_limit"],
                    "nh3n": outfall["nh3n_limit"],
                    "tp": outfall["tp_limit"],
                },
            )
            code = body.sample_code or _next_sample_code(conn, body.outfall_id)
            if conn.execute(
                "SELECT id FROM sample_batches WHERE sample_code=?", (code,)
            ).fetchone():
                raise HTTPException(400, "采样编号已存在")
            status = "旁路挂起" if exceeded else "已裁定"
            adjudicated = None if exceeded else now_iso()
            cur = conn.execute(
                """INSERT INTO sample_batches(sample_code,outfall_id,permit_ref,metrics,
                   flow_m3h,generation,status,maintenance_conflict,adjudicated_at,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    code,
                    body.outfall_id,
                    body.permit_ref,
                    json.dumps(metrics, ensure_ascii=False),
                    body.flow_m3h,
                    1,
                    status,
                    0,
                    adjudicated,
                    now_iso(),
                ),
            )
            sid = cur.lastrowid
            hold = None
            if exceeded:
                hold_key = f"EX-{code}-{metric}"
                conn.execute(
                    """INSERT INTO exceed_holds(sample_id,hold_key,exceed_metric,measured,
                       limit_value,status,opened_at,note)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        sid,
                        hold_key,
                        metric,
                        measured,
                        limit,
                        "开放",
                        now_iso(),
                        "入库自动挂起",
                    ),
                )
                hold = hold_key
            write_audit(
                conn,
                user,
                "sample_create",
                code,
                {
                    "status": status,
                    "metrics": metrics,
                    "summary": metric_summary(metrics),
                    "exceed": exceeded,
                },
            )
            conn.commit()
            return {
                "id": sid,
                "sample_code": code,
                "status": status,
                "exceed": exceeded,
                "hold_key": hold,
            }
        finally:
            release(conn, lock_key, handle)
            conn.commit()
