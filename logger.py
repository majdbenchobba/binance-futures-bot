import logging
import os
from config import LOG_FILE


def setup_logger():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
