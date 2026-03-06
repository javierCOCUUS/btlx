# Grasshopper Quick Setup

## 1) Componente GhPython
Crea un componente GhPython y define estos **inputs**:
- `run` (bool)
- `btlx_path` (text)
- `output_ngc_path` (text)
- `repo_root` (text, opcional)
- `report_json_path` (text, opcional)
- `setup_json_path` (text, opcional)
- `tools_json_path` (text, opcional)
- `no_toolchange` (bool)
- `local_origin` (bool)
- `split_testa_setups` (bool)
- `split_by_part_setup` (bool)
- `strict_tool_map` (bool)

Define estos **outputs**:
- `ok`
- `message`
- `result_json`

## 2) Copiar script
Pega el contenido de:
- `converter/ghpython_component.py`

en el editor del componente GhPython.

## 3) Valores recomendados (primera prueba)
- `run`: `False` (hasta revisar rutas)
- `btlx_path`: `c:\demo pista\btlx\converter\grasshopper_btlx\btlx2.btlx`
- `output_ngc_path`: `c:\demo pista\btlx\out\gh_btlx2.ngc`
- `repo_root`: `c:\demo pista\btlx`
- `report_json_path`: `c:\demo pista\btlx\out\gh_btlx2.report.json`
- `setup_json_path`: `c:\demo pista\btlx\out\gh_btlx2.setup.json`
- `tools_json_path`: (vacío o ruta a tu json de herramientas)
- `no_toolchange`: `False` (en tu máquina, Tn M6 está bien)
- `local_origin`: `False`
- `split_testa_setups`: `True`
- `split_by_part_setup`: `False` (pon `True` para sacar un .ngc por viga+setup)
- `strict_tool_map`: `True` (recomendado: falla si hay operación sin mapeo T1/T2/T3)

Notas:
- Si conectas `tools_json_path` con tu `tools.json` de Fusion, el post usa RPM, feed, plunge, ramp feed, rampa y pasos de mecanizado cuando estén definidos.
- El post valida limites de máquina (X=1300, Y=2500) y falla si una pieza no cabe.

## 4) Ejecutar
- Cambia `run` a `True`.
- Si todo va bien:
  - `ok = True`
  - `message = OK`
  - tendrás `.ngc` + `.report.json` + `.setup.json` en `out`.

## 5) Nota sobre compartir con ETH
No hace falta hardcodear tu ruta si todos clonan el repo y ponen su `repo_root` local.
