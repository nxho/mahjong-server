import logging

def init():
    logger = logging.getLogger('mahjong-server')
    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] - %(message)s'))

    logger.addHandler(ch)

def get():
    return logging.getLogger('mahjong-server')

