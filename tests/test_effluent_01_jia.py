"""排污甲第1槽 · 失败测甲：检修厂采样写口。

口径（甲路径）：厂态非运行 ⇒ 采样写口当场拒写、正式排放册零增，
并当场落「检修禁采偏航」痕；预置夹具不得把检修厂批次写进正式册。
本测先盯「检修厂仍写出正式采样行」。
"""
import pytest
from fastapi.testclient import TestClient

from app import app
from db import connect, init_db

MAINT_PLANT = "PL-EAST-01"
MAINT_OUTFALL = "OF-E1-A"
PERMIT = "DP-2026-E01"


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "jia.db")
    init_db()
    yield


def _auth(c: TestClient, user="admin", password="admin123") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": password}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _formal_count(plant_code: str) -> int:
    with connect() as conn:
        return conn.execute(
            """SELECT COUNT(*) c FROM sample_batches s
               JOIN outfalls o ON o.id=s.outfall_id
               JOIN plants p ON p.id=o.plant_id
               WHERE p.plant_code=?""",
            (plant_code,),
        ).fetchone()["c"]


def test_maintenance_plant_has_no_formal_sample_row():
    """预置夹具 SM-A01 挂在检修厂，只能落拒收封存，正式册不得有行。"""
    c = TestClient(app)
    h = _auth(c)

    plants = c.get("/api/plants", headers=h).json()["items"]
    east = next(p for p in plants if p["plant_code"] == MAINT_PLANT)
    assert east["status"] == "检修"
    assert east["is_maintenance"] is True

    items = c.get("/api/samples", headers=h).json()["items"]
    codes = [s["sample_code"] for s in items]
    assert "SM-A01" not in codes, "检修厂预置批次仍进正式排放册"
    # 检修前历史合法批次可留册；检修期误采（SM-A01）必须零行。
    assert _formal_count(MAINT_PLANT) == 3, "检修期误采批次混入正式册"

    with connect() as conn:
        sealed = conn.execute(
            "SELECT * FROM sample_drafts WHERE sample_code='SM-A01'"
        ).fetchone()
    assert sealed is not None, "预置批次未转拒收封存"
    assert sealed["status"] == "拒收封存"


def test_maintenance_plant_write_refused_and_register_unchanged():
    """检修厂写口当场拒写，正式册零增，留「检修禁采偏航」痕。"""
    c = TestClient(app)
    h = _auth(c)
    outfalls = c.get("/api/outfalls", headers=h).json()["items"]
    of = next(o for o in outfalls if o["outfall_code"] == MAINT_OUTFALL)
    before = _formal_count(MAINT_PLANT)

    r = c.post(
        "/api/samples",
        headers=h,
        json={
            "outfall_id": of["id"],
            "permit_ref": PERMIT,
            "sample_code": "SM-A01-B",
            "flow_m3h": 900,
            "metrics": {"cod": 33, "nh3n": 2.6, "tp": 0.21},
        },
    )
    assert r.status_code in (400, 403, 409), r.text
    assert _formal_count(MAINT_PLANT) == before, "检修厂采样仍写进正式册"

    with connect() as conn:
        sealed = conn.execute(
            "SELECT * FROM sample_drafts WHERE sample_code='SM-A01-B'"
        ).fetchone()
    assert sealed is not None and sealed["status"] == "拒收封存", "拒收未当日封死"

    audit = c.get("/api/audit", headers=h).json()["items"]
    assert any(a["action"] == "检修禁采偏航" for a in audit), "拒写未留偏航痕"
