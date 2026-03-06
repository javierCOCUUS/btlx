# Setup Rules (BTLx -> CNC 3 ejes)

## Objetivo
Definir de forma explicita como se decide el setup de cada operacion BTLx para evitar decisiones ambiguas.

## Setups base
- Setup 1: caras 2, 4, 6 (top + testas cuando proceda)
- Setup 2: cara 1 (volteo 180 sobre eje longitudinal)
- Setup 3: cara 3 (volteo 90)
- Setup 4: cara 5 (volteo 270)
- Setup 5: dedicado testa cara 4
- Setup 6: dedicado testa cara 6

## Regla general
- Si la operacion tiene cara 1,2,3,5: se usa `FACE_DEFAULT_SETUP`.
- Si la operacion no tiene cara: fallback setup 1 y queda marcada como unresolved.

## Regla de testas (caras 4 y 6)
Las testas se deciden por tipo de operacion + complejidad angular.

### Tipos de corte (cut-like)
- JackRafterCut
- DoubleCut
- CutOff
- LongitudinalCut
- RidgeValleyCut
- SimpleScarf
- ScarfJoint
- StepJoint
- StepJointNotch
- BirdsMouth

Decision:
- Si Angle e Inclination estan cerca de 90 (+/-2): setup 1
- Si no: setup dedicado (5 para cara 4, 6 para cara 6)

### Tipos de rebaje/cajeado/contorno (pocket-like)
- Lap
- Mortise
- HouseMortise
- House
- DovetailMortise
- DovetailTenon
- Dovetail
- TyroleanDovetail
- Tenon
- Slot
- FreeContour
- ProfileHead
- ProfileCambered
- Planing
- Drilling
- NailContour
- Marking
- Text

Decision:
- Siempre setup dedicado de testa (5 o 6)

### Tipos desconocidos en testa
- Por defecto: setup dedicado (5 o 6)
- Opcion CLI para forzar fallback setup 1: `--unknown-testa-to-setup1`

## Overrides manuales
Se permite override por operacion (GUID) para casos especiales de produccion.

## Reportabilidad
`setups.py` imprime:
- resumen por setup (parts, faces, types)
- detalle por operacion con motivo (`--detailed`)
- salida JSON (`--json-out`)

Esto permite validar con ejemplos reales antes de postprocesar a G-code.
