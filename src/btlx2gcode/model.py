from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Operation:
    kind: str
    name: str
    reference_plane_id: int | None
    params: Dict[str, object] = field(default_factory=dict)


@dataclass
class Part:
    part_id: str
    length: float
    width: float
    height: float
    operations: List[Operation] = field(default_factory=list)
    reference_planes: Dict[int, Dict[str, tuple[float, float, float]]] = field(default_factory=dict)


@dataclass
class BTLXProgram:
    source_path: str
    version: str
    parts: List[Part]


@dataclass
class ConversionReport:
    source_path: str
    output_path: str
    converted_ops: int = 0
    skipped_ops: int = 0
    skipped_by_kind: Dict[str, int] = field(default_factory=dict)
