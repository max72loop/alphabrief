import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(Path('/root/.env'))       # clés globales (FMP, DeepSeek)
load_dotenv(BASE_DIR / '.env')        # surcharges locales


class Config:
    DATA_DIR = BASE_DIR / 'data'
    DB_PATH = BASE_DIR / 'data' / 'alphabrief.db'
    MAX_RETRIES = 3
    ALERT_REFRESH_HOURS = 4
    ALERT_SCORE_DELTA = 15
    ALERT_STRONG_BUY = 75
    # FMP (Financial Modeling Prep)
    FMP_API_KEY = os.environ.get('FMP_API_KEY', '')
    # Base : Postgres local, joint par socket Unix. Aucun secret à porter ici —
    # voir core/storage/db.py. Surcharge possible via ALPHABRIEF_DSN.
    # LLM (DeepSeek — compatible OpenAI SDK)
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
    LLM_MODEL = 'deepseek-chat'
    LLM_BASE_URL = 'https://api.deepseek.com'
