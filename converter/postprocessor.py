"""
postprocessor.py - Bridge module for Grasshopper and CLI.

Uses the converter in src/btlx2gcode/post.py and adds:
- setup plan report based on converter/setups.py
- simple callable API for GhPython component
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# Paths
THIS_DIR = Path(__file__).resolve().parent
ROOT_DIR = THIS_DIR.parent
SRC_DIR = ROOT_DIR / "src"

# Ensure local converter modules are resolved first (parser.py, setups.py, faces.py)
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

# Ensure btlx2gcode package is importable
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from btlx2gcode.post import convert_file  # type: ignore


def _load_local_module(name: str, filename: str):
    path = THIS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_local_parser = _load_local_module("converter_local_parser", "parser.py")
_local_setups = _load_local_module("converter_local_setups", "setups.py")

parse_btlx = _local_parser.parse_btlx
SetupPolicy = _local_setups.SetupPolicy
build_setup_plan = _local_setups.build_setup_plan
plan_to_json = _local_setups.plan_to_json


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find_project_parts(root: ET.Element) -> tuple[ET.Element | None, ET.Element | None]:
    project = None
    parts = None
    for ch in list(root):
        if _local(ch.tag) == "Project":
            project = ch
            break
    if project is None:
        return None, None
    for ch in list(project):
        if _local(ch.tag) == "Parts":
            parts = ch
            break
    return project, parts


def _find_processings(part_el: ET.Element) -> ET.Element | None:
    for ch in list(part_el):
        if _local(ch.tag) == "Processings":
            return ch
    return None


def _build_part_setup_index(parts: list[dict[str, Any]], split_testa_setups: bool) -> dict[tuple[str, int], int]:
    """Map (part_number, op_index) -> setup."""
    policy = SetupPolicy(split_testa_setups=split_testa_setups)
    plan = build_setup_plan(parts, policy=policy)
    out: dict[tuple[str, int], int] = {}
    for sid, grp in plan.groups.items():
        for op in grp.operations:
            out[(str(op.part_number), int(op.op_index))] = int(sid)
    return out


def _convert_split_by_part_setup(
    input_btlx: Path,
    output_ngc: Path,
    *,
    report_json: str | None,
    tools_json: str | None,
    machine_profile: str,
    no_toolchange: bool,
    local_origin: bool,
    split_testa_setups: bool,
) -> dict[str, Any]:
    """
    Generate one G-code per part/setup:
      <stem>_part<NNN>_setup<S>.ngc
    """
    parts = parse_btlx(input_btlx)
    setup_index = _build_part_setup_index(parts, split_testa_setups=split_testa_setups)

    # Optional setup report from same decision table.
    setup_report_payload = plan_to_json(build_setup_plan(parts, policy=SetupPolicy(split_testa_setups=split_testa_setups)))

    tree = ET.parse(input_btlx)
    root = tree.getroot()
    _, parts_el = _find_project_parts(root)
    if parts_el is None:
        raise ValueError("BTLx sin nodo Project/Parts")

    ns_uri = root.tag.split("}")[0][1:] if root.tag.startswith("{") and "}" in root.tag else ""
    total_converted = 0
    total_skipped = 0
    generated: list[dict[str, Any]] = []

    setup_ids = sorted({sid for sid in setup_index.values()})
    stem = output_ngc.stem
    out_dir = output_ngc.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="btlx_split_") as td:
        tmp_dir = Path(td)
        # Iterate original parts in XML order for deterministic outputs.
        for xml_part in list(parts_el):
            if _local(xml_part.tag) != "Part":
                continue
            part_number = str(xml_part.attrib.get("SingleMemberNumber", ""))
            proc_el = _find_processings(xml_part)
            if proc_el is None:
                continue
            all_ops = [ch for ch in list(proc_el)]
            if not all_ops:
                continue

            for sid in setup_ids:
                op_indices = [idx for idx, _op in enumerate(all_ops) if setup_index.get((part_number, idx)) == sid]
                if not op_indices:
                    continue

                # Fresh tree copy to keep namespaces/metadata intact.
                split_root = ET.fromstring(ET.tostring(root, encoding="utf-8"))
                _, split_parts = _find_project_parts(split_root)
                if split_parts is None:
                    continue

                # Keep only current part.
                target_part = None
                for p in list(split_parts):
                    if _local(p.tag) != "Part":
                        split_parts.remove(p)
                        continue
                    if str(p.attrib.get("SingleMemberNumber", "")) == part_number and target_part is None:
                        target_part = p
                    else:
                        split_parts.remove(p)
                if target_part is None:
                    continue

                # Keep only operations assigned to this setup.
                split_proc = _find_processings(target_part)
                if split_proc is None:
                    continue
                for idx, op_el in enumerate(list(split_proc)):
                    if idx not in op_indices:
                        split_proc.remove(op_el)

                if len(list(split_proc)) == 0:
                    continue

                tmp_btlx = tmp_dir / f"{stem}_part{part_number}_setup{sid}.btlx"
                ET.ElementTree(split_root).write(tmp_btlx, encoding="utf-8", xml_declaration=True)

                out_ngc = out_dir / f"{stem}_part{part_number}_setup{sid}.ngc"
                out_rep = out_dir / f"{stem}_part{part_number}_setup{sid}.report.json" if report_json else None
                rep = convert_file(
                    input_path=str(tmp_btlx),
                    output_path=str(out_ngc),
                    report_path=str(out_rep) if out_rep else None,
                    tools_json_path=tools_json,
                    machine_profile=machine_profile,
                    no_toolchange=no_toolchange,
                    local_origin=local_origin,
                )
                total_converted += int(rep.converted_ops)
                total_skipped += int(rep.skipped_ops)
                generated.append(
                    {
                        "part_number": part_number,
                        "setup": sid,
                        "ops": len(op_indices),
                        "output_ngc": str(out_ngc),
                        "report_json": str(out_rep) if out_rep else None,
                    }
                )

    return {
        "converted_ops": total_converted,
        "skipped_ops": total_skipped,
        "generated_files": generated,
        "setup_payload": setup_report_payload,
    }


def run_postprocessor(
    input_btlx: str,
    output_ngc: str,
    *,
    report_json: str | None = None,
    setup_json: str | None = None,
    tools_json: str | None = None,
    machine_profile: str = "elephant3spindle",
    no_toolchange: bool = False,
    local_origin: bool = False,
    split_testa_setups: bool = True,
    split_by_part_setup: bool = False,
) -> dict[str, Any]:
    """
    Convert BTLx to Mach3 G-code and optionally emit setup report.

    Returns a dict with paths and counters so Grasshopper can display status.
    """
    inp = Path(input_btlx)
    out = Path(output_ngc)

    if not inp.exists():
        raise FileNotFoundError(f"Input BTLx not found: {inp}")

    out.parent.mkdir(parents=True, exist_ok=True)

    if split_by_part_setup:
        split_res = _convert_split_by_part_setup(
            inp,
            out,
            report_json=report_json,
            tools_json=tools_json,
            machine_profile=machine_profile,
            no_toolchange=no_toolchange,
            local_origin=local_origin,
            split_testa_setups=split_testa_setups,
        )
        converted_ops = int(split_res["converted_ops"])
        skipped_ops = int(split_res["skipped_ops"])
        setup_payload = split_res["setup_payload"]
        generated_files = split_res["generated_files"]
    else:
        rep = convert_file(
            input_path=str(inp),
            output_path=str(out),
            report_path=report_json,
            tools_json_path=tools_json,
            machine_profile=machine_profile,
            no_toolchange=no_toolchange,
            local_origin=local_origin,
        )
        converted_ops = int(rep.converted_ops)
        skipped_ops = int(rep.skipped_ops)
        parts = parse_btlx(inp)
        policy = SetupPolicy(split_testa_setups=split_testa_setups)
        plan = build_setup_plan(parts, policy=policy)
        setup_payload = plan_to_json(plan)
        generated_files = []

    if setup_json:
        sp = Path(setup_json)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(setup_payload, indent=2), encoding="utf-8")

    return {
        "input": str(inp),
        "output_ngc": str(out),
        "report_json": report_json,
        "setup_json": setup_json,
        "converted_ops": converted_ops,
        "skipped_ops": skipped_ops,
        "machine_profile": machine_profile,
        "no_toolchange": no_toolchange,
        "local_origin": local_origin,
        "split_by_part_setup": split_by_part_setup,
        "generated_files": generated_files,
    }


def _build_cli() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="BTLx -> Mach3 postprocessor bridge")
    ap.add_argument("--input", required=True, help="Input BTLx file")
    ap.add_argument("--output", required=True, help="Output .ngc/.tap file")
    ap.add_argument("--report", help="Optional conversion report JSON")
    ap.add_argument("--setup-report", help="Optional setup-plan JSON")
    ap.add_argument("--tools", help="Optional tools JSON")
    ap.add_argument("--machine-profile", default="elephant3spindle", help="generic | elephant3spindle")
    ap.add_argument("--no-toolchange", action="store_true", help="Skip Tn M6 in output")
    ap.add_argument("--local-origin", action="store_true", help="Normalize XY per part")
    ap.add_argument("--single-testa-setup", action="store_true", help="Use one dedicated setup for both testas")
    ap.add_argument("--split-by-part-setup", action="store_true", help="Emit one .ngc per part/setup")
    return ap


if __name__ == "__main__":
    args = _build_cli().parse_args()
    res = run_postprocessor(
        input_btlx=args.input,
        output_ngc=args.output,
        report_json=args.report,
        setup_json=args.setup_report,
        tools_json=args.tools,
        machine_profile=args.machine_profile,
        no_toolchange=args.no_toolchange,
        local_origin=args.local_origin,
        split_testa_setups=not args.single_testa_setup,
        split_by_part_setup=args.split_by_part_setup,
    )
    print(json.dumps(res, indent=2))

