import logging

import config

logger = logging.getLogger("Judge")
logger.setLevel(config.LOGGER_LEVEL)
handler = logging.StreamHandler()
if config.LOGGER_LEVEL == logging.DEBUG:
    formatter = logging.Formatter(
        "%(asctime)s %(filename)s %(name)s - %(levelname)s: %(message)s"
    )
else:
    formatter = logging.Formatter("%(asctime)s %(name)s %(message)s")

handler.setFormatter(formatter)
logger.addHandler(handler)
