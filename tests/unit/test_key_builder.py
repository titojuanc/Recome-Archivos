"""Unit tests para key_builder.construir_key (T005)."""

from src.worker.storage.key_builder import construir_key


def test_construir_key_formato_esperado():
    key = construir_key("anuncio-123", "solicitud-abc")
    assert key == "reportes/anuncio-123/solicitud-abc.xlsx"


def test_construir_key_es_deterministica():
    key1 = construir_key("anuncio-123", "solicitud-abc")
    key2 = construir_key("anuncio-123", "solicitud-abc")
    assert key1 == key2


def test_construir_key_estable_con_caracteres_especiales():
    key = construir_key("anuncio con espacios/raros#1", "solicitud-abc")
    assert key.startswith("reportes/")
    assert key.endswith("/solicitud-abc.xlsx")
    # No debe lanzar excepcion y debe producir siempre el mismo resultado
    assert key == construir_key("anuncio con espacios/raros#1", "solicitud-abc")
