"""Org-wide settings an admin sets once and everyone reads.

Deliberately a fixed whitelist rather than a free key-value store. The write endpoint
is reachable from a browser, so an open key space turns one admin form into arbitrary
writes against a shared table.

Values are stored as text and coerced on the way out. That coercion is the whole
point of this module: 'false' is a non-empty string, so an uncoerced value read in
the browser is truthy — which is exactly how a hide-flag gets stuck on with no way to
turn it off from the UI. List settings are stored as JSON text and coerced back to a
normalised list of lowercased strings.
"""
import json

# key -> value when no row exists. Off / empty by default: withholding a feature has to
# be a deliberate act, never what a fresh install does on its own.
DEFAULTS: dict[str, object] = {
    # Lead phone numbers in the New Leads / Follow-up / segment tables. For shared
    # screens and screenshots — the number still reaches the browser and the call
    # button still works, this only stops it being rendered.
    "hide_lead_phones": False,
    # WhatsApp top-bar button visibility for non-admins. Admins always see it.
    #   wa_show_all_rms  — master switch: show it to every RM.
    #   wa_allowed_emails — extra grant: specific users who see it even when the
    #                       master switch is off.
    "wa_show_all_rms": False,
    "wa_allowed_emails": [],
}

# keys whose value is a list of strings (stored as JSON) rather than a boolean
LIST_KEYS = frozenset({"wa_allowed_emails"})
SETTING_KEYS = frozenset(DEFAULTS)

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off", ""}


def _coerce_list(key: str, value) -> list[str]:
    """Stored JSON text (or a real list) -> normalised list of unique, lowercased,
    non-empty strings. Anything unparseable falls back to the default."""
    default = list(DEFAULTS[key])  # type: ignore[arg-type]
    if value is None:
        return default
    if isinstance(value, list):
        items = value
    else:
        try:
            parsed = json.loads(str(value))
        except (ValueError, TypeError):
            return default
        if not isinstance(parsed, list):
            return default
        items = parsed
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        s = str(it).strip().lower()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def coerce(key: str, value):
    """Stored text -> real value (bool for flags, list[str] for list keys). Unknown
    keys raise; unparseable values fall back to the default rather than guessing."""
    if key not in SETTING_KEYS:
        raise KeyError(f"unknown setting {key!r}")
    if key in LIST_KEYS:
        return _coerce_list(key, value)
    if isinstance(value, bool):
        return value
    if value is None:
        return DEFAULTS[key]
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return DEFAULTS[key]


def merge_defaults(stored: dict) -> dict:
    """Every known key, coerced, with defaults filling the gaps.

    The frontend indexes straight into this object, so a key with no row must come
    back as its default (false / []) rather than missing — an undefined would render
    the control empty instead of off.
    """
    return {k: coerce(k, stored.get(k)) for k in DEFAULTS}
