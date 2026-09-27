import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """
    Retorna um logger configurado com formato estruturado para o módulo especificado.

    Formato: timestamp | LEVEL | module.name | mensagem
    Nível padrão: INFO (configurável via variável de ambiente LOG_LEVEL).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        import os
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))

    return logger
