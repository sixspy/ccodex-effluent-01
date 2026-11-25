"""排放批争用锁。"""
from __future__ import annotations

import sqlite3
import time

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit

router = APIRouter(tags=["locks"])

# 持锁复现窗口：生产默认 0；并发验收夹具注入以稳定复现同厂争用。
LOCK_HOLD_SECONDS = 0.0


def claim(conn, lock_key: str, holder: str) -> tuple[bool, str | None]:
    """原子抢锁：以 lock_key 主键唯一性判定成败，败方返回现有持有人。

    读-改-写竞态由 SQLite 主键约束消解，避免两路会话同厂双成。
    """
    try:
        conn.execute(
            "INSERT INTO effluent_locks(lock_key,holder,acquired_at) VALUES (?,?,?)",
            (lock_key, holder, now_iso()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        row = conn.execute(
            "SELECT holder FROM effluent_locks WHERE lock_key=?", (lock_key,)
        ).fetchone()
        if row and row["holder"] == holder:
            return True, None
        return False, (row["holder"] if row else None)
    if LOCK_HOLD_SECONDS:
        time.sleep(LOCK_HOLD_SECONDS)
    return True, None


def require_lock(conn, lock_key: str, holder: str) -> None:
    ok, current = claim(conn, lock_key, holder)
    if not ok:
        conn.execute(
            """INSERT INTO contention_log(lock_key,actor,action,detail,created_at)
               VALUES (?,?,?,?,?)""",
            (lock_key, holder, "争用失败", f"持有人={current}", now_iso()),
        )
        raise HTTPException(409, f"锁被占用：{lock_key} 持有人 {current}")


def release(conn, lock_key: str, holder: str) -> None:
    conn.execute(
        "DELETE FROM effluent_locks WHERE lock_key=? AND holder=?",
        (lock_key, holder),
    )


@router.get("/api/locks")
def list_locks(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        locks = [dict(r) for r in conn.execute("SELECT * FROM effluent_locks").fetchall()]
        logs = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM contention_log ORDER BY id DESC LIMIT 50"
            ).fetchall()
        ]
        return {"locks": locks, "contention": logs}


@router.post("/api/locks/acquire")
def acquire(lock_key: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        require_lock(conn, lock_key, user)
        write_audit(conn, user, "lock_acquire", lock_key, {})
        conn.commit()
        return {"ok": True, "lock_key": lock_key, "holder": user}


@router.post("/api/locks/release")
def release_api(lock_key: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        release(conn, lock_key, user)
        write_audit(conn, user, "lock_release", lock_key, {})
        conn.commit()
        return {"ok": True}
