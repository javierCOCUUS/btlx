from __future__ import annotations

import json
import math
import re
from dataclasses import asdict
from pathlib import Path

from .model import ConversionReport, Operation, Part
from .parser import parse_btlx

SAFE_Z = 15.0
RAPID_COMMENT = "(rapid in G0)"

TOOL_DRILL = 1
TOOL_FLAT = 2
TOOL_FINISH = 3

DEFAULT_TOOLSET = {
    TOOL_DRILL: {
        "diameter_mm": 8.0,
        "feed": 800.0,
        "plunge": 250.0,
        "ramp_feed": 250.0,
        "rpm": 8000.0,
        "ramp_angle_deg": 2.0,
        "stepdown_mm": 4.0,
        "stepover_mm": 4.8,
    },
    TOOL_FLAT: {
        "diameter_mm": 8.0,
        "feed": 800.0,
        "plunge": 250.0,
        "ramp_feed": 250.0,
        "rpm": 8000.0,
        "ramp_angle_deg": 2.0,
        "stepdown_mm": 4.0,
        "stepover_mm": 4.8,
    },
    TOOL_FINISH: {
        "diameter_mm": 6.0,
        "feed": 700.0,
        "plunge": 220.0,
        "ramp_feed": 220.0,
        "rpm": 8000.0,
        "ramp_angle_deg": 2.0,
        "stepdown_mm": 3.0,
        "stepover_mm": 3.6,
    },
}

_XY_TOKEN_RE = re.compile(r"([XY])\s*([-+]?\d*\.?\d+)")

# Fixed machine policy requested by user:
#   T1 = drill
#   T2 = roughing
#   T3 = finishing
TOOL_KIND_MAP = {
    # Drill
    "Drilling": TOOL_DRILL,
    # Roughing
    "Slot": TOOL_FLAT,
    "Mortise": TOOL_FLAT,
    "HouseMortise": TOOL_FLAT,
    "Lap": TOOL_FLAT,
    "JackRafterCut": TOOL_FLAT,
    "BirdsMouth": TOOL_FLAT,
    "DoubleCut": TOOL_FLAT,
    "TyroleanDovetail": TOOL_FLAT,
    "Dovetail": TOOL_FLAT,
    "DovetailMortise": TOOL_FLAT,
    "DovetailTenon": TOOL_FLAT,
    "LogHouseJoint": TOOL_FLAT,
    "House": TOOL_FLAT,
    "StepJoint": TOOL_FLAT,
    "StepJointNotch": TOOL_FLAT,
    "ScarfJoint": TOOL_FLAT,
    "SimpleScarf": TOOL_FLAT,
    "Aperture": TOOL_FLAT,
    "RidgeValleyCut": TOOL_FLAT,
    "Planing": TOOL_FLAT,
    # Finishing
    "Tenon": TOOL_FINISH,
    "NailContour": TOOL_FINISH,
    "Outline": TOOL_FINISH,
    "FreeContour": TOOL_FINISH,
    "Marking": TOOL_FINISH,
    "Text": TOOL_FINISH,
    "LongitudinalCut": TOOL_FINISH,
    "ProfileHead": TOOL_FINISH,
    "ProfileCambered": TOOL_FINISH,
    "Chamfer": TOOL_FINISH,
    "RoundArch": TOOL_FINISH,
}


def _num(params: dict, key: str, default: float = 0.0) -> float:
    v = params.get(key, default)
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v))
    except Exception:
        return default


def _load_toolset(
    tools_json_path: str | None,
    db_tool_numbers: dict[int, int] | None = None,
) -> dict[int, dict[str, float]]:
    toolset = {k: dict(v) for k, v in DEFAULT_TOOLSET.items()}
    # Logical machine mapping (fixed by your machine):
    #   T1 drill, T2 roughing, T3 finishing
    select = dict(db_tool_numbers or {})
    select.setdefault(TOOL_DRILL, 1)
    select.setdefault(TOOL_FLAT, 2)
    select.setdefault(TOOL_FINISH, 3)
    reverse_select = {int(v): int(k) for k, v in select.items()}
    if not tools_json_path:
        return toolset
    p = Path(tools_json_path)
    if not p.exists():
        return toolset
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return toolset
    # Accept:
    # 1) plain list[dict]
    # 2) Fusion style object {"data":[...]}
    rows = data
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        rows = data.get("data")
    if not isinstance(rows, list):
        return toolset

    for row in rows:
        if not isinstance(row, dict):
            continue
        post_num = row.get("fusion_post_number")
        if post_num is None:
            post_num = ((row.get("post-process") or {}).get("number"))
        if post_num is None:
            expr = row.get("expressions") or {}
            post_num = expr.get("tool_number")
        if post_num not in reverse_select:
            try:
                post_num = int(float(post_num))
            except Exception:
                continue
        if post_num not in reverse_select:
            continue

        geometry = row.get("geometry") or {}
        presets = ((row.get("start-values") or {}).get("presets") or [])
        preset = presets[0] if presets and isinstance(presets[0], dict) else {}
        try:
            t = reverse_select[int(post_num)]
            diameter = float(
                row.get(
                    "diameter_mm",
                    geometry.get("DC", toolset[t]["diameter_mm"]),
                )
            )
            feed = float(
                row.get(
                    "feed_recommend_mm_per_min",
                    preset.get("v_f", toolset[t]["feed"]),
                )
            )
            plunge = float(
                row.get(
                    "fusion_feed_plunge_mm_per_min",
                    row.get("plunge_recommend_mm_per_min", preset.get("v_f_plunge", toolset[t]["plunge"])),
                )
            )
            ramp_feed = float(preset.get("v_f_ramp", toolset[t]["ramp_feed"]))
            rpm = float(row.get("rpm_recommend", preset.get("n", toolset[t]["rpm"])))
            ramp_angle = float(preset.get("ramp-angle", toolset[t]["ramp_angle_deg"]))
            stepdown = float(
                row.get(
                    "stepdown_mm",
                    preset.get("stepdown", toolset[t]["stepdown_mm"]),
                )
            )
            stepover = float(
                row.get(
                    "stepover_mm",
                    preset.get("stepover", toolset[t]["stepover_mm"]),
                )
            )
        except Exception:
            continue
        toolset[t]["diameter_mm"] = max(0.1, diameter)
        toolset[t]["feed"] = max(1.0, feed)
        toolset[t]["plunge"] = max(1.0, plunge)
        toolset[t]["ramp_feed"] = max(1.0, ramp_feed)
        toolset[t]["rpm"] = max(1.0, rpm)
        toolset[t]["ramp_angle_deg"] = max(0.1, ramp_angle)
        if stepdown > 0:
            toolset[t]["stepdown_mm"] = stepdown
        if stepover > 0:
            toolset[t]["stepover_mm"] = stepover

    return toolset


def _tool_stepdown(tool: dict[str, float]) -> float:
    d = max(0.1, tool.get("diameter_mm", 6.0))
    return max(0.5, min(tool.get("stepdown_mm", d * 0.5), d * 2.0))


def _tool_stepover(tool: dict[str, float]) -> float:
    d = max(0.1, tool.get("diameter_mm", 6.0))
    return max(0.5, min(tool.get("stepover_mm", d * 0.6), d * 1.2))


def _ramp_len_for_depth(depth_abs: float, angle_deg: float) -> float:
    ang = max(0.5, min(angle_deg, 20.0))
    return depth_abs / math.tan(math.radians(ang))


def _angle_to_xy_deg(btlx_angle_deg: float) -> float:
    # In many BTLx timber operations, 90deg is aligned with member X.
    # Convert to math angle used by cos/sin (0deg on +X).
    return btlx_angle_deg - 90.0


def _axes_from_btlx_angle(btlx_angle_deg: float) -> tuple[float, float, float, float]:
    theta = math.radians(_angle_to_xy_deg(btlx_angle_deg))
    ux, uy = math.cos(theta), math.sin(theta)
    vx, vy = -uy, ux
    return ux, uy, vx, vy


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _pt_local_to_global(op: Operation, part: Part, pt: tuple[float, float, float]) -> tuple[float, float, float]:
    ref = op.reference_plane_id
    if ref is None or ref not in part.reference_planes:
        return (pt[0], pt[1], pt[2])

    plane = part.reference_planes[ref]
    ox, oy, oz = plane["origin"]
    xv = plane["xvec"]
    yv = plane["yvec"]
    zv = _cross(xv, yv)

    x, y, z = pt
    gx = ox + x * xv[0] + y * yv[0] + z * zv[0]
    gy = oy + x * xv[1] + y * yv[1] + z * zv[1]
    gz = oz + x * xv[2] + y * yv[2] + z * zv[2]
    return (gx, gy, gz)


def _arc_center_from_3pts(
    p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float]
) -> tuple[float, float] | None:
    x1, y1 = p0
    x2, y2 = p1
    x3, y3 = p2
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return None
    ux = (
        (x1 * x1 + y1 * y1) * (y2 - y3)
        + (x2 * x2 + y2 * y2) * (y3 - y1)
        + (x3 * x3 + y3 * y3) * (y1 - y2)
    ) / d
    uy = (
        (x1 * x1 + y1 * y1) * (x3 - x2)
        + (x2 * x2 + y2 * y2) * (x1 - x3)
        + (x3 * x3 + y3 * y3) * (x2 - x1)
    ) / d
    return (ux, uy)


def _free_contour_real(lines: list[str], op: Operation, part: Part, tool: dict[str, float], default_depth: float = 1.0) -> bool:
    start = op.params.get("__contour_start")
    segments = op.params.get("__contour_segments")
    if not isinstance(start, tuple) or not isinstance(segments, list) or not segments:
        return False

    depth = abs(_num(op.params, "Depth", default_depth))
    depth = min(max(0.2, depth), part.height)
    plunge = tool["plunge"]
    feed = tool["feed"]

    samples_local: list[tuple[float, float, float]] = [start]
    for seg in segments:
        if isinstance(seg, dict):
            end = seg.get("end")
            mid = seg.get("mid")
            if isinstance(end, tuple):
                samples_local.append(end)
            if isinstance(mid, tuple):
                samples_local.append(mid)
    samples_g = [_pt_local_to_global(op, part, p) for p in samples_local]
    ys = [p[1] for p in samples_g]
    zs = [p[2] for p in samples_g]
    y_span = (max(ys) - min(ys)) if ys else 0.0
    z_span = (max(zs) - min(zs)) if zs else 0.0
    use_z_as_machine_y = y_span < 1e-6 and z_span > 1e-6

    def _to_machine_xy(local_pt: tuple[float, float, float]) -> tuple[float, float]:
        gx, gy, gz = _pt_local_to_global(op, part, local_pt)
        return (gx, gz) if use_z_as_machine_y else (gx, gy)

    p0 = _to_machine_xy(start)
    lines.extend(
        [
            f"({op.kind} contour: {op.name}, ref={op.reference_plane_id})",
            f"G0 X{p0[0]:.3f} Y{p0[1]:.3f}",
            f"G1 Z{-depth:.3f} F{plunge:.1f}",
        ]
    )

    curr = p0
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        st = str(seg.get("type", "")).lower()
        if st == "line":
            end = seg.get("end")
            if not isinstance(end, tuple):
                continue
            p = _to_machine_xy(end)
            lines.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F{feed:.1f}")
            curr = p
            continue
        if st == "arc":
            end = seg.get("end")
            mid = seg.get("mid")
            if not isinstance(end, tuple) or not isinstance(mid, tuple):
                continue
            pe = _to_machine_xy(end)
            pm = _to_machine_xy(mid)
            center = _arc_center_from_3pts(curr, pm, pe)
            if center is None:
                lines.append(f"G1 X{pe[0]:.3f} Y{pe[1]:.3f} F{feed:.1f}")
                curr = pe
                continue

            cx, cy = center
            i = cx - curr[0]
            j = cy - curr[1]
            # Orientation from triangle signed area (p0 -> pm -> pe).
            orient = (pm[0] - curr[0]) * (pe[1] - pm[1]) - (pm[1] - curr[1]) * (pe[0] - pm[0])
            code = "G3" if orient > 0 else "G2"
            lines.append(f"{code} X{pe[0]:.3f} Y{pe[1]:.3f} I{i:.3f} J{j:.3f} F{feed:.1f}")
            curr = pe

    lines.append(f"G0 Z{SAFE_Z:.3f}")
    return True


def _emit_header(lines: list[str], machine_profile: str) -> None:
    if machine_profile == "elephant3spindle":
        lines.extend(
            [
                "%",
                "(BTLx -> Mach3 G-code MVP | elephant3spindle)",
                "G90 G94 G91.1 G40 G49 G17",
                "G21",
                "M5",
                "M9",
                f"G0 Z{SAFE_Z:.3f} {RAPID_COMMENT}",
            ]
        )
        return
    lines.extend(
        [
            "%",
            "(BTLx -> Mach3 G-code MVP)",
            "G21 G17 G90 G40 G49 G80",
            f"G0 Z{SAFE_Z:.3f} {RAPID_COMMENT}",
        ]
    )


def _emit_footer(lines: list[str], machine_profile: str) -> None:
    if machine_profile == "elephant3spindle":
        lines.extend([f"G0 Z{SAFE_Z:.3f}", "M5", "M9", "M30", "%"])
        return
    lines.extend([f"G0 Z{SAFE_Z:.3f}", "M5", "M30", "%"])


def _tool_change(
    lines: list[str],
    tool: int,
    current_tool: list[int | None],
    toolset: dict[int, dict[str, float]],
    machine_profile: str,
    do_toolchange: bool = True,
) -> None:
    if current_tool[0] == tool:
        return
    cfg = toolset.get(tool, {})
    rpm = int(round(cfg.get("rpm", 8000.0)))
    feed = cfg.get("feed", 0.0)
    plunge = cfg.get("plunge", 0.0)
    ramp_feed = cfg.get("ramp_feed", plunge)
    stepdown = cfg.get("stepdown_mm", 0.0)
    stepover = cfg.get("stepover_mm", 0.0)
    ramp_angle = cfg.get("ramp_angle_deg", 0.0)
    diameter = cfg.get("diameter_mm", 0.0)
    if machine_profile == "elephant3spindle":
        if do_toolchange:
            lines.extend(
                [
                    "M5",
                    "M9",
                    f"(Tool T{tool}: D={diameter:.3f} RPM={rpm} F={feed:.1f} Fplunge={plunge:.1f} Framp={ramp_feed:.1f} stepdown={stepdown:.3f} stepover={stepover:.3f} rampAngle={ramp_angle:.2f})",
                    f"T{tool}M6",
                    f"S{rpm} M3",
                    "M9",
                    f"G0 Z{SAFE_Z:.3f}",
                ]
            )
        else:
            lines.extend(
                [
                    "M5",
                    "M9",
                    f"(Toolchange skipped - using active spindle as T{tool})",
                    f"(Tool T{tool}: D={diameter:.3f} RPM={rpm} F={feed:.1f} Fplunge={plunge:.1f} Framp={ramp_feed:.1f} stepdown={stepdown:.3f} stepover={stepover:.3f} rampAngle={ramp_angle:.2f})",
                    f"S{rpm} M3",
                    "M9",
                    f"G0 Z{SAFE_Z:.3f}",
                ]
            )
    else:
        if do_toolchange:
            lines.extend([f"T{tool} M6", "G43 H0", f"S{rpm}", "M3", f"G0 Z{SAFE_Z:.3f}"])
        else:
            lines.extend([f"(Toolchange skipped - logical tool T{tool})", f"S{rpm}", "M3", f"G0 Z{SAFE_Z:.3f}"])
    current_tool[0] = tool


def _linear_slot(lines: list[str], op: Operation, part: Part, toolset: dict[int, dict[str, float]]) -> None:
    flat = toolset[TOOL_FLAT]
    tool_diam = flat["diameter_mm"]
    cut_feed = flat["feed"]
    plunge_feed = flat["plunge"]
    ramp_feed = flat.get("ramp_feed", plunge_feed)
    ramp_angle = flat.get("ramp_angle_deg", 2.0)
    x = _num(op.params, "StartX")
    y = _num(op.params, "StartY")
    length = max(0.0, _num(op.params, "Length"))
    depth = min(abs(_num(op.params, "Depth", 0.0)), part.height)
    if depth <= 0.0 or length <= 0.0:
        return

    thickness = max(_num(op.params, "Thickness", tool_diam), tool_diam)
    ux, uy, vx, vy = _axes_from_btlx_angle(_num(op.params, "Angle", 90.0))

    x2 = x + length * ux
    y2 = y + length * uy

    step_down = _tool_stepdown(flat)
    stepover = _tool_stepover(flat)
    passes = max(1, int(math.ceil(thickness / stepover)))

    lines.append(f"(Slot: {op.name})")
    z = -step_down
    while z > -depth:
        z = max(z, -depth)
        for i in range(passes):
            offset = -thickness / 2.0 + (i + 0.5) * (thickness / passes)
            sx = x + vx * offset
            sy = y + vy * offset
            ex = x2 + vx * offset
            ey = y2 + vy * offset
            lines.extend(
                [
                    f"G0 X{sx:.3f} Y{sy:.3f}",
                ]
            )
            seg_len = math.hypot(ex - sx, ey - sy)
            ramp_len = min(seg_len * 0.4, max(tool_diam, _ramp_len_for_depth(abs(z), ramp_angle)))
            if ramp_len > 0.5:
                ux = (ex - sx) / max(seg_len, 1e-9)
                uy = (ey - sy) / max(seg_len, 1e-9)
                rx = sx + ux * ramp_len
                ry = sy + uy * ramp_len
                lines.extend(
                    [
                        f"G1 X{rx:.3f} Y{ry:.3f} Z{z:.3f} F{ramp_feed:.1f}",
                        f"G1 X{ex:.3f} Y{ey:.3f} F{cut_feed:.1f}",
                    ]
                )
            else:
                lines.extend(
                    [
                        f"G1 Z{z:.3f} F{plunge_feed:.1f}",
                        f"G1 X{ex:.3f} Y{ey:.3f} F{cut_feed:.1f}",
                    ]
                )
            lines.extend(
                [
                    f"G0 Z{SAFE_Z:.3f}",
                ]
            )
        z -= step_down


def _drilling(lines: list[str], op: Operation, part: Part, toolset: dict[int, dict[str, float]]) -> None:
    plunge_feed = toolset[TOOL_DRILL]["plunge"]
    x = _num(op.params, "StartX")
    y = _num(op.params, "StartY")
    depth = min(abs(_num(op.params, "Depth", part.height)), part.height)
    if depth <= 0.0:
        return

    lines.extend(
        [
            f"(Drilling: {op.name})",
            f"G0 X{x:.3f} Y{y:.3f}",
            f"G1 Z{-depth:.3f} F{plunge_feed:.1f}",
            f"G0 Z{SAFE_Z:.3f}",
        ]
    )


def _rect_pocket(
    lines: list[str],
    cx: float,
    cy: float,
    angle_deg: float,
    length: float,
    width: float,
    depth: float,
    tool_diam: float,
    cut_feed: float,
    plunge_feed: float,
    step_down: float | None = None,
    stepover: float | None = None,
) -> None:
    if depth <= 0 or length <= 0 or width <= 0:
        return
    ux, uy, vx, vy = _axes_from_btlx_angle(angle_deg + 90.0)

    half_w = width / 2.0
    step = stepover if stepover and stepover > 0 else _tool_stepover({"diameter_mm": tool_diam, "stepover_mm": tool_diam * 0.6})
    stripes = max(1, int(math.ceil(width / step)))
    step_down = step_down if step_down and step_down > 0 else _tool_stepdown({"diameter_mm": tool_diam, "stepdown_mm": tool_diam * 0.5})

    z = -step_down
    while z > -depth:
        z = max(z, -depth)
        for i in range(stripes):
            off = -half_w + (i + 0.5) * (width / stripes)
            sx = cx + vx * off
            sy = cy + vy * off
            ex = sx + ux * length
            ey = sy + uy * length
            lines.extend(
                [
                    f"G0 X{sx:.3f} Y{sy:.3f}",
                    f"G1 Z{z:.3f} F{plunge_feed:.1f}",
                    f"G1 X{ex:.3f} Y{ey:.3f} F{cut_feed:.1f}",
                    f"G0 Z{SAFE_Z:.3f}",
                ]
            )
        z -= step_down


def _mortise(lines: list[str], op: Operation, part: Part, toolset: dict[int, dict[str, float]]) -> None:
    flat = toolset[TOOL_FLAT]
    x = _num(op.params, "StartX")
    y = _num(op.params, "StartY")
    angle = _angle_to_xy_deg(_num(op.params, "Angle", 90.0))
    length = max(0.0, _num(op.params, "Length"))
    width = max(0.0, _num(op.params, "Width"))
    depth = min(abs(_num(op.params, "Depth", 0.0)), part.height)
    lines.append(f"(Mortise/HouseMortise: {op.name})")
    _rect_pocket(
        lines,
        x,
        y - width / 2.0,
        angle,
        length,
        width,
        depth,
        flat["diameter_mm"],
        flat["feed"],
        flat["plunge"],
        step_down=_tool_stepdown(flat),
        stepover=_tool_stepover(flat),
    )


def _tenon(lines: list[str], op: Operation, part: Part, toolset: dict[int, dict[str, float]]) -> None:
    finish = toolset[TOOL_FINISH]
    x = _num(op.params, "StartX")
    y = _num(op.params, "StartY")
    angle = _angle_to_xy_deg(_num(op.params, "Angle", 90.0))
    length = max(0.0, _num(op.params, "Length"))
    width = max(0.0, _num(op.params, "Width"))
    depth = min(max(1.0, _num(op.params, "Height", 5.0) * 0.5), part.height)
    lines.append(f"(Tenon simplified contour: {op.name})")
    _rect_pocket(
        lines,
        x,
        y - width / 2.0,
        angle,
        length,
        width,
        depth,
        finish["diameter_mm"],
        finish["feed"],
        finish["plunge"],
        step_down=_tool_stepdown(finish),
        stepover=_tool_stepover(finish),
    )


def _lap(lines: list[str], op: Operation, part: Part, toolset: dict[int, dict[str, float]]) -> None:
    flat = toolset[TOOL_FLAT]
    x = _num(op.params, "StartX")
    y = _num(op.params, "StartY")
    # BTLx lap angles are often expressed with 90 as longitudinal.
    angle = _angle_to_xy_deg(_num(op.params, "Angle", 90.0))
    length = max(0.0, min(_num(op.params, "Length"), part.length))
    width = max(flat["diameter_mm"], min(_num(op.params, "Width", part.width), part.width))
    depth = min(abs(_num(op.params, "Depth", 0.0)), part.height)
    if depth <= 0.0 or length <= 0.0:
        return
    lines.append(f"(Lap simplified pocket: {op.name}, ref={op.reference_plane_id})")
    _rect_pocket(
        lines,
        x,
        y + width / 2.0,
        angle,
        length,
        width,
        depth,
        flat["diameter_mm"],
        flat["feed"],
        flat["plunge"],
        step_down=_tool_stepdown(flat),
        stepover=_tool_stepover(flat),
    )


def _jack_rafter_cut(lines: list[str], op: Operation, part: Part, toolset: dict[int, dict[str, float]]) -> None:
    flat = toolset[TOOL_FLAT]
    x = _num(op.params, "StartX")
    y = _num(op.params, "StartY")
    start_depth = max(0.0, _num(op.params, "StartDepth", 0.0))
    total_depth = max(0.0, part.height - start_depth)
    if total_depth <= 0.0:
        return

    inclination = _num(op.params, "Inclination", 90.0)
    orient = str(op.params.get("Orientation", "start")).lower()
    # 3-axis stair-step plane approximation using inclination against normal direction.
    slope = math.tan(math.radians(inclination - 90.0))
    sign = -1.0 if orient == "start" else 1.0
    ux, uy, vx, vy = _axes_from_btlx_angle(_num(op.params, "Angle", 90.0))

    step_down = _tool_stepdown(flat)
    ramp_feed = flat.get("ramp_feed", flat["plunge"])
    ramp_angle = flat.get("ramp_angle_deg", 2.0)
    z_abs = step_down
    lines.append(f"(JackRafterCut simplified: {op.name}, ref={op.reference_plane_id}, inc={inclination:.3f})")
    while z_abs <= total_depth + 1e-9:
        z_abs = min(z_abs, total_depth)
        shift = sign * slope * z_abs
        sx = x + vx * shift
        sy = y + vy * shift
        ex = sx + ux * max(part.width, flat["diameter_mm"])
        ey = sy + uy * max(part.width, flat["diameter_mm"])
        lines.extend([f"G0 X{sx:.3f} Y{sy:.3f}"])
        seg_len = math.hypot(ex - sx, ey - sy)
        ramp_len = min(seg_len * 0.4, max(flat["diameter_mm"], _ramp_len_for_depth(z_abs, ramp_angle)))
        if ramp_len > 0.5:
            ux2 = (ex - sx) / max(seg_len, 1e-9)
            uy2 = (ey - sy) / max(seg_len, 1e-9)
            rx = sx + ux2 * ramp_len
            ry = sy + uy2 * ramp_len
            lines.extend(
                [
                    f"G1 X{rx:.3f} Y{ry:.3f} Z{-z_abs:.3f} F{ramp_feed:.1f}",
                    f"G1 X{ex:.3f} Y{ey:.3f} F{flat['feed']:.1f}",
                    f"G0 Z{SAFE_Z:.3f}",
                ]
            )
        else:
            lines.extend(
                [
                    f"G1 Z{-z_abs:.3f} F{flat['plunge']:.1f}",
                    f"G1 X{ex:.3f} Y{ey:.3f} F{flat['feed']:.1f}",
                    f"G0 Z{SAFE_Z:.3f}",
                ]
            )
        z_abs += step_down


def _generic_line(lines: list[str], op: Operation, part: Part, tool: dict[str, float], default_depth: float = 1.0) -> None:
    x = _num(op.params, "StartX")
    y = _num(op.params, "StartY")
    angle = _angle_to_xy_deg(_num(op.params, "Angle", 90.0))
    length = max(tool["diameter_mm"], min(_num(op.params, "Length", part.width), part.length))
    depth = abs(_num(op.params, "Depth", default_depth))
    depth = min(max(0.2, depth), part.height)
    theta = math.radians(angle)
    ex = x + length * math.cos(theta)
    ey = y + length * math.sin(theta)
    lines.extend(
        [
            f"({op.kind} line approximation: {op.name}, ref={op.reference_plane_id})",
            f"G0 X{x:.3f} Y{y:.3f}",
            f"G1 Z{-depth:.3f} F{tool['plunge']:.1f}",
            f"G1 X{ex:.3f} Y{ey:.3f} F{tool['feed']:.1f}",
            f"G0 Z{SAFE_Z:.3f}",
        ]
    )


def _generic_pocket(lines: list[str], op: Operation, part: Part, tool: dict[str, float], default_depth: float = 5.0) -> None:
    x = _num(op.params, "StartX")
    y = _num(op.params, "StartY")
    angle = _angle_to_xy_deg(_num(op.params, "Angle", 90.0))
    length = max(tool["diameter_mm"], min(_num(op.params, "Length", part.width), part.length))
    width = max(tool["diameter_mm"], min(_num(op.params, "Width", part.width), part.width))
    depth = abs(_num(op.params, "Depth", default_depth))
    if depth <= 0.0:
        depth = default_depth
    depth = min(max(0.2, depth), part.height)
    lines.append(f"({op.kind} pocket approximation: {op.name}, ref={op.reference_plane_id})")
    _rect_pocket(
        lines,
        x,
        y + width / 2.0,
        angle,
        length,
        width,
        depth,
        tool["diameter_mm"],
        tool["feed"],
        tool["plunge"],
        step_down=_tool_stepdown(tool),
        stepover=_tool_stepover(tool),
    )


def _generic_planing(lines: list[str], op: Operation, part: Part, tool: dict[str, float]) -> None:
    start_x = _num(op.params, "StartX", 0.0)
    length = max(tool["diameter_mm"], min(_num(op.params, "Length", part.length), part.length))
    depth = abs(_num(op.params, "Depth", 0.5))
    if depth <= 0.0:
        depth = 0.5
    depth = min(depth, part.height)
    lines.append(f"(Planing approximation: {op.name})")
    _rect_pocket(
        lines,
        start_x,
        part.width / 2.0,
        0.0,
        length,
        part.width,
        depth,
        tool["diameter_mm"],
        tool["feed"],
        tool["plunge"],
        step_down=_tool_stepdown(tool),
        stepover=_tool_stepover(tool),
    )


def _birdsmouth(lines: list[str], op: Operation, part: Part, toolset: dict[int, dict[str, float]]) -> None:
    flat = toolset[TOOL_FLAT]
    x = _num(op.params, "StartX")
    y = _num(op.params, "StartY")
    width = _num(op.params, "Width", 0.0)
    if width <= 0.0:
        width = max(flat["diameter_mm"], part.width * 0.4)
    depth = abs(_num(op.params, "Depth", 0.0))
    if depth <= 0.0:
        depth = min(part.height * 0.3, 30.0)
    angle = _angle_to_xy_deg(_num(op.params, "Angle", 90.0))
    length = max(flat["diameter_mm"], min(width, part.length))
    lines.append(f"(BirdsMouth profiled pocket: {op.name}, ref={op.reference_plane_id})")
    _rect_pocket(
        lines,
        x,
        y + width / 2.0,
        angle,
        length,
        width,
        min(depth, part.height),
        flat["diameter_mm"],
        flat["feed"],
        flat["plunge"],
        step_down=_tool_stepdown(flat),
        stepover=_tool_stepover(flat),
    )


def _doublecut(lines: list[str], op: Operation, part: Part, toolset: dict[int, dict[str, float]]) -> None:
    # Model as two jack-like cutting planes referenced by angle1/2 and inclination1/2.
    params1 = dict(op.params)
    params1["Angle"] = _num(op.params, "Angle1", _num(op.params, "Angle", 90.0))
    params1["Inclination"] = _num(op.params, "Inclination1", _num(op.params, "Inclination", 90.0))
    op1 = Operation(kind="JackRafterCut", name=f"{op.name}-A", reference_plane_id=op.reference_plane_id, params=params1)

    params2 = dict(op.params)
    params2["Angle"] = _num(op.params, "Angle2", _num(op.params, "Angle", 90.0))
    params2["Inclination"] = _num(op.params, "Inclination2", _num(op.params, "Inclination", 90.0))
    op2 = Operation(kind="JackRafterCut", name=f"{op.name}-B", reference_plane_id=op.reference_plane_id, params=params2)

    lines.append(f"(DoubleCut decomposed to 2 plane cuts: {op.name})")
    _jack_rafter_cut(lines, op1, part, toolset)
    _jack_rafter_cut(lines, op2, part, toolset)


def _generic_fallback(lines: list[str], op: Operation, part: Part, tool: dict[str, float]) -> None:
    x = _num(op.params, "StartX", 0.0)
    y = _num(op.params, "StartY", 0.0)
    depth = min(max(0.2, abs(_num(op.params, "Depth", 0.2))), part.height)
    lines.extend(
        [
            f"(Fallback conversion for {op.kind}: {op.name}, ref={op.reference_plane_id})",
            f"G0 X{x:.3f} Y{y:.3f}",
            f"G1 Z{-depth:.3f} F{tool['plunge']:.1f}",
            f"G0 Z{SAFE_Z:.3f}",
        ]
    )


def _skip(report: ConversionReport, kind: str) -> None:
    report.skipped_ops += 1
    report.skipped_by_kind[kind] = report.skipped_by_kind.get(kind, 0) + 1


def _mapped_tool_for_kind(kind: str) -> int | None:
    return TOOL_KIND_MAP.get(kind)


def _normalize_part_xy(lines: list[str]) -> list[str]:
    base_x: float | None = None
    base_y: float | None = None

    for line in lines:
        if not line.startswith(("G0", "G1", "G2", "G3")):
            continue
        vals = {m.group(1): float(m.group(2)) for m in _XY_TOKEN_RE.finditer(line)}
        if base_x is None and "X" in vals:
            base_x = vals["X"]
        if base_y is None and "Y" in vals:
            base_y = vals["Y"]
        if base_x is not None and base_y is not None:
            break

    if base_x is None and base_y is None:
        return lines

    def _shift_line(line: str) -> str:
        if not line.startswith(("G0", "G1", "G2", "G3")):
            return line

        vals = {m.group(1): float(m.group(2)) for m in _XY_TOKEN_RE.finditer(line)}
        out = line
        if base_x is not None and "X" in vals:
            out = re.sub(r"X\s*[-+]?\d*\.?\d+", f"X{(vals['X'] - base_x):.3f}", out, count=1)
        if base_y is not None and "Y" in vals:
            out = re.sub(r"Y\s*[-+]?\d*\.?\d+", f"Y{(vals['Y'] - base_y):.3f}", out, count=1)
        return out

    return [_shift_line(line) for line in lines]


def convert_file(
    input_path: str,
    output_path: str,
    report_path: str | None = None,
    tools_json_path: str | None = None,
    machine_profile: str = "generic",
    no_toolchange: bool = False,
    local_origin: bool = False,
    strict_tool_map: bool = False,
    db_tool_numbers: dict[int, int] | None = None,
) -> ConversionReport:
    program = parse_btlx(input_path)
    toolset = _load_toolset(tools_json_path, db_tool_numbers=db_tool_numbers)
    lines: list[str] = []
    _emit_header(lines, machine_profile)

    current_tool: list[int | None] = [None]
    report = ConversionReport(source_path=input_path, output_path=output_path)

    for part in program.parts:
        part_lines: list[str] = [f"(Part {part.part_id} L={part.length:.3f} W={part.width:.3f} H={part.height:.3f})"]
        for op in part.operations:
            mapped_tool = _mapped_tool_for_kind(op.kind)
            if strict_tool_map and mapped_tool is None:
                raise ValueError(
                    f"Operacion sin mapeo de herramienta (strict_tool_map): kind={op.kind}, part={part.part_id}, op={op.name}"
                )
            flat_tool = toolset[TOOL_FLAT]
            finish_tool = toolset[TOOL_FINISH]
            if op.kind == "Drilling":
                _tool_change(part_lines, TOOL_DRILL, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _drilling(part_lines, op, part, toolset)
                report.converted_ops += 1
                continue
            if op.kind == "Slot":
                _tool_change(part_lines, TOOL_FLAT, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _linear_slot(part_lines, op, part, toolset)
                report.converted_ops += 1
                continue
            if op.kind in ("Mortise", "HouseMortise"):
                _tool_change(part_lines, TOOL_FLAT, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _mortise(part_lines, op, part, toolset)
                report.converted_ops += 1
                continue
            if op.kind == "Tenon":
                _tool_change(part_lines, TOOL_FINISH, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _tenon(part_lines, op, part, toolset)
                report.converted_ops += 1
                continue
            if op.kind == "Lap":
                _tool_change(part_lines, TOOL_FLAT, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _lap(part_lines, op, part, toolset)
                report.converted_ops += 1
                continue
            if op.kind == "JackRafterCut":
                _tool_change(part_lines, TOOL_FLAT, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _jack_rafter_cut(part_lines, op, part, toolset)
                report.converted_ops += 1
                continue
            if op.kind == "BirdsMouth":
                _tool_change(part_lines, TOOL_FLAT, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _birdsmouth(part_lines, op, part, toolset)
                report.converted_ops += 1
                continue
            if op.kind == "DoubleCut":
                _tool_change(part_lines, TOOL_FLAT, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _doublecut(part_lines, op, part, toolset)
                report.converted_ops += 1
                continue

            if op.kind in ("TyroleanDovetail", "Dovetail", "DovetailMortise", "DovetailTenon", "LogHouseJoint", "House", "StepJoint", "StepJointNotch", "ScarfJoint", "SimpleScarf", "Aperture", "RidgeValleyCut"):
                _tool_change(part_lines, TOOL_FLAT, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _generic_pocket(part_lines, op, part, flat_tool)
                report.converted_ops += 1
                continue

            if op.kind in ("NailContour", "Outline", "FreeContour"):
                _tool_change(part_lines, TOOL_FINISH, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                if not _free_contour_real(part_lines, op, part, finish_tool, default_depth=0.8):
                    _generic_line(part_lines, op, part, finish_tool, default_depth=0.8)
                report.converted_ops += 1
                continue

            if op.kind in ("Marking", "Text", "LongitudinalCut", "ProfileHead", "ProfileCambered", "Chamfer", "RoundArch"):
                _tool_change(part_lines, TOOL_FINISH, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _generic_line(part_lines, op, part, finish_tool, default_depth=0.8)
                report.converted_ops += 1
                continue

            if op.kind == "Planing":
                _tool_change(part_lines, TOOL_FLAT, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
                _generic_planing(part_lines, op, part, flat_tool)
                report.converted_ops += 1
                continue

            _tool_change(part_lines, TOOL_FINISH, current_tool, toolset, machine_profile, do_toolchange=not no_toolchange)
            _generic_fallback(part_lines, op, part, finish_tool)
            report.converted_ops += 1

        if local_origin:
            part_lines = _normalize_part_xy(part_lines)
        lines.extend(part_lines)

    _emit_footer(lines, machine_profile)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if report_path:
        rp = Path(report_path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

    return report
