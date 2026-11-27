import logging

def setup_logger(name, file_path, level=logging.DEBUG, console_log=False):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if console_log:
        console = logging.StreamHandler()
        console.setFormatter(formatter)

        logger.addHandler(console)

    file = logging.FileHandler(file_path, encoding="utf-8")
    file.setFormatter(formatter)

    logger.addHandler(file)
    return logger

_sys_log = setup_logger("lpat-sys-logger", "sys.log",console_log=True)

def sys_log():
    """Returns the system logger"""
    return _sys_log