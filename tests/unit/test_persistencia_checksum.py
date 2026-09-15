"""Unit test para persistencia.calcular_checksum (T009)."""

import io

from src.worker.storage.persistencia import calcular_checksum


def test_calcular_checksum_es_consistente_y_reproducible():
    contenido = b"contenido de prueba del reporte excel"
    checksum1 = calcular_checksum(io.BytesIO(contenido))
    checksum2 = calcular_checksum(io.BytesIO(contenido))
    assert checksum1 == checksum2
    assert isinstance(checksum1, str)
    assert len(checksum1) > 0


def test_calcular_checksum_distinto_para_contenidos_distintos():
    checksum_a = calcular_checksum(io.BytesIO(b"contenido A"))
    checksum_b = calcular_checksum(io.BytesIO(b"contenido B"))
    assert checksum_a != checksum_b
