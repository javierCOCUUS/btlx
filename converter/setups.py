"""
setups.py - Build setup plan from parsed BTLx operations.

Policy goals:
- Keep deterministic setup assignment from face + operation type.
- Treat testa operations (faces 4/6) with explicit heuristics.
- Produce an auditable per-operation report (reason + suggested setup).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import argparse
import json
from pathlib import Path
from typing import Any

from faces import FACE_DEFAULT_SETUP, FACE_FLIP_INSTRUCTION


SetupId = int


FACE_HUMAN_LABEL = {
    1: "bottom",
    2: "top",
    3: "left",
    4: "start_end",
    5: "right",
    6: "end_end",
}


# Operations that are usually "through/angle cuts" rather than pockets.
CUT_LIKE_TYPES = {
    "JackRafterCut",
    "DoubleCut",
    "CutOff",
    "LongitudinalCut",
    "RidgeValleyCut",
    "SimpleScarf",
    "ScarfJoint",
    "StepJoint",
    "StepJointNotch",
    "BirdsMouth",
}

# Operations that are clearly pocket/rebate/freeform machining.
POCKET_LIKE_TYPES = {
    "Lap",
    "Mortise",
    "HouseMortise",
    "House",
    "DovetailMortise",
    "DovetailTenon",
    "Dovetail",
    "TyroleanDovetail",
    "Tenon",
    "Slot",
    "FreeContour",
    "ProfileHead",
    "ProfileCambered",
    "Planing",
    "Drilling",
    "NailContour",
    "Marking",
    "Text",
}


@dataclass
class SetupOperation:
    part_guid: str
    part_name: str
    part_number: str
    op_guid: str
    op_index: int
    op_name: str
    op_type: str
    face: int | None
    reference_plane_id: int | None
    setup: SetupId
    reason: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class SetupGroup:
    setup: SetupId
    flip_instruction: str | None
    operations: list[SetupOperation] = field(default_factory=list)


@dataclass
class SetupPlan:
    groups: dict[SetupId, SetupGroup]
    unresolved: list[SetupOperation]


@dataclass
class SetupPolicy:
    split_testa_setups: bool = True
    unknown_testa_to_dedicated: bool = True
    optimize_flips: bool = False
    through_cut_tol_mm: float = 0.5
    prefer_drilling_setup1: bool = True
    preferred_primary_face: int = 2
    consolidate_opposite_cuts: bool = False
    auto_min_setups: bool = False
    testa_start_face: int = 4
    testa_end_face: int = 6


def _is_testa(face: int | None, policy: SetupPolicy) -> bool:
    return face in (policy.testa_start_face, policy.testa_end_face)


def _setup_for_primary_face(policy: SetupPolicy) -> int:
    face = policy.preferred_primary_face
    if face == 1:
        return FACE_DEFAULT_SETUP.get(1, 2)
    return FACE_DEFAULT_SETUP.get(2, 1)


def _float_param(params: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except Exception:
        return default


def _setup_for_face(face: int) -> int:
    return FACE_DEFAULT_SETUP.get(face, 1)


def _angle_complexity(params: dict[str, Any]) -> str:
    """
    Heuristic for testa operations:
    - simple: near orthogonal attack (Angle/Inclination ~= 90)
    - complex: otherwise
    """
    angle = _float_param(params, "Angle", 90.0)
    incl = _float_param(params, "Inclination", 90.0)
    if abs(angle - 90.0) <= 2.0 and abs(incl - 90.0) <= 2.0:
        return "simple"
    return "complex"


def _dedicated_testa_setup(face: int | None, policy: SetupPolicy) -> int:
    split_testa_setups = policy.split_testa_setups
    if not split_testa_setups:
        return 5
    if face == policy.testa_start_face:
        return 5
    if face == policy.testa_end_face:
        return 6
    return 5


def _propose_setup_for_testa(op: dict[str, Any], policy: SetupPolicy) -> tuple[int, str]:
    face = op.get("face")
    op_type = str(op.get("type", "Unknown"))
    params = op.get("params", {}) if isinstance(op.get("params"), dict) else {}
    complexity = _angle_complexity(params)

    if op_type in CUT_LIKE_TYPES:
        if complexity == "simple":
            return 1, f"testa corte simple ({op_type}) -> setup 1"
        sid = _dedicated_testa_setup(face, policy)
        return sid, f"testa corte complejo ({op_type}) -> setup {sid}"

    if op_type in POCKET_LIKE_TYPES:
        sid = _dedicated_testa_setup(face, policy)
        return sid, f"testa pocket/rebaje ({op_type}) -> setup {sid}"

    if policy.unknown_testa_to_dedicated:
        sid = _dedicated_testa_setup(face, policy)
        return sid, f"testa tipo desconocido ({op_type}) -> setup {sid}"

    return 1, f"testa tipo desconocido ({op_type}) -> fallback setup 1"


def _is_through_cut_operation(op: dict[str, Any], part: dict[str, Any], tol_mm: float) -> bool:
    op_type = str(op.get("type", "Unknown"))
    if op_type not in CUT_LIKE_TYPES:
        return False

    params = op.get("params", {}) if isinstance(op.get("params"), dict) else {}
    part_h = _float_param(part, "height", 0.0)
    if part_h <= 0.0:
        return False

    depth = abs(_float_param(params, "Depth", 0.0))
    if depth > 0.0 and depth >= (part_h - max(0.0, tol_mm)):
        return True

    # Heuristic for cut-like features often encoded without explicit depth.
    if op_type in {"JackRafterCut", "DoubleCut", "CutOff", "LongitudinalCut", "RidgeValleyCut"}:
        start_depth = max(0.0, _float_param(params, "StartDepth", 0.0))
        if (part_h - start_depth) >= (part_h - max(0.0, tol_mm)):
            return True
    return False


def _default_setup_for_operation(op: dict[str, Any], part: dict[str, Any], policy: SetupPolicy) -> tuple[int, str]:
    face = op.get("face")
    op_type = str(op.get("type", "Unknown"))
    primary_setup = _setup_for_primary_face(policy)

    # Keep drilling in setup 1 when optimization is enabled to reduce flips.
    if policy.optimize_flips and policy.prefer_drilling_setup1 and op_type == "Drilling":
        return primary_setup, f"optimize_flips: drilling -> setup {primary_setup}"

    # Optional aggressive consolidation between top/bottom pair.
    # This minimizes flips but can degrade geometric fidelity in some cases.
    if (
        policy.optimize_flips
        and policy.consolidate_opposite_cuts
        and op_type in CUT_LIKE_TYPES
        and face in (1, 2)
        and policy.preferred_primary_face in (1, 2)
        and face != policy.preferred_primary_face
    ):
        return (
            primary_setup,
            f"optimize_flips: mover corte cara {face} -> setup {primary_setup} (cara {policy.preferred_primary_face})",
        )

    # Conservative optimization: only remap through-cuts on testas.
    # Do NOT remap lateral/bottom cuts to top because quality can degrade.
    if policy.optimize_flips and _is_through_cut_operation(op, part, policy.through_cut_tol_mm):
        if face in (policy.testa_start_face, policy.testa_end_face):
            return 1, f"optimize_flips: corte pasante desde cara {face} -> setup 1 (cara 2)"

    if _is_testa(face, policy):
        return _propose_setup_for_testa(op, policy)

    if isinstance(face, int):
        setup = FACE_DEFAULT_SETUP.get(face, 1)
        return setup, f"setup por cara {face}"

    # No face info: keep in setup 1 but mark unresolved.
    if policy.optimize_flips and policy.preferred_primary_face in (1, 2):
        return primary_setup, f"sin cara clara, optimize_flips -> setup {primary_setup}"
    return 1, "sin cara clara, fallback setup 1"


def _can_move_op_to_setup(
    op_row: SetupOperation,
    part: dict[str, Any],
    target_setup: int,
    policy: SetupPolicy,
) -> tuple[bool, str]:
    """
    Conservative "safe to remap" heuristic used by auto_min_setups.
    """
    if op_row.setup == target_setup:
        return True, "ya esta en setup objetivo"

    op_type = str(op_row.op_type)
    face = op_row.face
    params = op_row.params if isinstance(op_row.params, dict) else {}
    tol = max(0.0, float(policy.through_cut_tol_mm))

    # Unknown face can follow dominant setup (e.g. Planing).
    if face is None:
        return True, "sin cara: se puede consolidar"

    # Keep dedicated testa pockets conservative.
    if _is_testa(face, policy) and op_type in POCKET_LIKE_TYPES and op_type != "Drilling":
        return False, "testa pocket no se remapea automaticamente"

    # Through drilling can be consolidated.
    if op_type == "Drilling":
        depth = abs(_float_param(params, "Depth", 0.0))
        part_h = abs(_float_param(part, "height", 0.0))
        if depth >= max(0.0, part_h - tol):
            return True, "taladro pasante consolidable"
        return False, "taladro no pasante"

    # Optional opposite-face consolidation for cut-like ops (1<->2).
    if op_type in CUT_LIKE_TYPES and face in (1, 2) and policy.consolidate_opposite_cuts:
        return True, "corte 1/2 consolidable"

    # Lateral lap (3/5) that cuts through member width can be remapped.
    if op_type == "Lap" and face in (3, 5):
        depth = abs(_float_param(params, "Depth", 0.0))
        part_w = abs(_float_param(part, "width", 0.0))
        if depth >= max(0.0, part_w - tol):
            return True, "lap lateral pasante consolidable"
        return False, "lap lateral no pasante"

    # Through-cuts on testas can be consolidated if optimization active.
    if policy.optimize_flips and _is_testa(face, policy):
        if _is_through_cut_operation(
            {
                "type": op_type,
                "params": params,
                "face": face,
            },
            part,
            policy.through_cut_tol_mm,
        ):
            return True, "testa pasante consolidable"

    return False, "no seguro de consolidar"


def build_setup_plan(
    parts: list[dict[str, Any]],
    *,
    op_setup_overrides: dict[str, int] | None = None,
    policy: SetupPolicy | None = None,
) -> SetupPlan:
    """
    Build setup groups.

    Args:
        parts: output of parser.parse_btlx
        op_setup_overrides: {"op_guid": setup_id} to force specific setup
        policy: setup policy flags
    """
    cfg = policy or SetupPolicy()
    overrides = op_setup_overrides or {}
    groups: dict[int, SetupGroup] = {}
    unresolved: list[SetupOperation] = []
    rows: list[SetupOperation] = []

    # Optional dedicated setups for complex testa.
    setup_flip = dict(FACE_FLIP_INSTRUCTION)
    setup_flip[5] = "Setup dedicado testa cara 4 (definir posicion manual en maquina)"
    setup_flip[6] = "Setup dedicado testa cara 6 (definir posicion manual en maquina)"

    for part in parts:
        part_guid = str(part.get("guid", ""))
        part_name = str(part.get("name", ""))
        part_number = str(part.get("number", ""))

        for op_idx, op in enumerate(part.get("operations", [])):
            op_guid = str(op.get("guid", ""))
            op_name = str(op.get("name", op.get("type", "")))
            op_type = str(op.get("type", "Unknown"))
            face = op.get("face")
            ref_id = op.get("reference_plane_id")
            params = op.get("params", {})

            if op_guid and op_guid in overrides:
                setup = int(overrides[op_guid])
                reason = "override manual"
            else:
                setup, reason = _default_setup_for_operation(op, part, cfg)

            row = SetupOperation(
                part_guid=part_guid,
                part_name=part_name,
                part_number=part_number,
                op_guid=op_guid,
                op_index=op_idx,
                op_name=op_name,
                op_type=op_type,
                face=face if isinstance(face, int) else None,
                reference_plane_id=ref_id if isinstance(ref_id, int) else None,
                setup=setup,
                reason=reason,
                params=params if isinstance(params, dict) else {},
            )

            rows.append(row)

    if cfg.auto_min_setups:
        part_lookup = {str(p.get("guid", "")): p for p in parts}
        by_part: dict[str, list[SetupOperation]] = {}
        for r in rows:
            by_part.setdefault(r.part_guid, []).append(r)

        for part_guid, ops in by_part.items():
            if not ops:
                continue
            counts: dict[int, int] = {}
            for r in ops:
                counts[r.setup] = counts.get(r.setup, 0) + 1

            # Dominant setup by operation count.
            target_setup = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))[0]
            part = part_lookup.get(part_guid, {})

            for r in ops:
                can, why = _can_move_op_to_setup(r, part, target_setup, cfg)
                if can and r.setup != target_setup:
                    old = r.setup
                    r.setup = target_setup
                    r.reason = f"{r.reason}; auto_min_setups: {why} ({old}->{target_setup})"
                elif not can:
                    r.reason = f"{r.reason}; auto_min_setups: {why}"

    for row in rows:
        if not isinstance(row.face, int):
            unresolved.append(row)

        grp = groups.get(row.setup)
        if grp is None:
            grp = SetupGroup(setup=row.setup, flip_instruction=setup_flip.get(row.setup))
            groups[row.setup] = grp
        grp.operations.append(row)

    return SetupPlan(groups=groups, unresolved=unresolved)


def plan_as_text(plan: SetupPlan, detailed: bool = False) -> str:
    lines: list[str] = []
    for sid in sorted(plan.groups.keys()):
        grp = plan.groups[sid]
        lines.append(f"Setup {sid}: ops={len(grp.operations)}")
        if grp.flip_instruction:
            lines.append(f"  Flip: {grp.flip_instruction}")
        by_part: dict[str, int] = {}
        by_face: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for op in grp.operations:
            key = op.part_name or f"part_{op.part_number}"
            by_part[key] = by_part.get(key, 0) + 1
            face_key = str(op.face) if op.face is not None else "?"
            by_face[face_key] = by_face.get(face_key, 0) + 1
            by_type[op.op_type] = by_type.get(op.op_type, 0) + 1
        lines.append(f"  Parts: {by_part}")
        lines.append(f"  Faces: {by_face}")
        lines.append(f"  Types: {by_type}")

        if detailed:
            for op in grp.operations:
                face_txt = "?" if op.face is None else str(op.face)
                lines.append(
                    f"    - part={op.part_number} op_idx={op.op_index} op={op.op_type} face={face_txt} ref={op.reference_plane_id} -> setup {op.setup} ({op.reason})"
                )

    if plan.unresolved:
        lines.append(f"Unresolved face ops: {len(plan.unresolved)}")

    return "\n".join(lines)


def plan_to_json(plan: SetupPlan) -> dict[str, Any]:
    return {
        "setups": {
            str(sid): {
                "flip_instruction": grp.flip_instruction,
                "operations": [
                    {
                        "part_guid": o.part_guid,
                        "part_name": o.part_name,
                        "part_number": o.part_number,
                        "op_guid": o.op_guid,
                        "op_index": o.op_index,
                        "op_name": o.op_name,
                        "op_type": o.op_type,
                        "face": o.face,
                        "face_human": FACE_HUMAN_LABEL.get(o.face),
                        "reference_plane_id": o.reference_plane_id,
                        "setup": o.setup,
                        "reason": o.reason,
                    }
                    for o in grp.operations
                ],
            }
            for sid, grp in sorted(plan.groups.items())
        },
        "unresolved_count": len(plan.unresolved),
    }


def _build_cli() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Build setup plan from BTLx file")
    ap.add_argument("btlx_file", help="Input .btlx path")
    ap.add_argument("--detailed", action="store_true", help="Print operation-level details")
    ap.add_argument("--single-testa-setup", action="store_true", help="Use setup 5 for both testa faces")
    ap.add_argument("--unknown-testa-to-setup1", action="store_true", help="Keep unknown testa types in setup 1")
    ap.add_argument("--auto-min-setups", action="store_true", help="Per-part automatic setup minimization")
    ap.add_argument("--json-out", help="Write JSON report to this path")
    return ap


if __name__ == "__main__":
    from parser import parse_btlx

    args = _build_cli().parse_args()

    parts = parse_btlx(args.btlx_file)
    policy = SetupPolicy(
        split_testa_setups=not args.single_testa_setup,
        unknown_testa_to_dedicated=not args.unknown_testa_to_setup1,
        auto_min_setups=args.auto_min_setups,
    )
    plan = build_setup_plan(parts, policy=policy)
    print(plan_as_text(plan, detailed=args.detailed))

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(plan_to_json(plan), indent=2), encoding="utf-8")
        print(f"\nJSON report written: {out_path}")
