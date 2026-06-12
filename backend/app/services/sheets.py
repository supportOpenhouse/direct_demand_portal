"""Google Sheets access via service account. gspread is sync — callers wrap in
asyncio.to_thread. Header normalization + price parsing live here so they can be
unit-tested without credentials."""
import re

from ..config import get_settings

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def normalize_header(h: str) -> str:
    """'Asking Price (₹)' -> 'asking_price'"""
    h = h.strip().lower()
    h = re.sub(r"[^\w]+", "_", h, flags=re.UNICODE)
    return h.strip("_")


def parse_price_lacs(text: str | float | int | None) -> float | None:
    """Best-effort: '₹1.2 Cr' -> 120, '85 L'/'85 Lacs' -> 85, '9500000' -> 95.

    Bare numbers are interpreted by magnitude: >= 100000 is rupees, < 1000 is lacs.
    """
    if text is None:
        return None
    s = str(text).strip().lower().replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "")
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    n = float(m.group(1))
    if re.search(r"\bcr\b|crore", s):
        return n * 100
    if re.search(r"\bl\b|lac|lakh", s):
        return n
    if n >= 100000:  # plain rupees
        return round(n / 100000, 2)
    if n < 1000:  # plausibly already lacs
        return n
    return None


def fetch_sheet_values() -> list[list[str]]:
    """Blocking. Returns all rows of the first worksheet (row 0 = headers)."""
    import gspread
    from google.oauth2.service_account import Credentials

    settings = get_settings()
    info = settings.service_account_info
    if not info or not settings.SHEET_ID:
        raise RuntimeError("Sheets sync not configured")
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(settings.SHEET_ID).sheet1
    return sheet.get_all_values()
