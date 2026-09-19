"""方案构建：调用排样引擎，把结果组装为 API 响应字典。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .models import PlanRequest
from .nesting import pack


def build_plan(req: PlanRequest) -> dict:
    sheets, unplaced = pack(
        req.parts,
        sheet_width=req.sheet.width,
        sheet_height=req.sheet.height,
        kerf=req.sheet.kerf,
        max_sheets=req.sheet.max_sheets,
    )

    sheet_outs = []
    total_cuts = 0
    placed_area = 0.0
    for s in sheets:
        placements = [
            {
                "part_id": p.part_id,
                "instance": p.instance,
                "label": f"{p.part_id}#{p.instance}",
                "x": p.x,
                "y": p.y,
                "width": p.w,
                "height": p.h,
                "rotated": p.rotated,
            }
            for p in s.placements
        ]
        cuts = [
            {
                "seq": c.seq,
                "orientation": c.orientation,
                "x1": c.x1,
                "y1": c.y1,
                "x2": c.x2,
                "y2": c.y2,
                "length": abs(c.x2 - c.x1) + abs(c.y2 - c.y1),
            }
            for c in s.cuts
        ]
        leftovers = [
            {
                "x": r.x,
                "y": r.y,
                "width": r.w,
                "height": r.h,
                "area": r.w * r.h,
            }
            for r in s.free
        ]
        used = sum(p["width"] * p["height"] for p in placements)
        leftover_area = sum(lo["area"] for lo in leftovers)
        placed_area += used
        total_cuts += len(cuts)
        sheet_outs.append(
            {
                "sheet_index": s.index,
                "width": s.width,
                "height": s.height,
                "used_area": used,
                "leftover_area": leftover_area,
                "placements": placements,
                "cuts": cuts,
                "leftovers": leftovers,
            }
        )

    unplaced_outs = [
        {
            "part_id": inst.part_id,
            "instance": inst.instance,
            "label": inst.label,
            "width": inst.width,
            "height": inst.height,
            "rotatable": inst.rotatable,
            "reason": reason,
        }
        for inst, reason in unplaced
    ]

    total_parts = sum(p.quantity for p in req.parts)
    placed_parts = total_parts - len(unplaced_outs)
    sheet_area = req.sheet.width * req.sheet.height
    utilization = (
        round(placed_area / (len(sheet_outs) * sheet_area), 4) if sheet_outs else 0.0
    )
    if placed_parts == total_parts:
        status = "complete"
    elif placed_parts == 0:
        status = "failed"
    else:
        status = "partial"

    return {
        "plan_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "input": req.model_dump(),
        "summary": {
            "sheets_used": len(sheet_outs),
            "total_parts": total_parts,
            "placed_parts": placed_parts,
            "unplaced_parts": len(unplaced_outs),
            "total_cuts": total_cuts,
            "utilization": utilization,
        },
        "sheets": sheet_outs,
        "unplaced": unplaced_outs,
    }
