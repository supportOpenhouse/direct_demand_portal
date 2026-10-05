"""Turn an upload / paste into campaign rows — pure, no DB (spec §5.1)."""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import openpyxl


_SCI = re.compile(r"(\d)\.(\d+)[eE]\+?(\d+)")


def phone10(raw) -> str | None:
    """Exactly one Indian mobile: 10 digits starting with 6–9, optionally behind 00/91/0.
    Stricter than the app's last-10 MATCHING key (which permits any 10 digits); a campaign
    SENDS to this number, so it must be exactly one valid Indian mobile, never truncated
    from garbage. Excel stores numbers as floats: 919876543210 → 9.1987654321e11,
    '9876543210.0', or in a CSV saved from Excel — '9.19876543210E+11'. Format those as
    integers before validating. A scientific value that lost digits to rounding
    ('9.19877E+11') is refused, never guessed. Non-ASCII digits (Devanagari, etc.) are refused."""
    if raw is None:
        return None
    if isinstance(raw, float):
        if not raw.is_integer():
            return None
        raw = f"{raw:.0f}"
    s = str(raw).strip()
    # Refuse non-ASCII digits outright (before stripping) — drops Devanagari, etc.
    if any(ch.isdigit() and not ch.isascii() for ch in s):
        return None
    m = _SCI.fullmatch(s)
    if m:
        digits, exp = m.group(1) + m.group(2), int(m.group(3))
        if len(digits) < exp + 1 or digits[exp + 1:].strip("0"):
            return None
        s = digits[: exp + 1]
    else:
        s = re.sub(r"(?<=\d)\.0+$", "", s)  # '….0', with or without a '+91' in front
    d = re.sub(r"[^0-9]", "", s)  # ASCII digits only (\D is Unicode-aware)
    mobile = re.fullmatch(r"0{0,2}(?:91)?0?([6-9]\d{9})", d)  # exactly one Indian mobile
    return mobile.group(1) if mobile else None


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        if v.time() == datetime.min.time():
            return v.date().isoformat()
        else:
            return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return f"{v:.0f}"
    return str(v).strip()


def parse_upload(filename: str, data: bytes) -> tuple[list[str], list[list[str]]]:
    """(headers, rows) from a .csv or .xlsx; first sheet, first row is the header."""
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm")):
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            ws = wb.worksheets[0]
            ws.reset_dimensions()
            rows = [[_cell(v) for v in r] for r in ws.iter_rows(values_only=True)]
        finally:
            wb.close()
    elif lower.endswith((".csv", ".txt")):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252")
        rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text))]
    else:
        raise ValueError("upload a .csv or .xlsx file")
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return [], []
    return rows[0], rows[1:]


def parse_paste(text: str) -> list[list[str]]:
    out = []
    for line in (text or "").splitlines():
        if line.strip():
            out.append([c.strip() for c in re.split(r"[,\t]", line)])
    return out


def flatten_param(v: str | None) -> str | None:
    """Flatten a template parameter to one line. Meta refuses a param with a newline,
    a tab or 5+ spaces in a row (error 132018). Returns None if the result is blank."""
    return " ".join((v or "").split()) or None


@dataclass
class Candidate:
    phone10: str | None
    name: str | None
    variables: list = field(default_factory=list)
    error: str | None = None  # invalid_phone | missing_variable | duplicate


def build(rows, *, phone_col: int, name_col: int | None, var_cols: list[int | None],
          fixed: list[str | None], defaults: list[str | None]) -> list[Candidate]:
    """One Candidate per input row, in order. Each slot i takes var_cols[i]'s cell, else
    fixed[i], and if that's blank, defaults[i]; still blank → missing_variable. Only a
    valid row claims its phone; duplicates and invalid rows are flagged `duplicate` /
    `invalid_phone` (never sent twice)."""
    seen: set[str] = set()
    out = []
    for r in rows:
        get = lambda i: (r[i].strip() if i is not None and i < len(r) and r[i] else "")  # noqa: E731
        p = phone10(get(phone_col))
        name = get(name_col) or None if name_col is not None else None
        values = []
        for i, col in enumerate(var_cols):
            v = (get(col) if col is not None else (fixed[i] or "")) or defaults[i] or ""
            values.append(flatten_param(v))
        if p is None:
            out.append(Candidate(None, name, values, "invalid_phone"))
        elif p in seen:
            out.append(Candidate(p, name, values, "duplicate"))
        else:
            error = "missing_variable" if None in values else None
            if error is None:
                seen.add(p)
            out.append(Candidate(p, name, values, error))
    return out
