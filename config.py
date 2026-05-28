import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
PDF_DIR = DATA_DIR / "lcaps"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
PDF_DIR.mkdir(exist_ok=True)

CDE_DIRECTORY_URL = "https://www.cde.ca.gov/schooldirectory/report?rid=dl1&tp=txt"
SCHOOLS_CACHE = DATA_DIR / "ca_schools.txt"
MIDDLE_SCHOOLS_CACHE = DATA_DIR / "middle_schools.csv"

CLAUDE_MODEL = "claude-sonnet-4-5"  # 4.5 supports PDF document input + vision


DEFAULT_COUNTY = "Los Angeles"
DEFAULT_LIMIT = 5
