"""FastAPI 应用入口：板材直切排样 API。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from . import db
from .models import PlanListResponse, PlanRequest, PlanResponse
from .service import build_plan


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时自动初始化 SQLite（建表，幂等）
    db.init_db()
    yield


app = FastAPI(
    title="板材直切排样 API",
    description=(
        "面向小型加工坊的矩形零件直切（guillotine）排样服务。"
        "输入母板尺寸、锯缝宽度、母板数量上限与零件清单，"
        "输出每块零件的母板编号、坐标、朝向、按顺序排列的切割线与余料矩形。"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.post(
    "/api/v1/plans",
    response_model=PlanResponse,
    status_code=201,
    tags=["plans"],
    summary="生成排样方案",
)
def create_plan(req: PlanRequest):
    plan = build_plan(req)
    db.insert_plan(plan)
    return plan


@app.get(
    "/api/v1/plans",
    response_model=PlanListResponse,
    tags=["plans"],
    summary="方案列表（摘要，按创建时间倒序）",
)
def list_plans(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    total, items = db.list_plans(limit, offset)
    return {"total": total, "items": items}


@app.get(
    "/api/v1/plans/{plan_id}",
    response_model=PlanResponse,
    tags=["plans"],
    summary="按 ID 查询完整方案",
)
def get_plan(plan_id: str):
    plan = db.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    return plan
