"""处理厂主数据。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from models import PlantIn

router = APIRouter(tags=["plants"])

PLANT_STATUSES = ("运行", "检修", "停用")


def plant_payload(row, outfall_count: int | None = None) -> dict:
    """厂态同源出口：处理厂页、总览页、采样页共用同一 is_maintenance 口径。"""
    d = dict(row)
    d["is_maintenance"] = d["status"] == "检修"
    d["sampling_blocked"] = d["status"] != "运行"
    if outfall_count is not None:
        d["outfall_count"] = outfall_count
    return d


@router.get("/api/plants")
def list_plants(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute("SELECT * FROM plants ORDER BY id").fetchall()
        items = []
        for r in rows:
            out_n = conn.execute(
                "SELECT COUNT(*) c FROM outfalls WHERE plant_id=?", (r["id"],)
            ).fetchone()["c"]
            items.append(plant_payload(r, out_n))
        return {"items": items}


@router.get("/api/plants/{plant_id}")
def get_plant(plant_id: int, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        row = conn.execute("SELECT * FROM plants WHERE id=?", (plant_id,)).fetchone()
        if not row:
            raise HTTPException(404, "处理厂不存在")
        outfalls = conn.execute(
            "SELECT * FROM outfalls WHERE plant_id=? ORDER BY id", (plant_id,)
        ).fetchall()
        permits = conn.execute(
            "SELECT * FROM discharge_permits WHERE plant_id=? ORDER BY id", (plant_id,)
        ).fetchall()
        return {
            "plant": plant_payload(row),
            "outfalls": [dict(o) for o in outfalls],
            "permits": [dict(p) for p in permits],
        }


@router.post("/api/plants")
def create_plant(body: PlantIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    if body.status not in PLANT_STATUSES:
        raise HTTPException(400, "非法状态")
    with connect() as conn:
        if conn.execute(
            "SELECT id FROM plants WHERE plant_code=?", (body.plant_code,)
        ).fetchone():
            raise HTTPException(400, "处理厂编码已存在")
        cur = conn.execute(
            """INSERT INTO plants(plant_code,name,basin,design_cap_m3d,status,
               maintenance_since,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                body.plant_code,
                body.name,
                body.basin,
                body.design_cap_m3d,
                body.status,
                now_iso() if body.status == "检修" else None,
                now_iso(),
            ),
        )
        pid = cur.lastrowid
        write_audit(conn, user, "plant_create", body.plant_code, body.model_dump())
        conn.commit()
        return {"id": pid, **body.model_dump()}


@router.get("/api/maintenance/decisions")
def list_maintenance_decisions(authorization: AuthHeader = None):
    """检修禁采拍板说明（处理厂页、总览页同源展示）。"""
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM maintenance_decisions ORDER BY id DESC"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/plants/{plant_id}/status")
def set_plant_status(plant_id: int, status: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    if status not in PLANT_STATUSES:
        raise HTTPException(400, "非法状态")
    with connect() as conn:
        row = conn.execute("SELECT * FROM plants WHERE id=?", (plant_id,)).fetchone()
        if not row:
            raise HTTPException(404, "处理厂不存在")
        since = row["maintenance_since"]
        if status == "检修" and row["status"] != "检修":
            since = now_iso()
        elif status != "检修":
            since = None
        conn.execute(
            "UPDATE plants SET status=?, maintenance_since=? WHERE id=?",
            (status, since, plant_id),
        )
        if status != "运行":
            from db import record_maintenance_decision

            record_maintenance_decision(
                conn,
                plant_id,
                row["plant_code"],
                f"厂态转{status}：采样写口当日封死，正式排放册零增，"
                "既有待检草稿一律拒收封存",
                f"由 {user} 于 {now_iso()} 拍板；恢复运行前禁止正式采样写口。",
                plant_status=status,
            )
        write_audit(
            conn,
            user,
            "plant_status",
            row["plant_code"],
            {
                "from": row["status"],
                "to": status,
                "decision": "检修禁采当日封死" if status != "运行" else "恢复采样",
            },
        )
        conn.commit()
        return {"id": plant_id, "status": status, "is_maintenance": status == "检修"}
