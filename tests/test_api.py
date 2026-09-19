"""API 层测试：创建、查询、列表、稳定性、校验。"""

from __future__ import annotations

import os
import tempfile

# 必须在导入 app 之前指定临时数据库
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_plans.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # 作为上下文管理器使用才会执行 lifespan（启动时初始化数据库）
    with TestClient(app) as c:
        yield c

PAYLOAD = {
    "sheet": {"width": 2440, "height": 1220, "kerf": 3, "max_sheets": 5},
    "parts": [
        {"id": "door", "width": 800, "height": 400, "quantity": 4, "rotatable": True},
        {"id": "shelf", "width": 600, "height": 300, "quantity": 6, "rotatable": False},
    ],
}


def test_create_and_get_plan(client):
    r = client.post("/api/v1/plans", json=PAYLOAD)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "complete"
    assert body["summary"]["total_parts"] == 10
    assert body["summary"]["placed_parts"] == 10
    assert body["summary"]["unplaced_parts"] == 0
    assert body["unplaced"] == []
    assert len(body["sheets"]) >= 1

    sheet = body["sheets"][0]
    assert sheet["placements"]
    for c in sheet["cuts"]:
        assert c["seq"] >= 1
        assert c["orientation"] in ("H", "V")
        assert c["length"] > 0
    seqs = [c["seq"] for c in sheet["cuts"]]
    assert seqs == list(range(1, len(seqs) + 1)), "切割线必须按顺序编号"

    plan_id = body["plan_id"]
    r2 = client.get(f"/api/v1/plans/{plan_id}")
    assert r2.status_code == 200
    assert r2.json() == body


def test_same_input_stable_layout(client):
    r1 = client.post("/api/v1/plans", json=PAYLOAD).json()
    r2 = client.post("/api/v1/plans", json=PAYLOAD).json()
    assert r1["sheets"] == r2["sheets"]
    assert r1["unplaced"] == r2["unplaced"]
    assert r1["summary"] == r2["summary"]


def test_unplaced_listed(client):
    payload = {
        "sheet": {"width": 1000, "height": 1000, "kerf": 3, "max_sheets": 1},
        "parts": [
            {"id": "big", "width": 900, "height": 900, "quantity": 2},
            {"id": "huge", "width": 3000, "height": 100, "quantity": 1, "rotatable": True},
        ],
    }
    r = client.post("/api/v1/plans", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "partial"
    reasons = {u["part_id"]: u["reason"] for u in body["unplaced"]}
    assert reasons["big"] == "no_remaining_space"
    assert reasons["huge"] == "exceeds_sheet_size"
    assert body["summary"]["unplaced_parts"] == 2


def test_list_plans(client):
    r = client.get("/api/v1/plans")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 3
    assert body["items"][0]["plan_id"]


def test_get_missing_plan_404(client):
    assert client.get("/api/v1/plans/does-not-exist").status_code == 404


def test_validation_errors(client):
    bad_cases = [
        {},  # 缺字段
        {"sheet": {"width": -1, "height": 100}, "parts": [{"id": "a", "width": 1, "height": 1}]},
        {"sheet": {"width": 100, "height": 100, "kerf": -2}, "parts": [{"id": "a", "width": 1, "height": 1}]},
        {"sheet": {"width": 100, "height": 100}, "parts": []},
        {"sheet": {"width": 100, "height": 100}, "parts": [{"id": "a", "width": 1, "height": 1, "quantity": 0}]},
        {
            "sheet": {"width": 100, "height": 100},
            "parts": [
                {"id": "a", "width": 1, "height": 1},
                {"id": "a", "width": 2, "height": 2},
            ],
        },  # id 重复
    ]
    for payload in bad_cases:
        assert client.post("/api/v1/plans", json=payload).status_code == 422, payload


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
