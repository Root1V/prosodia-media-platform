"""Configuracion compartida por toda la suite.

Se carga antes que cualquier conftest de subdirectorio, que es lo que hace
falta aqui: `tests/unit/web/conftest.py` importa la app de FastAPI, y
`web/main.py` llama a `argus.init()` al importarse (tiene que ser antes de los
routers). O sea que el solo hecho de recoger los tests de la web arrancaba
telemetria de verdad.

Y arrancaba exportando: si no hay OTEL_EXPORTER_OTLP_ENDPOINT, el SDK no se
queda callado, cae a `http://localhost:4318` -- el agente local. Con eso, cada
`configure_logging()` de cada test construia el puente de exportacion y
mandaba sus registros al almacen compartido de Argus, sin nombre de servicio
(salian como "unknown-service") y con rutas de ficheros temporales de pytest
dentro. Se midieron 1346 registros entre el 25 y el 30 de septiembre antes de
verlo.

`setdefault` y no asignacion directa: asi se puede forzar lo contrario desde
fuera (`ARGUS_DISABLED=0 pytest ...`) si alguna vez hay que depurar la
instrumentacion con un colector de pruebas.
"""

from __future__ import annotations

import os

os.environ.setdefault("ARGUS_DISABLED", "1")
