import json
import logging

def setup_logger(name, file_path, level=logging.DEBUG):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file = logging.FileHandler(file_path, encoding="utf-8")
    file.setFormatter(formatter)

    logger.addHandler(console)
    logger.addHandler(file)
    return logger

logger = None
_sys_log = setup_logger("lpat-sys-logger", "sys.log")

def sys_log():
    """Returns the system logger"""
    return _sys_log