import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
# Each user's "drop here" folder lives under INBOX_DIR/<e-mail>/ (files that were taken in move to processed/)
INBOX_DIR = BASE_DIR / "inbox"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
INBOX_DIR.mkdir(exist_ok=True)

# Topics that existed before accounts were introduced belong to this person (they claim them by registering).
DEFAULT_OWNER_EMAIL = os.getenv("DEFAULT_OWNER_EMAIL", "ariel29961@gmail.com")
DEFAULT_OWNER_NAME = os.getenv("DEFAULT_OWNER_NAME", "Ariel Rabinovitch")

DATABASE_URL = f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"

# Ask AI: how much of the sources the model reads (see services/context_budget.py)
MAX_CONTEXT_CHARS = 120000  # all sources of the topic together
MAX_SOURCE_CHARS = 30000  # one source (a 30-minute transcript is about 27,000)
CROSS_CONTEXT_CHARS = 30000  # all sources picked from other topics together
CROSS_SOURCE_CHARS = 8000  # one of those
