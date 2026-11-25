"""排放口限值与开放态。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from models import OutfallIn

router = APIRouter(tags=["outfalls"])


def _today() -> str:
    return now_iso()[:10]


@router.get("/api/outfalls")
def list_outfalls(authorization: AuthHeader = None, plant_id: int | None = None):
    require_user(authorization)
    with connect() as conn:
        base = """SELECT o.*, p.plant_code, p.name plant_name, p.status plant_status
                  FROM outfalls o JOIN plants p ON p.id=o.plant_id"""
        if plant_id:
            rows = conn.execute(
                base + " WHERE o.plant_id=? ORDER BY o.id", (plant_id,)
            ).fetchall()
        else:
            rows = conn.execute(base + " ORDER BY o.id").fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["is_maintenance"] = d["plant_status"] == "检修"
            items.append(d)
        return {"items": items}


@router.get("/api/outfalls/{outfall_id}")
def get_outfall(outfall_id: int, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        row = conn.execute(
            """SELECT o.*, p.plant_code, p.design_cap_m3d, p.status plant_status
               FROM outfalls o
               JOIN plants p ON p.id=o.plant_id WHERE o.id=?""",
            (outfall_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "排放口不存在")
        is_maintenance = row["plant_status"] == "检修"
        recent = conn.execute(
            """SELECT sample_code, status, flow_m3h, creation_day FROM (
                   SELECT sample_code, status, flow_m3h,
                          substr(created_at,1,10) creation_day
                   FROM sample_batches WHERE outfall_id=? ORDER BY id DESC
               ) WHERE creation_day=? ORDER BY sample_code""",
            (outfall_id, _today()),
        ).fetchall()
        excluded = conn.execute(
            """SELECT COUNT(*) c FROM sample_drafts d
               JOIN outfalls o ON o.id=d.outfall_id
               WHERE o.id=? AND d.status='拒收封存'""",
            (outfall_id,),
        ).fetchone()["c"]
        # 检修厂当日曲线一律剔除（草稿不入曲线），同源账实。
        curve = []
        if not is_maintenance:
            curve = [
                {
                    "sample_code": s["sample_code"],
                    "flow_m3h": s["flow_m3h"],
                    "status": s["status"],
                }
                for s in recent
            ]
        outfall_payload = dict(row)
        outfall_payload["is_maintenance"] = is_maintenance
        return {
            "outfall": outfall_payload,
            "recent_samples": [] if is_maintenance else [dict(s) for s in recent],
            "daily_curve": curve,
            "maintenance_excluded": excluded,
        }


@router.post("/api/outfalls")
def create_outfall(body: OutfallIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        plant = conn.execute(
            "SELECT * FROM plants WHERE id=?", (body.plant_id,)
        ).fetchone()
        if not plant:
            raise HTTPException(404, "处理厂不存在")
        if conn.execute(
            "SELECT id FROM outfalls WHERE outfall_code=?", (body.outfall_code,)
        ).fetchone():
            raise HTTPException(400, "排放口编码已存在")
        cur = conn.execute(
            """INSERT INTO outfalls(outfall_code,plant_id,river_reach,cod_limit,nh3n_limit,
               tp_limit,status,created_at) VALUES (?,?,?,?,?,?,?,?)""",
            (
                body.outfall_code,
                body.plant_id,
                body.river_reach,
                body.cod_limit,
                body.nh3n_limit,
                body.tp_limit,
                body.status,
                now_iso(),
            ),
        )
        oid = cur.lastrowid
        write_audit(conn, user, "outfall_create", body.outfall_code, body.model_dump())
        conn.commit()
        return {"id": oid, **body.model_dump()}


@router.post("/api/outfalls/{outfall_id}/status")
def set_outfall_status(outfall_id: int, status: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    if status not in ("开放", "停用", "检修"):
        raise HTTPException(400, "非法状态")
    with connect() as conn:
        row = conn.execute("SELECT * FROM outfalls WHERE id=?", (outfall_id,)).fetchone()
        if not row:
            raise HTTPException(404, "排放口不存在")
        conn.execute("UPDATE outfalls SET status=? WHERE id=?", (status, outfall_id))
        write_audit(
            conn, user, "outfall_status", row["outfall_code"], {"status": status}
        )
        conn.commit()
        return {"id": outfall_id, "status": status}
