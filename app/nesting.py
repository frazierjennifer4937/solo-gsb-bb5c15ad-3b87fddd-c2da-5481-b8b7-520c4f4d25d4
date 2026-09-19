"""直切（guillotine）排样引擎。

纯 Python 实现，无任何第三方依赖，结果完全确定（相同输入必得相同布局）。

坐标系：原点位于母板左下角，x 轴向右，y 轴向上；单位由调用方决定（通常为毫米）。

锯缝（kerf）模型：每一刀在切割线的"余料侧"消耗 kerf 宽度的材料，
即零件始终保持名义尺寸，余料矩形在切割方向上减少 kerf。
若剩余边条宽度不足 kerf，则该边条视为废料（仍会产生一刀修边切割线）。

直切约束：每一刀都贯穿"当前被切的余料区域"（从一侧到另一侧），
切割线按生成顺序执行即可复现整个排样——每个余料矩形在被消费前
必然已由之前的某一刀（或母板本身）产生。
"""

from __future__ import annotations

from dataclasses import dataclass

EPS = 1e-9


@dataclass(frozen=True)
class PartInstance:
    """展开数量后的单个零件实例。"""

    part_id: str
    instance: int  # 该零件类型内的序号，从 1 开始
    width: float
    height: float
    rotatable: bool

    @property
    def label(self) -> str:
        return f"{self.part_id}#{self.instance}"


@dataclass
class FreeRect:
    x: float
    y: float
    w: float
    h: float


@dataclass
class Placement:
    part_id: str
    instance: int
    x: float
    y: float
    w: float
    h: float
    rotated: bool


@dataclass
class Cut:
    seq: int
    orientation: str  # "H" 水平切割线 / "V" 垂直切割线
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class SheetLayout:
    index: int  # 母板编号，从 1 开始
    width: float
    height: float
    kerf: float
    free: list  # list[FreeRect] 当前余料矩形
    placements: list  # list[Placement]
    cuts: list  # list[Cut] 按执行顺序排列

    @classmethod
    def new(cls, index: int, width: float, height: float, kerf: float) -> "SheetLayout":
        return cls(
            index=index,
            width=width,
            height=height,
            kerf=kerf,
            free=[FreeRect(0.0, 0.0, width, height)],
            placements=[],
            cuts=[],
        )


def expand_instances(parts) -> list[PartInstance]:
    """把带数量的零件展开为实例列表，并按固定规则排序（保证确定性）。

    排序键：长边降序 -> 短边降序 -> 零件 id -> 实例序号，构成全序。
    """
    instances: list[PartInstance] = []
    for p in parts:
        for i in range(1, p.quantity + 1):
            instances.append(
                PartInstance(
                    part_id=p.id,
                    instance=i,
                    width=float(p.width),
                    height=float(p.height),
                    rotatable=bool(p.rotatable),
                )
            )
    instances.sort(
        key=lambda t: (
            -max(t.width, t.height),
            -min(t.width, t.height),
            t.part_id,
            t.instance,
        )
    )
    return instances


def _orientations(inst: PartInstance):
    """候选朝向列表：(宽, 高, 是否旋转)。优先不旋转。"""
    out = [(inst.width, inst.height, False)]
    if inst.rotatable and inst.width != inst.height:
        out.append((inst.height, inst.width, True))
    return out


def _fits_empty_sheet(inst: PartInstance, sheet_w: float, sheet_h: float) -> bool:
    return any(
        pw <= sheet_w + EPS and ph <= sheet_h + EPS
        for pw, ph, _ in _orientations(inst)
    )


def _find_slot(sheets, inst: PartInstance):
    """在所有已开母板的余料中寻找最佳放置位置（best-fit，全序确定性）。

    评分键：短边余量 -> 长边余量 -> 母板编号 -> 余料 y -> 余料 x -> 是否旋转。
    """
    best = None
    for sheet in sheets:
        for idx, fr in enumerate(sheet.free):
            for pw, ph, rot in _orientations(inst):
                if pw <= fr.w + EPS and ph <= fr.h + EPS:
                    dw = fr.w - pw
                    dh = fr.h - ph
                    key = (min(dw, dh), max(dw, dh), sheet.index, fr.y, fr.x, rot)
                    if best is None or key < best[0]:
                        best = (key, sheet, idx, pw, ph, rot)
    return best


def _emit_cut(sheet: SheetLayout, orientation: str, x1: float, y1: float, x2: float, y2: float):
    sheet.cuts.append(
        Cut(seq=len(sheet.cuts) + 1, orientation=orientation, x1=x1, y1=y1, x2=x2, y2=y2)
    )


def _place(sheet: SheetLayout, rect_idx: int, inst: PartInstance, pw: float, ph: float, rotated: bool):
    """在指定余料矩形的左下角放置零件，并以直切方式分裂余料。

    分裂顺序二选一（均为合法直切）：
      - 先横切：水平一刀贯穿整个余料宽度，再对零件所在条带垂直一刀；
      - 先竖切：垂直一刀贯穿整个余料高度，再对零件所在条带水平一刀。
    选择规则：使最大单块余料面积更大者优先，平局时先横切（固定规则，保证确定性）。
    """
    fr = sheet.free.pop(rect_idx)
    kerf = sheet.kerf
    fx, fy, fw, fh = fr.x, fr.y, fr.w, fr.h

    dw = fw - pw  # 零件右侧剩余（未扣锯缝）
    dh = fh - ph  # 零件上方剩余（未扣锯缝）
    right_w = dw - kerf  # 竖切后右侧余料可用宽度
    top_h = dh - kerf  # 横切后上方余料可用高度

    has_right = dw > EPS  # 需要竖直修边刀
    has_top = dh > EPS  # 需要水平修边刀
    right_usable = right_w > EPS  # 右侧余料可用（否则为废料边条）
    top_usable = top_h > EPS  # 上方余料可用

    h_best = max(
        right_w * ph if right_usable else 0.0,
        fw * top_h if top_usable else 0.0,
    )
    v_best = max(
        right_w * fh if right_usable else 0.0,
        pw * top_h if top_usable else 0.0,
    )
    horizontal_first = h_best >= v_best

    if horizontal_first:
        if has_top:
            _emit_cut(sheet, "H", fx, fy + ph, fx + fw, fy + ph)
        if has_right:
            _emit_cut(sheet, "V", fx + pw, fy, fx + pw, fy + ph)
        if right_usable:
            sheet.free.append(FreeRect(fx + pw + kerf, fy, right_w, ph))
        if top_usable:
            sheet.free.append(FreeRect(fx, fy + ph + kerf, fw, top_h))
    else:
        if has_right:
            _emit_cut(sheet, "V", fx + pw, fy, fx + pw, fy + fh)
        if has_top:
            _emit_cut(sheet, "H", fx, fy + ph, fx + pw, fy + ph)
        if right_usable:
            sheet.free.append(FreeRect(fx + pw + kerf, fy, right_w, fh))
        if top_usable:
            sheet.free.append(FreeRect(fx, fy + ph + kerf, pw, top_h))

    sheet.placements.append(
        Placement(
            part_id=inst.part_id,
            instance=inst.instance,
            x=fx,
            y=fy,
            w=pw,
            h=ph,
            rotated=rotated,
        )
    )


def pack(parts, sheet_width: float, sheet_height: float, kerf: float, max_sheets: int):
    """执行排样。

    返回 (sheets, unplaced)：
      - sheets: list[SheetLayout]，每块母板的放置、切割线与余料；
      - unplaced: list[(PartInstance, reason)]，reason ∈
        {"exceeds_sheet_size", "no_remaining_space"}。
    """
    instances = expand_instances(parts)
    sheets: list[SheetLayout] = []
    unplaced: list = []

    for inst in instances:
        slot = _find_slot(sheets, inst)
        if slot is None and len(sheets) < max_sheets:
            if _fits_empty_sheet(inst, sheet_width, sheet_height):
                sheets.append(SheetLayout.new(len(sheets) + 1, sheet_width, sheet_height, kerf))
                slot = _find_slot(sheets, inst)
        if slot is None:
            reason = (
                "no_remaining_space"
                if _fits_empty_sheet(inst, sheet_width, sheet_height)
                else "exceeds_sheet_size"
            )
            unplaced.append((inst, reason))
            continue
        _, sheet, idx, pw, ph, rot = slot
        _place(sheet, idx, inst, pw, ph, rot)

    return sheets, unplaced
