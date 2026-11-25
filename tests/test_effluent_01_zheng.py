"""排污甲第1槽 · 失败测丙（争用）：同厂两路会话并发建采样须占厂锁。

口径：两路会话同厂同时抢建采样须占厂锁（plant:{plant_id}），
败方只记争用痕、不落采样行；争用核销与命运取舍分两段写。
并发脚本走本机种子夹具，触发点 ping_plant_sample_lock。
"""
import threading

import pytest
from fastapi.testclient import TestClient

from app import app
from db import connect, init_db

# 选运行中的西湾厂，专测锁而非厂态；两路走不同排放口，旧实现只按口加锁。
PLANT_CODE = "PL-WEST-02"
OUTFALL_A = "OF-W2-A"
OUTFALL_B = "OF-W2-B"
PERMIT = "DP-2026-W02"


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "zheng.db")
    # 夹具走本机种子 + 复现窗口：持锁 0.4s，令两路请求必然重叠。
    monkeypatch.setattr("locks.LOCK_HOLD_SECONDS", 0.4)
    init_db()
    yield


def _auth(c: TestClient, user="admin", password="admin123") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": password}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _outfall_id(c: TestClient, h: dict, code: str) -> int:
    outfalls = c.get("/api/outfalls", headers=h).json()["items"]
    return next(o for o in outfalls if o["outfall_code"] == code)["id"]


def ping_plant_sample_lock(sessions, outfall_ids, results, barrier):
    """并发脚本：两路同厂会话同刻抢建采样，验证厂锁。"""
    def _fire(tag, client, headers, outfall_id):
        barrier.wait()
        try:
            r = client.post(
                "/api/samples",
                headers=headers,
                json={
                    "outfall_id": outfall_id,
                    "permit_ref": PERMIT,
                    "flow_m3h": 900,
                    "metrics": {"cod": 33, "nh3n": 2.6, "tp": 0.21},
                },
            )
            results.append((tag, r.status_code, r.json()))
        except Exception as exc:  # noqa: BLE001 - 线程内异常回传
            results.append((tag, "error", str(exc)))

    threads = [
        threading.Thread(target=_fire, args=(tag, c, h, oid))
        for (tag, c, h), oid in zip(sessions, outfall_ids)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_same_plant_concurrent_sample_single_lock():
    """同厂两路并发建批必须一成一败，败方只留争用痕。

    两路走同一 admin 账号的两个独立会话，验证锁不把同账号当重入。
    """
    c1 = TestClient(app)
    c2 = TestClient(app)
    h1 = _auth(c1, "admin", "admin123")
    h2 = _auth(c2, "admin", "admin123")
    of_a = _outfall_id(c1, h1, OUTFALL_A)
    of_b = _outfall_id(c2, h2, OUTFALL_B)

    with connect() as conn:
        before = conn.execute("SELECT COUNT(*) c FROM sample_batches").fetchone()["c"]
        plant_id = conn.execute(
            "SELECT id FROM plants WHERE plant_code=?", (PLANT_CODE,)
        ).fetchone()["id"]

    results = []
    barrier = threading.Barrier(2)
    ping_plant_sample_lock(
        [("A", c1, h1), ("B", c2, h2)], [of_a, of_b], results, barrier
    )

    codes = [r[1] for r in results]
    assert codes.count(200) == 1, f"同厂抢建无锁双成或双败：{results}"
    assert any(code == 409 for code in codes), f"败方未按争用拒写：{results}"

    with connect() as conn:
        after = conn.execute("SELECT COUNT(*) c FROM sample_batches").fetchone()["c"]
        logs = conn.execute(
            "SELECT * FROM contention_log WHERE lock_key=?", (f"plant:{plant_id}",)
        ).fetchall()
        audits = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM audit_trail WHERE action IN ('争用核销','命运取舍')"
            ).fetchall()
        ]
    assert after == before + 1, f"败方仍落采样行：{before}->{after}"
    assert len(logs) == 1, f"厂锁争用痕不符：{logs}"
    assert {a["action"] for a in audits} == {"争用核销", "命运取舍"}, "核销/取舍未分两段写"
