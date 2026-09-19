"""API 请求 / 响应模型（Pydantic v2）。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------- 请求


class SheetSpec(BaseModel):
    """母板规格。"""

    width: float = Field(gt=0, description="母板宽度")
    height: float = Field(gt=0, description="母板高度")
    kerf: float = Field(ge=0, default=3.0, description="锯缝宽度")
    max_sheets: int = Field(ge=1, le=1000, default=100, description="母板数量上限")


class PartSpec(BaseModel):
    """一种矩形零件（可带数量与可旋转标记）。"""

    id: str = Field(min_length=1, max_length=64, description="零件标识，请求内唯一")
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    quantity: int = Field(ge=1, le=1000, default=1)
    rotatable: bool = Field(default=False, description="是否允许旋转 90°")


class PlanRequest(BaseModel):
    sheet: SheetSpec
    parts: list[PartSpec] = Field(min_length=1, max_length=500)

    @field_validator("parts")
    @classmethod
    def _validate_parts(cls, v: list[PartSpec]) -> list[PartSpec]:
        ids = [p.id for p in v]
        if len(ids) != len(set(ids)):
            raise ValueError("零件 id 必须唯一")
        if sum(p.quantity for p in v) > 5000:
            raise ValueError("零件实例总数不能超过 5000")
        return v


# ---------------------------------------------------------------- 响应


class PlacementOut(BaseModel):
    part_id: str
    instance: int = Field(description="该零件类型内的实例序号")
    label: str = Field(description="实例标签，形如 part_id#instance")
    x: float
    y: float
    width: float
    height: float
    rotated: bool


class CutOut(BaseModel):
    seq: int = Field(description="该母板上的执行顺序，从 1 开始")
    orientation: str = Field(description="H=水平切割线，V=垂直切割线")
    x1: float
    y1: float
    x2: float
    y2: float
    length: float


class LeftoverOut(BaseModel):
    x: float
    y: float
    width: float
    height: float
    area: float


class SheetOut(BaseModel):
    sheet_index: int = Field(description="母板编号，从 1 开始")
    width: float
    height: float
    used_area: float = Field(description="零件占用面积")
    leftover_area: float = Field(description="可用余料面积")
    placements: list[PlacementOut]
    cuts: list[CutOut]
    leftovers: list[LeftoverOut]


class UnplacedOut(BaseModel):
    part_id: str
    instance: int
    label: str
    width: float
    height: float
    rotatable: bool
    reason: str = Field(
        description="exceeds_sheet_size=单件超过母板尺寸；no_remaining_space=母板数量上限内无足够空间"
    )


class SummaryOut(BaseModel):
    sheets_used: int
    total_parts: int
    placed_parts: int
    unplaced_parts: int
    total_cuts: int
    utilization: float = Field(description="零件总面积 / 已用母板总面积")


class PlanResponse(BaseModel):
    plan_id: str
    created_at: str
    status: str = Field(description="complete=全部排入；partial=部分排入；failed=全部未排入")
    input: PlanRequest
    summary: SummaryOut
    sheets: list[SheetOut]
    unplaced: list[UnplacedOut]


class PlanListItem(BaseModel):
    plan_id: str
    created_at: str
    status: str
    sheets_used: int
    placed_parts: int
    unplaced_parts: int
    utilization: float


class PlanListResponse(BaseModel):
    total: int
    items: list[PlanListItem]
