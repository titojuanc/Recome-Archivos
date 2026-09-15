"""Entry point del worker (placeholder de Fase 2; logica de negocio en fases
posteriores segun tasks.md)."""

from __future__ import annotations

import logging

from src.worker.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger("worker.main")


def main() -> None:
    config = Config.from_env()
    logger.info(
        "Iniciando worker de reportes (queue=%s, dead_letter=%s, max_concurrencia=%s)",
        config.queue_reporte_generar,
        config.dead_letter_exchange,
        config.max_concurrencia,
    )
    # El registro del consumer y el loop de consumo se conectan en la tarea T022/T024.
    raise NotImplementedError(
        "El loop de consumo se implementa en User Story 1 (T022-T024 de tasks.md)"
    )


if __name__ == "__main__":
    main()
