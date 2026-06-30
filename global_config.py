import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SIGNAL_FILE = ".secrets/login_complete.signal"
DEFAULT_STORAGE_STATE = ".secrets/samsung_storage_state.json"
DEFAULT_URL = "https://www.samsung.com/sec/"
LLM_SMALL = os.getenv("LLM_SMALL")
LLM_MIDDLE = os.getenv("LLM_MIDDLE")
LLM_HIGH = os.getenv("LLM_HIGH")
MODEL_SMALL = os.getenv("MODEL_SMALL")
MODEL_MIDDLE = os.getenv("MODEL_MIDDLE")
MODEL_HIGH = os.getenv("MODEL_HIGH")
BASE_URL_SMALL = os.getenv("BASE_URL_SMALL")
BASE_URL_MIDDLE = os.getenv("BASE_URL_MIDDLE")
BASE_URL_HIGH = os.getenv("BASE_URL_HIGH")
API_KEY_SMALL = os.getenv("API_KEY_SMALL")
API_KEY_MIDDLE = os.getenv("API_KEY_MIDDLE")
API_KEY_HIGH = os.getenv("API_KEY_HIGH")
