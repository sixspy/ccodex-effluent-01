"""排放许可与采样对账证明。"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from validators import validate_permit_match

router = APIRouter(tags=["reconcile"])


@router.get("/api/reconcile")
def reconcile_all(authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        rows = conn.execute(
            "SELECT permit_code FROM discharge_permits ORDER BY permit_code"
        ).fetchall()
        return {"items": [_reconcile_permit(conn, r["permit_code"]) for r in rows]}


@router.get("/api/reconcile/{permit_code}")
def reconcile_one(permit_code: str, authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        if not conn.execute(
            "SELECT id FROM discharge_permits WHERE permit_code=?", (permit_code,)
        ).fetchone():
            raise HTTPException(404, "许可不存在")
        return _reconcile_permit(conn, permit_code)


def _reconcile_permit(conn, permit_code: str) -> dict:
    permit = conn.execute(
        "SELECT * FROM discharge_permits WHERE permit_code=?", (permit_code,)
    ).fetchone()
    # 同源账实：流量卡只统计正式在册且非检修期批次；
    # 检修期采样（当日及之后）即便残留册中也不得计入流量，另列 maintenance_excluded。
    rows = conn.execute(
        """SELECT s.sample_code, s.flow_m3h, s.metrics, s.status, s.generation,
                  s.created_at, p.plant_code, p.status plant_status,
                  p.maintenance_since
           FROM sample_batches s
           JOIN outfalls o ON o.id=s.outfall_id
           JOIN plants p ON p.id=o.plant_id
           WHERE s.permit_ref=? AND s.status NOT IN ('作废')""",
        (permit_code,),
    ).fetchall()
    samples = []
    maintenance_excluded = 0
    for r in rows:
        in_maint_window = (
            r["plant_status"] == "检修"
            and r["maintenance_since"]
            and str(r["created_at"])[:10] >= str(r["maintenance_since"])[:10]
        )
        if in_maint_window:
            maintenance_excluded += 1
            continue
        samples.append(r)
    draft_rows = conn.execute(
        """SELECT d.sample_code, d.status FROM sample_drafts d
           WHERE d.permit_ref=?""",
        (permit_code,),
    ).fetchall()
    maintenance_excluded += len(
        [d for d in draft_rows if d["status"] == "拒收封存"]
    )
    flow_m3h_total = round(sum(float(s["flow_m3h"]) for s in samples), 3)
    flow_m3d_total = round(flow_m3h_total * 24.0, 3)
    if not samples:
        return {
            "permit_code": permit_code,
            "balanced": True,
            "reason": "无正式在册采样批次",
            "quota_m3d": permit["quota_m3d"],
            "flow_m3h_total": 0.0,
            "flow_m3d_total": 0.0,
            "maintenance_excluded": maintenance_excluded,
            "samples": [],
            "seals": [],
            "seal_count": 0,
            "proof_ready": False,
        }
    caps = {
        "cod": permit["cod_cap"],
        "nh3n": permit["nh3n_cap"],
        "tp": permit["tp_cap"],
    }
    details = []
    all_ok = True
    for s in samples:
        metrics = json.loads(s["metrics"] or "{}")
        ok = validate_permit_match(
            caps, metrics, float(s["flow_m3h"]), float(permit["quota_m3d"])
        )
        if not ok:
            all_ok = False
        details.append(
            {
                "sample_code": s["sample_code"],
                "status": s["status"],
                "generation": s["generation"],
                "plant_code": s["plant_code"],
                "metrics": metrics,
                "flow_m3h": s["flow_m3h"],
                "matched": ok,
            }
        )
    seal_rows = conn.execute(
        """SELECT d.seal_ref, d.sample_generation, s.sample_code
           FROM discharge_seals d JOIN sample_batches s ON s.id=d.sample_id
           WHERE s.permit_ref=?""",
        (permit_code,),
    ).fetchall()
    return {
        "permit_code": permit_code,
        "quota_m3d": permit["quota_m3d"],
        "caps": caps,
        "balanced": all_ok,
        "proof_ready": all_ok and len(seal_rows) >= 1,
        "seal_count": len(seal_rows),
        "flow_m3h_total": flow_m3h_total,
        "flow_m3d_total": flow_m3d_total,
        "maintenance_excluded": maintenance_excluded,
        "samples": details,
        "seals": [dict(x) for x in seal_rows],
    }


@router.get("/api/proof/sample/{sample_code}")
def proof_sample(sample_code: str, authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        sample = conn.execute(
            "SELECT * FROM sample_batches WHERE sample_code=?", (sample_code,)
        ).fetchone()
        if not sample:
            raise HTTPException(404, "采样不存在")
        holds = conn.execute(
            "SELECT * FROM exceed_holds WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        releases = conn.execute(
            "SELECT * FROM discharge_releases WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        seals = conn.execute(
            "SELECT * FROM discharge_seals WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        open_holds = [h for h in holds if h["status"] == "开放"]
        closed = [h for h in holds if h["status"] == "已关闭"]
        return {
            "sample_code": sample_code,
            "status": sample["status"],
            "generation": sample["generation"],
            "released": any(r["status"] == "已准排" for r in releases),
            "sealed": any(s["status"] == "已封批" for s in seals),
            "exceed_closed": len(open_holds) == 0 and (len(closed) > 0 or sample["status"] != "旁路挂起"),
            "holds": [dict(h) for h in holds],
            "releases": [dict(r) for r in releases],
            "seals": [dict(s) for s in seals],
        }
