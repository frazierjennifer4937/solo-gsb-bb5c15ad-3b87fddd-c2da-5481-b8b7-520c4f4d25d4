"""SQLite 持久化：建表初始化与方案存取。

数据库路径由环境变量 DB_PATH 指定，默认 ./data/plans.db。
应用启动时调用 init_db() 完成初始化（幂等）。
"""

from __future__ import annotations

import json
import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.getcwd(), "data", "plans.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    plan_id        TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    status         TEXT NOT NULL,
    sheets_used    INTEGER NOT NULL,
    placed_parts   INTEGER NOT NULL,
    unplaced_parts INTEGER NOT NULL,
    utilization    REAL NOT NULL,
    request_json   TEXT NOT NULL,
    result_json    TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """初始化数据库（建表，幂等）。"""
    with _connect() as con:
        con.executescript(_SCHEMA)


def insert_plan(plan: dict) -> None:
    summary = plan["summary"]
    with _connect() as con:
        con.execute(
            """
            INSERT INTO plans (
                plan_id, created_at, status, sheets_used,
                placed_parts, unplaced_parts, utilization,
                request_json, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan["plan_id"],
                plan["created_at"],
                plan["status"],
                summary["sheets_used"],
                summary["placed_parts"],
                summary["unplaced_parts"],
                summary["utilization"],
                json.dumps(plan["input"], ensure_ascii=False),
                json.dumps(plan, ensure_ascii=False),
            ),
        )


def get_plan(plan_id: str) -> dict | None:
    with _connect() as con:
        row = con.execute(
            "SELECT result_json FROM plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["result_json"])


def list_plans(limit: int, offset: int) -> tuple[int, list[dict]]:
    with _connect() as con:
        total = con.execute("SELECT COUNT(*) AS n FROM plans").fetchone()["n"]
        rows = con.execute(
            """
            SELECT plan_id, created_at, status, sheets_used,
                   placed_parts, unplaced_parts, utilization
            FROM plans
            ORDER BY rowid DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return total, [dict(r) for r in rows]
