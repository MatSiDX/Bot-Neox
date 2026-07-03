import logging
import os
from datetime import datetime


LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")


def configure_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s", "%d/%m/%Y %H:%M:%S")
    existing_files = {
        getattr(handler, "baseFilename", None)
        for handler in root_logger.handlers
    }
    if LOG_FILE not in existing_files:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def log_event(message):
    configure_logging()
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)
    logging.getLogger("bot").info(message)


def log_exception(message, exc=None):
    configure_logging()
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{timestamp}] ERROR {message}", flush=True)
    logger = logging.getLogger("bot")
    if exc is None:
        logger.exception(message)
        return
    logger.exception("%s | %s: %s", message, type(exc).__name__, exc)
