"""Centralised logging configuration.

Call `configure_logging(component)` once at process startup.
Writes log files to ``logs/`` at the project root:
  - logs/api.log        — FastAPI / upload requests
  - logs/ingestion.log  — Celery ingestion pipeline
"""

import logging
import logging.handlers
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOGS_DIR = os.path.join(_ROOT, "logs")


def configure_logging(component: str = "api") -> None:
    os.makedirs(_LOGS_DIR, exist_ok=True)

    log_file = os.path.join(_LOGS_DIR, f"{component}.log")

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s [%(funcName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # On Windows, RotatingFileHandler fails to rename open files when uvicorn's
    # reloader subprocess holds a handle.  Plain FileHandler avoids this entirely.
    # Use rotation only on non-Windows (Linux/Mac in production).
    if sys.platform == "win32":
        file_handler = logging.FileHandler(log_file, encoding="utf-8", delay=True)
    else:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if configure_logging is called more than once
    file_handler_types = (logging.FileHandler, logging.handlers.RotatingFileHandler)
    if not any(isinstance(h, file_handler_types) for h in root.handlers):
        root.addHandler(file_handler)
    if not any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, file_handler_types)
        for h in root.handlers
    ):
        root.addHandler(console_handler)

    for noisy in ("sqlalchemy.engine", "urllib3", "httpx", "httpcore", "botocore", "boto3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Logging configured — writing to %s", log_file)
