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

    rep = convert_file(
        input_path=str(inp),
        output_path=str(out),
        report_path=report_json,
        tools_json_path=tools_json,
        machine_profile=machine_profile,
        no_toolchange=no_toolchange,
        local_origin=local_origin,
    )

    if setup_json:
        parts = parse_btlx(inp)
        policy = SetupPolicy(split_testa_setups=split_testa_setups)
        plan = build_setup_plan(parts, policy=policy)
        setup_payload = plan_to_json(plan)
        sp = Path(setup_json)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(setup_payload, indent=2), encoding="utf-8")

    return {
        "input": str(inp),
        "output_ngc": str(out),
        "report_json": report_json,
        "setup_json": setup_json,
        "converted_ops": rep.converted_ops,
        "skipped_ops": rep.skipped_ops,
        "machine_profile": machine_profile,
        "no_toolchange": no_toolchange,
        "local_origin": local_origin,
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
    )
    print(json.dumps(res, indent=2))

