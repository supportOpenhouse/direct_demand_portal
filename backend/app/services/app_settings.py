"""Org-wide settings an admin sets once and everyone reads.

Deliberately a fixed whitelist rather than a free key-value store. The write endpoint
is reachable from a browser, so an open key space turns one admin form into arbitrary
writes against a shared table.

Values are stored as text and coerced on the way out. That coercion is the whole
point of this module: 'false' is a non-empty string, so an uncoerced value read in
the browser is truthy — which is exactly how a hide-flag gets stuck on with no way to
turn it off from the UI.
"""

# key -> value when no row exists. Off by default: hiding the numbers RMs work from
# has to be a deliberate act, never what a fresh install does on its own.
DEFAULTS: dict[str, bool] = {
    # Lead phone numbers in the New Leads / Follow-up / segment tables. For shared
    # screens and screenshots — the number still reaches the browser and the call
    # button still works, this only stops it being rendered.
    "hide_lead_phones": False,
}

SETTING_KEYS = frozenset(DEFAULTS)

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off", ""}


def coerce(key: str, value) -> bool:
    """Stored text -> real boolean. Unknown keys raise; unparseable values fall back
    to the default rather than guessing."""
    if key not in SETTING_KEYS:
        raise KeyError(f"unknown setting {key!r}")
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


def merge_defaults(stored: dict) -> dict[str, bool]:
    """Every known key, coerced, with defaults filling the gaps.

    The frontend indexes straight into this object, so a key with no row must come
    back as false rather than missing — an undefined would render the toggle empty
    instead of off.
    """
    return {k: coerce(k, stored.get(k)) for k in DEFAULTS}
