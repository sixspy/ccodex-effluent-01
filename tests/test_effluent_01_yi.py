"""排污甲第1槽 · 失败测乙：对账流量不得吞进检修厂批次。

口径（甲）：检修厂采样写口拒写、正式册零增；
对账流量卡只统计正式册在册批次，检修厂草稿（作废待检）不得计入。
"""
import pytest
from fastapi.testclient import TestClient

from app import app
from db import connect, init_db

MAINT_PLANT = "PL-EAST-01"


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "yi.db")
    init_db()
    yield


def _auth(c: TestClient, user="admin", password="admin123") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": password}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def test_reconcile_flow_excludes_maintenance_batches():
    """对账流量卡不得计入检修期采样（当前假绿：SM-A01 的 1234 m3/h 被吞进）。"""
    c = TestClient(app)
    h = _auth(c)
    recon = c.get("/api/reconcile/DP-2026-E01", headers=h).json()
    codes = [s["sample_code"] for s in recon.get("samples", [])]
    assert "SM-A01" not in codes, "对账流量仍计入检修期批次"
    # 检修前历史合法批次（2800+2900+1200）仍应在账，仅剔除检修期 1234。
    assert float(recon.get("flow_m3h_total", -1)) == 6900.0
    assert float(recon.get("flow_m3d_total", -1)) == 6900.0 * 24
    assert recon.get("maintenance_excluded", 0) >= 1, "检修批次未在对账侧显式剔除"
    # 对账齐否另由在册批次超标判定（SM-OF-E1-A-002 本就超 COD），与本闸无关；
    # 此处只核流量卡剔除检修批、账实同源。


def test_maintenance_write_never_touches_formal_or_reconcile():
    """检修厂再写采样：当场拒写、正式册零增、对账流量零增。"""
    c = TestClient(app)
    h = _auth(c)
    outfalls = c.get("/api/outfalls", headers=h).json()["items"]
    of = next(o for o in outfalls if o["outfall_code"] == "OF-E1-A")

    with connect() as conn:
        before = conn.execute("SELECT COUNT(*) c FROM sample_batches").fetchone()["c"]

    r = c.post(
        "/api/samples",
        headers=h,
        json={
            "outfall_id": of["id"],
            "permit_ref": "DP-2026-E01",
            "sample_code": "SM-YI-REFUSE-01",
            "flow_m3h": 900,
            "metrics": {"cod": 33, "nh3n": 2.6, "tp": 0.21},
        },
    )
    assert r.status_code in (400, 403, 409), r.text

    with connect() as conn:
        after = conn.execute("SELECT COUNT(*) c FROM sample_batches").fetchone()["c"]
    assert after == before, "检修厂写入仍污染正式册"

    recon = c.get("/api/reconcile/DP-2026-E01", headers=h).json()
    assert float(recon.get("flow_m3h_total", -1)) == 6900.0
    assert float(recon.get("flow_m3d_total", -1)) == 6900.0 * 24
    assert recon.get("maintenance_excluded", 0) >= 2, "新拒收草稿未计入剔除数"


def test_outfall_daily_curve_excludes_maintenance_batches():
    """排放口页当日曲线剔除检修厂批次（同源账实）。"""
    c = TestClient(app)
    h = _auth(c)
    outfalls = c.get("/api/outfalls", headers=h).json()["items"]
    of = next(o for o in outfalls if o["outfall_code"] == "OF-E1-A")
    detail = c.get(f"/api/outfalls/{of['id']}", headers=h).json()
    assert detail["outfall"]["is_maintenance"] is True
    assert detail["recent_samples"] == []
    assert all(p["flow_m3h"] == 0 for p in detail["daily_curve"])
    assert detail["maintenance_excluded"] >= 1
