"""排样引擎测试：不变量、直切可执行性仿真、确定性、未排零件。"""

from __future__ import annotations

from itertools import combinations
from types import SimpleNamespace

from app.nesting import EPS, pack


def part(pid, w, h, qty=1, rotatable=False):
    return SimpleNamespace(id=pid, width=w, height=h, quantity=qty, rotatable=rotatable)


def simulate_cuts(sheet_w, sheet_h, kerf, cuts):
    """按顺序执行切割线，模拟锯切过程，返回最终物理片列表。

    每一刀必须恰好贯穿一个现存物理片（直切约束），否则抛 AssertionError。
    锯缝在切割线的余料侧消耗 kerf 宽度；不足 kerf 的边条消失（废料）。
    """
    pieces = [(0.0, 0.0, float(sheet_w), float(sheet_h))]
    for c in cuts:
        for i, (px, py, pw, ph) in enumerate(pieces):
            if c.orientation == "H":
                on_piece = (
                    abs(c.y1 - c.y2) < EPS
                    and abs(c.x1 - px) < EPS
                    and abs(c.x2 - (px + pw)) < EPS
                    and py + EPS < c.y1 < py + ph - EPS
                )
                if on_piece:
                    below = (px, py, pw, c.y1 - py)
                    above = (px, c.y1 + kerf, pw, py + ph - c.y1 - kerf)
                    pieces.pop(i)
                    pieces.extend(p for p in (below, above) if p[2] > EPS and p[3] > EPS)
                    break
            else:
                on_piece = (
                    abs(c.x1 - c.x2) < EPS
                    and abs(c.y1 - py) < EPS
                    and abs(c.y2 - (py + ph)) < EPS
                    and px + EPS < c.x1 < px + pw - EPS
                )
                if on_piece:
                    left = (px, py, c.x1 - px, ph)
                    right = (c.x1 + kerf, py, px + pw - c.x1 - kerf, ph)
                    pieces.pop(i)
                    pieces.extend(p for p in (left, right) if p[2] > EPS and p[3] > EPS)
                    break
        else:
            raise AssertionError(f"切割线未贯穿任何现存物理片: {c}")
    return pieces


def norm(rects):
    return sorted(tuple(round(v, 6) for v in r) for r in rects)


def check_sheet_invariants(sheet):
    """单块母板：不越界、零件两两间隔 >= kerf、切割仿真可复现零件与余料。"""
    W, H, kerf = sheet.width, sheet.height, sheet.kerf
    ps = sheet.placements

    for p in ps:
        assert -EPS < p.x and p.x + p.w <= W + EPS, f"越界: {p}"
        assert -EPS < p.y and p.y + p.h <= H + EPS, f"越界: {p}"

    for a, b in combinations(ps, 2):
        separated = (
            a.x + a.w + kerf <= b.x + EPS
            or b.x + b.w + kerf <= a.x + EPS
            or a.y + a.h + kerf <= b.y + EPS
            or b.y + b.h + kerf <= a.y + EPS
        )
        assert separated, f"零件间距不足锯缝或重叠: {a} vs {b}"

    pieces = simulate_cuts(W, H, kerf, sheet.cuts)
    expected = [(p.x, p.y, p.w, p.h) for p in ps] + [
        (r.x, r.y, r.w, r.h) for r in sheet.free
    ]
    assert norm(pieces) == norm(expected), "切割仿真结果与零件+余料不一致"


def test_basic_layout_invariants():
    parts = [
        part("door", 800, 400, qty=4, rotatable=True),
        part("shelf", 600, 300, qty=6),
        part("side", 1200, 250, qty=2, rotatable=True),
    ]
    sheets, unplaced = pack(parts, 2440, 1220, 3, 10)
    assert not unplaced
    assert len(sheets) >= 1
    for s in sheets:
        check_sheet_invariants(s)
    total = sum(len(s.placements) for s in sheets)
    assert total == 12


def test_determinism():
    parts = [
        part("a", 500, 300, qty=5, rotatable=True),
        part("b", 700, 200, qty=3),
        part("c", 250, 250, qty=8, rotatable=True),
    ]

    def snapshot():
        sheets, unplaced = pack(parts, 2000, 1000, 4, 5)
        return (
            [
                (
                    [(p.part_id, p.instance, p.x, p.y, p.w, p.h, p.rotated) for p in s.placements],
                    [(c.orientation, c.x1, c.y1, c.x2, c.y2) for c in s.cuts],
                    [(r.x, r.y, r.w, r.h) for r in s.free],
                )
                for s in sheets
            ],
            [(i.part_id, i.instance, r) for i, r in unplaced],
        )

    assert snapshot() == snapshot()


def test_rotation_used_when_needed():
    # 零件 900x300 不旋转放不进 500x1000 的母板，旋转后可以
    sheets, unplaced = pack([part("p", 900, 300, qty=1, rotatable=True)], 500, 1000, 3, 1)
    assert not unplaced
    assert sheets[0].placements[0].rotated is True
    assert sheets[0].placements[0].w == 300
    check_sheet_invariants(sheets[0])


def test_unplaced_when_max_sheets_reached():
    # 每块母板最多放 1 个 900x900，2 块母板放不下 3 个
    sheets, unplaced = pack([part("big", 900, 900, qty=3)], 1000, 1000, 3, 2)
    assert len(sheets) == 2
    assert len(unplaced) == 1
    assert unplaced[0][1] == "no_remaining_space"
    assert unplaced[0][0].label == "big#3"
    for s in sheets:
        check_sheet_invariants(s)


def test_oversize_part_reported():
    sheets, unplaced = pack([part("huge", 3000, 500, qty=1, rotatable=True)], 2440, 1220, 3, 5)
    assert not sheets
    assert len(unplaced) == 1
    assert unplaced[0][1] == "exceeds_sheet_size"


def test_kerf_consumed_between_parts():
    # 两个 497x1000 的零件 + kerf=3 恰好排进 1000 宽母板：497+3+497=997<=1000
    sheets, unplaced = pack([part("p", 497, 1000, qty=2)], 1000, 1000, 3, 1)
    assert not unplaced
    a, b = sorted(sheets[0].placements, key=lambda p: p.x)
    assert b.x - (a.x + a.w) >= 3 - EPS
    check_sheet_invariants(sheets[0])


def test_exact_fit_no_cuts():
    sheets, unplaced = pack([part("full", 1000, 1000, qty=1)], 1000, 1000, 3, 1)
    assert not unplaced
    assert sheets[0].cuts == []
    assert sheets[0].free == []


def test_mixed_many_parts_stress():
    parts = [
        part("p1", 300, 200, qty=30, rotatable=True),
        part("p2", 450, 150, qty=20, rotatable=True),
        part("p3", 120, 80, qty=50),
    ]
    sheets, unplaced = pack(parts, 2440, 1220, 3, 20)
    for s in sheets:
        check_sheet_invariants(s)
    placed = sum(len(s.placements) for s in sheets)
    assert placed + len(unplaced) == 100
