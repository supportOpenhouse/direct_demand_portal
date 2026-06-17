"""Canonical city + configuration normalizers, shared across leads, inventory,
supply and matching so filters and matching treat the same thing as the same.

- City: all Noida variants (Greater Noida, Gr Noida West, Noida Ext…) → "Noida";
  likewise Gurgaon/Gurugram → "Gurgaon", Ghaziabad → "Ghaziabad".
- Configuration: "2BHK", "2 bhk", "2 BHK + Study", "2BHK + SQ" → "2 BHK"
  (base BHK count only — suffixes are dropped for grouping/matching)."""
import re


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
    """'2BHK'/'2 bhk'/'2 BHK + Study' → '2 BHK'. Leaves non-BHK text as-is."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*bhk", s)
    if not m:
        return str(raw).strip()
    n = m.group(1)
    if n.endswith(".0"):
        n = n[:-2]
    return f"{n} BHK"
