import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(Path('/root/.env'))       # clés globales (FMP, Supabase)
load_dotenv(BASE_DIR / '.env')        # surcharges locales


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
    DATA_DIR = BASE_DIR / 'data'
    DB_PATH = BASE_DIR / 'data' / 'alphabrief.db'
    DEBUG = True
    MAX_RETRIES = 3
    ALERT_REFRESH_HOURS = 4
    ALERT_SCORE_DELTA = 15
    ALERT_STRONG_BUY = 75
    # FMP (Financial Modeling Prep)
    FMP_API_KEY = os.environ.get('FMP_API_KEY', '')
    # Supabase
    SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
    # LLM (DeepSeek — compatible OpenAI SDK)
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
    LLM_MODEL = 'deepseek-chat'
    LLM_BASE_URL = 'https://api.deepseek.com'
