"""
faces.py â€” Transformaciones de coordenadas BTLx â†’ mÃ¡quina para cada cara.

â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
MAPEO DE EJES â€” Esta mÃ¡quina especÃ­fica
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    MÃ¡quina:                    Recorrido:
      X  â†’  transversal          1300 mm
      Y  â†’  longitudinal         2500 mm  (a lo largo de la viga)
      Z  â†’  vertical (husillo)

    Origen de pieza:
      Y=0  â†’  testa de inicio de la viga
      X=0  â†’  borde frontal de la pieza (lado operario)
      Z=0  â†’  superficie activa (cara que mira al husillo)
      Z negativo â†’ hacia adentro de la pieza

BTLx â†’ MÃ¡quina:
      BTLx Length  (longitudinal)  â†’  Y mÃ¡quina
      BTLx Width   (transversal)   â†’  X mÃ¡quina
      BTLx Height  (vertical)      â†’  Z mÃ¡quina

â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
SISTEMA DE CARAS BTLx
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    Cara 1  Bottom (Zâˆ’)      â†’  volteo 180Â° sobre eje longitudinal Y
    Cara 2  Top    (Z+)      â†’  sin volteo, cara principal
    Cara 3  Front  (Widthâˆ’)  â†’  volteo 90Â°  sobre eje longitudinal Y
    Cara 4  Testa inicio     â†’  sin volteo, fresa baja en Z sobre Y=0
    Cara 5  Back   (Width+)  â†’  volteo 270Â° sobre eje longitudinal Y
    Cara 6  Testa fin        â†’  sin volteo, fresa baja en Z sobre Y=Length

Coordenadas locales BTLx por cara (u, v):
    u  â†’  siempre la direcciÃ³n longitudinal de la pieza (Length)
    v  â†’  direcciÃ³n transversal o de altura segÃºn la cara
    depth â†’ profundidad hacia el interior

â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
NOTA SOBRE ESPEJOS
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    Las caras opuestas (1â†”2, 3â†”5, 4â†”6) tienen el eje v espejado
    en BTLx para que siempre "mires hacia adentro".
    Cada funciÃ³n de transformaciÃ³n deshace ese espejo.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ConfiguraciÃ³n de la mÃ¡quina
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class MachineConfig:
    """LÃ­mites fÃ­sicos de la mÃ¡quina en mm."""
    x_max: float = 1300.0
    y_max: float = 2500.0
    z_max: float = 200.0
    z_min: float = -200.0
    safe_z: float = 50.0

MACHINE = MachineConfig()


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Tipos
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class PartGeometry:
    """
    Dimensiones de la pieza en mm, en coordenadas BTLx.
      length â†’ eje longitudinal â†’ Y mÃ¡quina
      width  â†’ eje transversal  â†’ X mÃ¡quina
      height â†’ eje vertical     â†’ Z mÃ¡quina
    """
    length: float
    width:  float
    height: float


@dataclass
class MachinePoint:
    """
    Punto en coordenadas de mÃ¡quina.
      x, y   â†’ posiciÃ³n en el plano de trabajo
      z      â†’ 0.0 en la superficie activa de la pieza
      feed_z â†’ profundidad final (siempre <= 0)
    """
    x:        float
    y:        float
    z:        float
    feed_z:   float
    warnings: list = field(default_factory=list)

    def is_valid(self, machine: MachineConfig = MACHINE) -> bool:
        return (
            0 <= self.x <= machine.x_max and
            0 <= self.y <= machine.y_max and
            self.feed_z >= machine.z_min
        )


FaceNumber = Literal[1, 2, 3, 4, 5, 6]


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Metadatos de cada cara
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

FACE_DESCRIPTIONS = {
    1: "Bottom (Z-)      â€” cara inferior, volteo 180 sobre eje longitudinal (Y)",
    2: "Top    (Z+)      â€” cara superior, sin volteo (cara principal)",
    3: "Front  (Width-)  â€” lateral frontal, volteo 90 sobre eje longitudinal (Y)",
    4: "Testa inicio     â€” Y=0, fresa baja en Z desde arriba, sin volteo",
    5: "Back   (Width+)  â€” lateral trasero, volteo 270 sobre eje longitudinal (Y)",
    6: "Testa fin        â€” Y=Length, fresa baja en Z desde arriba, sin volteo",
}

FACE_FLIP_INSTRUCTION = {
    1: "Volteo 180 sobre el eje longitudinal de la viga (Y maquina)",
    2: None,
    3: "Volteo 90 sobre el eje longitudinal de la viga (Y maquina)",
    4: None,
    5: "Volteo 270 sobre el eje longitudinal de la viga (Y maquina)",
    6: None,
}

# Setup 1: caras 2, 4, 6  (sin volteo)
# Setup 2: cara 1         (volteo 180)
# Setup 3: cara 3         (volteo 90)
# Setup 4: cara 5         (volteo 270)
FACE_DEFAULT_SETUP = {2: 1, 4: 1, 6: 1, 1: 2, 3: 3, 5: 4}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Transformaciones por cara
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def face_2_to_machine(u: float, v: float, depth: float, geo: PartGeometry) -> MachinePoint:
    """
    Cara 2 â€” Top (Z+). Sin volteo. Cara principal.

    BTLx:  u â†’ longitudinal desde testa inicio     â†’ Y maquina
           v â†’ desde borde Width+ hacia Width-      â†’ X maquina = Width - v
                (v=0 esta en el borde mas alejado del operario)
    """
    y = u
    x = geo.width - v       # desespejo: v=0 en BTLx = X maximo en maquina
    z = 0.0
    feed_z = -depth
    pt = MachinePoint(x, y, z, feed_z)
    _check_limits(pt, "Cara 2", geo)
    return pt


def face_1_to_machine(u: float, v: float, depth: float, geo: PartGeometry) -> MachinePoint:
    """
    Cara 1 â€” Bottom (Z-). Volteo 180 sobre Y.
    Tras el volteo la cara inferior queda mirando al husillo.

    BTLx:  u â†’ longitudinal                        â†’ Y maquina
           v â†’ desde borde Width- hacia Width+
    Tras volteo 180: Width- queda en X=0, Width+ en X=Width.
           â†’ X maquina = v
    """
    y = u
    x = v
    z = 0.0
    feed_z = -depth
    pt = MachinePoint(x, y, z, feed_z)
    _check_limits(pt, "Cara 1", geo)
    return pt


def face_3_to_machine(u: float, v: float, depth: float, geo: PartGeometry) -> MachinePoint:
    """
    Cara 3 â€” Front/Width- (lateral frontal). Volteo 90 sobre Y.
    Tras el volteo el lateral queda mirando al husillo.

    BTLx:  u â†’ longitudinal                        â†’ Y maquina
           v â†’ desde Z- (bottom) hacia Z+ (top)
    Tras volteo 90: la altura de la pieza se despliega en X.
           â†’ X maquina = v
    """
    y = u
    x = v
    z = 0.0
    feed_z = -depth         # depth maximo = Width de la pieza
    pt = MachinePoint(x, y, z, feed_z)
    _check_limits(pt, "Cara 3", geo)
    return pt


def face_5_to_machine(u: float, v: float, depth: float, geo: PartGeometry) -> MachinePoint:
    """
    Cara 5 â€” Back/Width+ (lateral trasero). Volteo 270 sobre Y.
    Tras el volteo el lateral trasero queda mirando al husillo.

    BTLx:  u â†’ longitudinal                        â†’ Y maquina
           v â†’ desde Z+ (top) hacia Z- (bottom)   <- espejado respecto a cara 3
    Tras volteo 270: desespejamos v.
           â†’ X maquina = Height - v
    """
    y = u
    x = geo.height - v
    z = 0.0
    feed_z = -depth
    pt = MachinePoint(x, y, z, feed_z)
    _check_limits(pt, "Cara 5", geo)
    return pt


def face_4_to_machine(u: float, v: float, depth: float, geo: PartGeometry) -> MachinePoint:
    """
    Cara 4 â€” Testa inicio (Y=0). Sin volteo.
    La fresa baja en Z sobre el canto de la testa, en Y=0.

    BTLx:  u â†’ ancho de la seccion (Width)         â†’ X maquina
           v â†’ alto de la seccion  (Height)        â†’ (define donde en Z)
           depth â†’ penetracion dentro de la viga   â†’ en direccion Y+

    Nota: la profundidad aqui es en Y, no en Z.
          feed_z representa esa penetracion en Y+.
          El postprocessor lo trata como G1 Y+depth en lugar de G1 Z-depth.
    """
    y = 0.0
    x = u
    z = 0.0
    feed_z = -depth         # penetracion en Y+ (postprocessor lo interpreta por face=4)
    pt = MachinePoint(x, y, z, feed_z)
    _check_limits(pt, "Cara 4", geo)
    return pt


def face_6_to_machine(u: float, v: float, depth: float, geo: PartGeometry) -> MachinePoint:
    """
    Cara 6 â€” Testa fin (Y=Length). Sin volteo.
    La fresa baja en Z sobre el canto de la testa final.

    BTLx:  u â†’ ancho desde Width+ hacia Width-     <- espejado respecto a cara 4
           v â†’ alto de la seccion
           depth â†’ penetracion en Y-

    â†’ X maquina = Width - u  (desespejo)
    â†’ Y maquina = Length
    """
    y = geo.length
    x = geo.width - u       # desespejo
    z = 0.0
    feed_z = -depth         # penetracion en Y- (postprocessor lo interpreta por face=6)
    pt = MachinePoint(x, y, z, feed_z)
    _check_limits(pt, "Cara 6", geo)
    return pt


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Validacion de limites
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _check_limits(pt: MachinePoint, label: str, geo: PartGeometry,
                  machine: MachineConfig = MACHINE) -> None:
    if pt.x < 0 or pt.x > machine.x_max:
        pt.warnings.append(
            f"AVISO {label}: X={pt.x:.1f} fuera de rango [0, {machine.x_max}]"
        )
    if pt.y < 0 or pt.y > machine.y_max:
        pt.warnings.append(
            f"AVISO {label}: Y={pt.y:.1f} fuera de rango [0, {machine.y_max}]"
        )
    if pt.feed_z < machine.z_min:
        pt.warnings.append(
            f"AVISO {label}: feed_z={pt.feed_z:.1f} supera Z minimo [{machine.z_min}]"
        )
    if geo.length > machine.y_max:
        pt.warnings.append(
            f"AVISO {label}: pieza L={geo.length} supera recorrido Y ({machine.y_max})"
        )
    if geo.width > machine.x_max:
        pt.warnings.append(
            f"AVISO {label}: pieza W={geo.width} supera recorrido X ({machine.x_max})"
        )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Interfaz publica
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_FACE_TRANSFORMS = {
    1: face_1_to_machine,
    2: face_2_to_machine,
    3: face_3_to_machine,
    4: face_4_to_machine,
    5: face_5_to_machine,
    6: face_6_to_machine,
}


def transform(face: int, u: float, v: float, depth: float,
              geo: PartGeometry, machine: MachineConfig = MACHINE) -> MachinePoint:
    """
    Transforma coordenadas BTLx (u, v, depth) de una cara
    a coordenadas de maquina (X, Y, Z, feed_z).

    Args:
        face:    numero de cara BTLx (1-6)
        u:       coordenada longitudinal local
        v:       coordenada transversal local
        depth:   profundidad de la operacion (mm, positivo)
        geo:     dimensiones de la pieza
        machine: configuracion de la maquina

    Returns:
        MachinePoint con warnings si hay problemas de limites

    Raises:
        ValueError: si face no esta entre 1 y 6
    """
    fn = _FACE_TRANSFORMS.get(face)
    if fn is None:
        raise ValueError(f"Cara {face} no valida. Debe ser 1-6.")
    return fn(u, v, depth, geo)


def face_info(face: int) -> dict:
    return {
        "face":          face,
        "description":   FACE_DESCRIPTIONS.get(face, "Desconocida"),
        "flip":          FACE_FLIP_INSTRUCTION.get(face),
        "default_setup": FACE_DEFAULT_SETUP.get(face),
    }


def needs_flip(face: int) -> bool:
    return FACE_FLIP_INSTRUCTION.get(face) is not None


def flip_instruction(face: int) -> Optional[str]:
    return FACE_FLIP_INSTRUCTION.get(face)


def default_setup(face: int) -> int:
    return FACE_DEFAULT_SETUP.get(face, 1)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Test
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if __name__ == "__main__":
    geo = PartGeometry(length=2000, width=200, height=100)

    print("=" * 60)
    print(f"Pieza: L={geo.length} W={geo.width} H={geo.height} mm")
    print(f"Maquina: X<={MACHINE.x_max}  Y<={MACHINE.y_max}  Zsafe={MACHINE.safe_z}")
    print("Ejes: Y=longitudinal (viga), X=transversal")
    print("=" * 60)

    test_cases = [
        # (cara,  u,     v,    depth,  descripcion)
        (2,   500,   100,    50,  "Taladro Ã˜16 en cara top"),
        (2,   900,     0,    50,  "Esquina entalladura cara top"),
        (1,   300,   100,    30,  "Taladro Ã˜10 en cara bottom"),
        (3,  1000,    50,    60,  "Taladro Ã˜12 en lateral front"),
        (5,   800,    30,    40,  "Taladro en lateral back"),
        (4,   100,    50,    80,  "Penetracion en testa inicio"),
        (6,   100,    50,    80,  "Penetracion en testa fin"),
    ]

    setup_names = {
        1: "Setup 1 (sin volteo)",
        2: "Setup 2 (volteo 180)",
        3: "Setup 3 (volteo 90)",
        4: "Setup 4 (volteo 270)",
    }

    for face, u, v, depth, desc in test_cases:
        pt = transform(face, u, v, depth, geo)
        s = default_setup(face)
        flip = flip_instruction(face)
        flip_str = flip if flip else "sin volteo"
        print(f"\n  [{desc}]")
        print(f"  Cara {face} | BTLx u={u} v={v} depth={depth}")
        print(f"  -> X={pt.x:7.1f}  Y={pt.y:7.1f}  Z={pt.z:.1f}  feed_z={pt.feed_z:.1f}")
        print(f"  -> {setup_names[s]} â€” {flip_str}")
        for w in pt.warnings:
            print(f"  {w}")

