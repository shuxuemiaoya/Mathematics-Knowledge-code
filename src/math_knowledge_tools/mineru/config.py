import logging
import os
from pathlib import Path

from dotenv import load_dotenv


def _load_env_files() -> None:
    """Load local secrets without requiring them to live inside this repo."""
    explicit_env = os.getenv("MATH_KNOWLEDGE_ENV")
    if explicit_env:
        load_dotenv(dotenv_path=explicit_env, override=False)

    package_file = Path(__file__).resolve()
    repo_root = package_file.parents[3]
    shared_parent = repo_root.parent

    for env_path in (repo_root / ".env", shared_parent / ".env"):
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)

    load_dotenv(override=False)


_load_env_files()

# API Config
MINERU_API_KEY = os.getenv("MINERU_API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://mineru.net/api/v4")

# Processing Config
MAX_PARALLEL_TASKS = int(os.getenv("MAX_PARALLEL_TASKS", "10"))
MAX_PAGES_PER_CHUNK = int(os.getenv("MAX_PAGES_PER_CHUNK", "200"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))

# Project defaults
DEFAULT_KNOWLEDGE_BASE_DIR = os.getenv(
    "KNOWLEDGE_BASE_DIR",
    r"C:\mygithub\Secondary-School-Mathematics-Knowledge-Map",
)
DEFAULT_SOURCE_MATERIALS_DIR = os.getenv(
    "SOURCE_MATERIALS_DIR",
    r"C:\code\BaiduSyncdisk\数学妙呀资料",
)

# Log Config
LOG_FORMAT = "%(asctime)s - [%(levelname)s] - %(threadName)s - %(message)s"
logger = logging.getLogger("MinerUParser")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    logger.propagate = False

def get_logger():
    return logger
