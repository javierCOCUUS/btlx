"""
GhPython wrapper template for converter/postprocessor.py

Inputs expected in Grasshopper component:
- btlx_path (str)
- output_ngc_path (str)
- report_json_path (str, optional)
- setup_json_path (str, optional)
- tools_json_path (str, optional)
- no_toolchange (bool)
- local_origin (bool)
- split_by_part_setup (bool)
- strict_tool_map (bool)
- db_tool_drill (int, optional)
- db_tool_rough (int, optional)
- db_tool_finish (int, optional)
- run (bool)

Outputs:
- ok (bool)
- message (str)
- result (dict/json string)
"""

import json
import os
import sys

ok = False
message = "Idle"
result = None

if run:
    try:
        # Resolve repo root from this file location or set manually.
        # Option A: hardcode your repo path in GH panel and replace ROOT below.
        ROOT = r"c:\demo pista\btlx"
        CONVERTER = os.path.join(ROOT, "converter")

        if CONVERTER not in sys.path:
            sys.path.insert(0, CONVERTER)

        from postprocessor import run_postprocessor

        res = run_postprocessor(
            input_btlx=btlx_path,
            output_ngc=output_ngc_path,
            report_json=report_json_path if report_json_path else None,
            setup_json=setup_json_path if setup_json_path else None,
            tools_json=tools_json_path if tools_json_path else None,
            machine_profile="elephant3spindle",
            no_toolchange=bool(no_toolchange),
            local_origin=bool(local_origin),
            split_testa_setups=True,
            split_by_part_setup=bool(split_by_part_setup),
            strict_tool_map=bool(strict_tool_map) if strict_tool_map is not None else True,
            db_tool_drill=int(db_tool_drill) if db_tool_drill not in (None, "") else None,
            db_tool_rough=int(db_tool_rough) if db_tool_rough not in (None, "") else None,
            db_tool_finish=int(db_tool_finish) if db_tool_finish not in (None, "") else None,
        )
        ok = True
        message = "OK"
        result = json.dumps(res, indent=2)

    except Exception as e:
        ok = False
        message = str(e)
        result = None
