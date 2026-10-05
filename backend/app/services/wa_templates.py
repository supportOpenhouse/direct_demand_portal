"""Template text rules — pure, no DB (spec §4.1)."""
import re

VAR_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}", re.ASCII)
GUPSHUP_ID_RE = re.compile(r"[0-9a-fA-F-]{32,40}")
# Once a campaign has used a template, these can't change: past campaigns must keep
# rendering exactly what was sent. variable_count is derived from body, so it's covered.
LOCKED_FIELDS = ("body", "gupshup_template_id")


def variable_count(body: str) -> int:
    """Number of {{n}} slots. Slots must run 1..n with no gap — {{1}} {{3}} would leave
    a slot Gupshup expects and nobody can fill. {{0}} and absurdly large numbers are rejected.
    First appearance of slots must be in order (Gupshup fills params in order of occurrence)."""
    matches = VAR_RE.findall(body or "")
    if not matches:
        return 0

    used = {int(m) for m in matches}
    # Check for {{0}} first
    if 0 in used:
        raise ValueError("template body uses {{0}} — slots must start at {{1}}")

    # Validate contiguous 1..n: must have exactly slots 1, 2, ..., n
    expected = set(range(1, len(used) + 1))
    if used != expected:
        # Find the first missing slot
        for i in range(1, max(used) + 1):
            if i not in used:
                raise ValueError(f"template body skips variable {{{{{i}}}}} — slots must run 1..{max(used)}")

    # Validate that slots first appear in order (Gupshup contract §1.3)
    seen = set()
    for m in matches:
        slot_num = int(m)
        if slot_num not in seen:
            # First appearance of this slot
            if slot_num != len(seen) + 1:
                raise ValueError("slots must first appear in order — {{1}} before {{2}} (Gupshup fills them in the order they occur)")
            seen.add(slot_num)

    return len(used)


def render(body: str, values: list[str]) -> str:
    n = variable_count(body)
    if len(values) != n:
        raise ValueError(f"template has {n} variable(s), got {len(values)}")
    return VAR_RE.sub(lambda m: str(values[int(m.group(1)) - 1]), body)


def normalize_template(fields: dict) -> dict:
    """Normalize and validate template fields. Raises ValueError for validation errors."""
    # Strip all string fields before validation
    gupshup_template_id = (fields.get("gupshup_template_id") or "").strip()
    name = (fields.get("name") or "").strip()
    body = (fields.get("body") or "").strip()
    language = ((fields.get("language") or "en").strip() or "en")
    category = ((fields.get("category") or "").strip() or None)

    # Validate required fields
    if not gupshup_template_id:
        raise ValueError("gupshup_template_id is required")
    if not name:
        raise ValueError("name is required")
    if not body:
        raise ValueError("body is required")

    # Validate Gupshup template ID format (§1.3 Gupshup contract)
    if not GUPSHUP_ID_RE.fullmatch(gupshup_template_id):
        raise ValueError("Use the Gupshup template ID (the long id shown in Gupshup → Templates), not the template name")

    # Validate and count variables
    n = variable_count(body)

    # Normalize variable_labels and variable_defaults per index
    variable_labels = fields.get("variable_labels") or []
    labels = []
    for i in range(n):
        lbl = variable_labels[i] if i < len(variable_labels) else None
        if lbl is None or (isinstance(lbl, str) and not lbl.strip()):
            lbl = f"Variable {i + 1}"
        else:
            lbl = lbl.strip()
        labels.append(lbl)

    variable_defaults = fields.get("variable_defaults") or []
    defaults = []
    for i in range(n):
        d = variable_defaults[i] if i < len(variable_defaults) else None
        if d is None or (isinstance(d, str) and not d.strip()):
            d = None
        elif isinstance(d, str):
            d = d.strip() or None
        defaults.append(d)

    # Normalize buttons: strip and remove empty
    buttons = [b.strip() for b in (fields.get("buttons") or []) if b.strip()]

    return {
        "gupshup_template_id": gupshup_template_id,
        "name": name,
        "language": language,
        "category": category,
        "body": body,
        "variable_count": n,
        "variable_labels": labels,
        "variable_defaults": defaults,
        "buttons": buttons,
        "active": fields.get("active", True),
    }


def locked_changes(current: dict, new: dict) -> list[str]:
    """Check if any locked fields have changed (comparing stripped versions).
    Returns list of changed field names, empty if no locked changes."""
    changes = []
    for field in LOCKED_FIELDS:
        cur_val = (current.get(field) or "").strip() if isinstance(current.get(field), str) else current.get(field)
        new_val = (new.get(field) or "").strip() if isinstance(new.get(field), str) else new.get(field)
        if cur_val != new_val:
            changes.append(field)
    return changes
