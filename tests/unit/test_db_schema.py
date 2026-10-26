"""El worker crea solo sus tablas propias y nunca `anuncio` (dueño: api-general/Flyway)."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from src.worker.db_schema import asegurar_tablas_propias


def _engine():
    return create_engine("sqlite:///:memory:")


def test_crea_solo_las_tablas_propias_y_no_anuncio():
    engine = _engine()
    asegurar_tablas_propias(engine)
    tablas = set(inspect(engine).get_table_names())
    assert tablas == {"reporte_autorizacion", "registro_idempotencia"}
    assert "anuncio" not in tablas


def test_es_idempotente_y_no_borra_datos():
    engine = _engine()
    asegurar_tablas_propias(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO reporte_autorizacion "
                "(solicitud_id, anuncio_id, usuario_solicitante, bucket, key, creado_en) "
                "VALUES ('s1', 'a1', 'u@x', 'b', 'k', '2026-10-26')"
            )
        )
    asegurar_tablas_propias(engine)  # segunda corrida
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM reporte_autorizacion")).scalar() == 1


def test_no_toca_una_tabla_anuncio_preexistente():
    """Si api-general (Flyway) ya creó `anuncio`, no se modifica ni se recrea."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE anuncio (id TEXT PRIMARY KEY, extra_flyway TEXT)"))
    asegurar_tablas_propias(engine)
    columnas = {c["name"] for c in inspect(engine).get_columns("anuncio")}
    assert columnas == {"id", "extra_flyway"}
