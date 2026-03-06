from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .model import BTLXProgram, Operation, Part


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _as_number_or_text(value: str):
    v = value.strip()
    low = v.lower()
    if low == "yes":
        return True
    if low == "no":
        return False
    try:
        return float(v)
    except ValueError:
        return v


def _extract_params(op_el: ET.Element) -> dict:
    params: dict = {}
    for child in list(op_el):
        key = _local(child.tag)
        if list(child):
            continue
        txt = (child.text or "").strip()
        if txt:
            params[key] = _as_number_or_text(txt)
    for k, v in op_el.attrib.items():
        params[k] = _as_number_or_text(v)
    return params


def _point_from_attrs(el: ET.Element | None) -> tuple[float, float, float] | None:
    if el is None:
        return None
    try:
        x = float(el.attrib.get("X", 0.0) or 0.0)
        y = float(el.attrib.get("Y", 0.0) or 0.0)
        z = float(el.attrib.get("Z", 0.0) or 0.0)
    except Exception:
        return None
    return (x, y, z)


def _extract_contour_geometry(op_el: ET.Element) -> dict[str, object]:
    out: dict[str, object] = {}
    contour_el = None
    for ch in list(op_el):
        if _local(ch.tag) == "Contour":
            contour_el = ch
            break
    if contour_el is None:
        return out

    start = None
    for ch in list(contour_el):
        if _local(ch.tag) == "StartPoint":
            start = _point_from_attrs(ch)
            break
    if start is not None:
        out["__contour_start"] = start

    segments: list[dict[str, object]] = []
    for ch in list(contour_el):
        tag = _local(ch.tag)
        if tag == "StartPoint":
            continue
        if tag == "Line":
            end = None
            for c2 in list(ch):
                if _local(c2.tag) == "EndPoint":
                    end = _point_from_attrs(c2)
                    break
            if end is not None:
                segments.append({"type": "line", "end": end})
            continue
        if tag == "Arc":
            end = None
            mid = None
            for c2 in list(ch):
                t2 = _local(c2.tag)
                if t2 == "EndPoint":
                    end = _point_from_attrs(c2)
                elif t2 == "PointOnArc":
                    mid = _point_from_attrs(c2)
            if end is not None and mid is not None:
                segments.append({"type": "arc", "end": end, "mid": mid})
            continue

    if segments:
        out["__contour_segments"] = segments
    return out


def _extract_reference_planes(part_el: ET.Element) -> dict[int, dict[str, tuple[float, float, float]]]:
    planes: dict[int, dict[str, tuple[float, float, float]]] = {}

    urp_root = None
    for ch in list(part_el):
        if _local(ch.tag) == "UserReferencePlanes":
            urp_root = ch
            break
    if urp_root is None:
        return planes

    for urp in list(urp_root):
        if _local(urp.tag) != "UserReferencePlane":
            continue
        id_raw = urp.attrib.get("ID")
        if not id_raw or not str(id_raw).isdigit():
            continue
        pid = int(id_raw)
        pos = None
        for ch in list(urp):
            if _local(ch.tag) == "Position":
                pos = ch
                break
        if pos is None:
            continue

        ref = xvec = yvec = None
        for ch in list(pos):
            tag = _local(ch.tag)
            if tag == "ReferencePoint":
                ref = _point_from_attrs(ch)
            elif tag == "XVector":
                xvec = _point_from_attrs(ch)
            elif tag == "YVector":
                yvec = _point_from_attrs(ch)
        if ref is None or xvec is None or yvec is None:
            continue
        planes[pid] = {"origin": ref, "xvec": xvec, "yvec": yvec}

    return planes


def parse_btlx(path: str | Path) -> BTLXProgram:
    p = Path(path)
    tree = ET.parse(p)
    root = tree.getroot()

    version = root.attrib.get("Version", "unknown")
    parts: list[Part] = []

    for part_el in root.iter():
        if _local(part_el.tag) != "Part":
            continue

        part_id = str(part_el.attrib.get("SingleMemberNumber", "part"))
        length = float(part_el.attrib.get("Length", 0.0) or 0.0)
        width = float(part_el.attrib.get("Width", 0.0) or 0.0)
        height = float(part_el.attrib.get("Height", 0.0) or 0.0)
        part = Part(part_id=part_id, length=length, width=width, height=height)
        part.reference_planes = _extract_reference_planes(part_el)

        proc_node = None
        for ch in list(part_el):
            if _local(ch.tag) == "Processings":
                proc_node = ch
                break

        if proc_node is not None:
            for op_el in proc_node.iter():
                kind = _local(op_el.tag)
                if kind == "Processings":
                    continue
                # Keep only real processing nodes. This filters out nested
                # parameter tags like StartX, Angle, EndPoint, etc.
                if "Process" not in op_el.attrib and "ReferencePlaneID" not in op_el.attrib:
                    continue
                name = str(op_el.attrib.get("Name", kind))
                ref_id_raw = op_el.attrib.get("ReferencePlaneID")
                ref_id = int(ref_id_raw) if ref_id_raw and str(ref_id_raw).isdigit() else None
                part.operations.append(
                    Operation(
                        kind=kind,
                        name=name,
                        reference_plane_id=ref_id,
                        params={**_extract_params(op_el), **_extract_contour_geometry(op_el)},
                    )
                )

        parts.append(part)

    return BTLXProgram(source_path=str(p), version=version, parts=parts)
