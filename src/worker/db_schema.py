"""Crea, al arrancar el worker, las tablas PROPIAS de este repo.

Solo `reporte_autorizacion` y `registro_idempotencia`. La tabla `anuncio` es compartida y
su dueño es recome-api-general (migración Flyway): NUNCA se crea desde acá. Si
`create_all` la creara antes de que corra Flyway, quedaría con un esquema distinto y
Flyway fallaría después (ver docs/CONTRATO_TABLA_ANUNCIO.md en api-general).

Por eso se pasa `tables=[...]` explícito en vez de `Base.metadata.create_all(engine)`.
`create_all` usa `checkfirst=True`: es idempotente y no toca tablas que ya existen.
"""

from __future__ import annotations

import logging

from sqlalchemy.engine import Engine

from src.models.anuncio import Base
from src.models.autorizacion import ReporteAutorizacion
from src.models.idempotencia import RegistroDeIdempotencia

logger = logging.getLogger("worker.db_schema")

TABLAS_PROPIAS = [
    ReporteAutorizacion.__table__,
    RegistroDeIdempotencia.__table__,
]


def asegurar_tablas_propias(engine: Engine) -> None:
    """Crea las tablas propias si faltan. No modifica tablas existentes ni toca `anuncio`."""
    Base.metadata.create_all(engine, tables=TABLAS_PROPIAS)
    logger.info("Tablas propias verificadas: %s", ", ".join(t.name for t in TABLAS_PROPIAS))
