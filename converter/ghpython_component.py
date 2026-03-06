"""
GhPython component script (ready to paste)
-----------------------------------------
Inputs expected in Grasshopper:
- run (bool)
- btlx_path (str)
- output_ngc_path (str)
- repo_root (str, optional)
- report_json_path (str, optional)
- setup_json_path (str, optional)
- tools_json_path (str, optional)
- no_toolchange (bool)
- local_origin (bool)
- split_testa_setups (bool)

Outputs:
- ok (bool)
- message (str)
- result_json (str)
"""

import json
import os
import sys

ok = False
message = "Idle"
result_json = ""


def _guess_repo_root(input_btlx):
    # Try from btlx path: .../btlx/converter/grasshopper_btlx/file.btlx
    p = os.path.abspath(input_btlx)
    cur = os.path.dirname(p)
    for _ in range(8):
        converter_dir = os.path.join(cur, "converter")
        src_dir = os.path.join(cur, "src")
        if os.path.isdir(converter_dir) and os.path.isdir(src_dir):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return ""


if run:
    try:
        if not btlx_path:
            raise Exception("btlx_path vacio")
        if not output_ngc_path:
            raise Exception("output_ngc_path vacio")

        root = (repo_root or "").strip()
        if not root:
            root = _guess_repo_root(btlx_path)

        if not root:
            raise Exception("No se pudo resolver repo_root. Conecta un Panel con la ruta del repo (ej: c:\\demo pista\\btlx)")

        converter_dir = os.path.join(root, "converter")
        if converter_dir not in sys.path:
            sys.path.insert(0, converter_dir)

        from postprocessor import run_postprocessor

        setup_flag = True if split_testa_setups is None else bool(split_testa_setups)

        result = run_postprocessor(
            input_btlx=btlx_path,
            output_ngc=output_ngc_path,
            report_json=report_json_path if report_json_path else None,
            setup_json=setup_json_path if setup_json_path else None,
            tools_json=tools_json_path if tools_json_path else None,
            machine_profile="elephant3spindle",
            no_toolchange=bool(no_toolchange),
            local_origin=bool(local_origin),
            split_testa_setups=setup_flag,
        )

        ok = True
        message = "OK"
        result_json = json.dumps(result, indent=2)

    except Exception as e:
        ok = False
        message = str(e)
        result_json = ""
