import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("smm.log"), logging.StreamHandler()]
)
log = logging.getLogger("smm")