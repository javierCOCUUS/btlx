from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .post import convert_file


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Convert BTLx to Mach3 G-code (MVP)")
    p.add_argument("--input", required=True, help="Input .btlx file")
    p.add_argument("--output", required=True, help="Output .ngc/.tap file")
    p.add_argument("--report", required=False, help="Optional JSON report path")
    p.add_argument("--tools-json", required=False, help="Tool database JSON (supports fusion_import.json)")
    p.add_argument("--machine-profile", required=False, default="generic", choices=["generic", "elephant3spindle"], help="Output profile")
    p.add_argument("--no-toolchange", action="store_true", help="Do not output Tn M6 sequence")
    p.add_argument("--local-origin", action="store_true", help="Normalize each part XY to local origin (first XY move becomes X0 Y0)")
    return p


def main() -> int:
    args = build_parser().parse_args()
    report = convert_file(
        args.input,
        args.output,
        args.report,
        args.tools_json,
        args.machine_profile,
        args.no_toolchange,
        args.local_origin,
    )
    print(json.dumps(asdict(report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
