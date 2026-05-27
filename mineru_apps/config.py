import os
import logging
from dotenv import load_dotenv

# 优先尝试从私有主目录（C:\mygithub）加载 .env，以便未来代码开源时不泄露 Token
parent_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
if os.path.exists(parent_env_path):
    load_dotenv(dotenv_path=parent_env_path)
else:
    load_dotenv()

# API Config
MINERU_API_KEY = os.getenv("MINERU_API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://mineru.net/api/v4")

# Processing Config
MAX_PARALLEL_TASKS = int(os.getenv("MAX_PARALLEL_TASKS", "10"))
MAX_PAGES_PER_CHUNK = int(os.getenv("MAX_PAGES_PER_CHUNK", "200"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))

# Log Config
LOG_FORMAT = "%(asctime)s - [%(levelname)s] - %(threadName)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("MinerUParser")

def get_logger():
    return logger
