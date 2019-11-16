import logging

def init(to_console=False, to_file=False):
    logger = logging.getLogger('mahjong-server')
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] - %(message)s')

    if to_console:
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    if to_file:
        fh = logging.FileHandler('server.log')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger

def get():
    return logging.getLogger('mahjong-server')

