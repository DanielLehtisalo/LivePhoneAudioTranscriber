import json
import logging

def setup_logger(name, file_name, level=logging.DEBUG):
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

    file = logging.FileHandler(file_name, encoding="utf-8")
    file.setFormatter(formatter)

    logger.addHandler(console)
    logger.addHandler(file)
    return logger

logger = None
_sys_log = setup_logger("lpat-sys-logger", "sys.log")


def start_logging(session, dir):
    global logger
    if logger is not None:
        _sys_log.warning("Tried to start another session with old session running.")
        return
    _sys_log.info(f"Starting logging.")
    logger = setup_logger(str(session), dir / "session.log", logging.INFO)
    logger.info("==Start of log==")
    return logger

def end_logging():
    global logger
    _sys_log.info("Ending logging.")
    logger.info("==End of log==")
    logger = None

def sys_log():
    return _sys_log