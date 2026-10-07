"""Canonical city + configuration normalizers, shared across leads, inventory,
supply and matching so filters and matching treat the same thing as the same.

- City: all Noida variants (Greater Noida, Gr Noida West, Noida Ext…) → "Noida";
  likewise Gurgaon/Gurugram → "Gurgaon", Ghaziabad → "Ghaziabad".
- Configuration: merges case/spacing variants ("2bhk", "2 BHK" → "2 BHK") but KEEPS
  meaningful qualifiers ("2 BHK + Study" stays distinct, NOT collapsed to "2 BHK").
  Matching compares the bedroom count via config_bhk so "2 BHK" still matches
  "2 BHK + Study"."""
import re
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

# qualifiers that make a config genuinely different — preserved, never merged away
_CONFIG_EXTRAS = [
    (r"\bstudy\b", "Study"),
    (r"\bservant\b|\bmaid\b|\bs\.?q\.?\b|\bservant\s*quarter\b", "Servant"),
    (r"\bpooja\b|\bpuja\b|\bmandir\b", "Pooja"),
    (r"\butility\b", "Utility"),
    (r"\bstore\b|\bstorage\b", "Store"),
]


def normalize_city(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if "noida" in s:
        return "Noida"
    if "gurgaon" in s or "gurugram" in s:
        return "Gurgaon"
    if "ghaziabad" in s:
        return "Ghaziabad"
    if "faridabad" in s:
        return "Faridabad"
    if "delhi" in s:
        return "Delhi"
    return str(raw).strip().title()


def normalize_config(raw: str | None) -> str | None:
    """Canonical config for display/filtering. '2bhk'/'2 BHK' → '2 BHK', but
    '2 BHK + Study'/'2 + study' → '2 BHK + Study' (kept distinct, not merged to
    '2 BHK'). '2BHK + SQ' → '2 BHK + Servant'. Non-numeric ('Studio', 'Villa') kept."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if "studio" in s:
        return "Studio"
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return str(raw).strip().title()
    n = m.group(1)
    if n.endswith(".0"):
        n = n[:-2]
    unit = "RK" if re.search(r"\brk\b", s) else "BHK"
    extras = [label for pat, label in _CONFIG_EXTRAS if re.search(pat, s)]
    base = f"{n} {unit}"
    return base + " + " + " + ".join(extras) if extras else base


def config_bhk(raw: str | None) -> float | None:
    """Bedroom count only, for matching — '2 BHK' and '2 BHK + Study' both → 2.0."""
    if raw is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    return float(m.group(1)) if m else None


def clean_societies(values: list[str] | None) -> list[str]:
    """Strip, drop blanks, de-dupe ignoring case — the first spelling wins. Every
    writer of leads.societies / shortlisted_societies goes through this."""
    out: list[str] = []
    seen: set[str] = set()
    for v in values or []:
        s = v.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


# A society list from a client: each name <= 200 chars, <= 50 names, else 422.
Societies = Annotated[
    list[Annotated[str, StringConstraints(max_length=200)]],
    Field(max_length=50),
    AfterValidator(clean_societies),
]
