"""Unit tests para key_builder.construir_key (T005)."""

from src.worker.storage.key_builder import construir_key


def test_construir_key_formato_esperado():
    key = construir_key("solicitud-abc")
    assert key == "reportes/solicitud-abc.xlsx"


def test_construir_key_es_deterministica():
    key1 = construir_key("solicitud-abc")
    key2 = construir_key("solicitud-abc")
    assert key1 == key2


def test_construir_key_estable_con_caracteres_especiales():
    key = construir_key("solicitud con espacios/raros#1")
    assert key.startswith("reportes/")
    assert key.endswith(".xlsx")
    # No debe lanzar excepcion y debe producir siempre el mismo resultado
    assert key == construir_key("solicitud con espacios/raros#1")
