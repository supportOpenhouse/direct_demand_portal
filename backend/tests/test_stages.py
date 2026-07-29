"""The stage model: `stage` decides which page a lead is on.

These guard the property the whole redesign exists for — every lead lands on exactly
one page, and no page can reference a stage that doesn't exist. The old model derived
pages from confirmed/follow_up_at/qualified_at and needed a catch-all clause to stop
worked leads disappearing; these tests make that regression impossible to reintroduce.
"""
import re

from app.routers.leads import SEGMENTS, STAGES, _TERMINAL

# stages the SQL is allowed to name, i.e. exactly the model
_STAGE_LITERAL = re.compile(r"'([a-z_]+)'")


def _stages_named_in(predicate: str) -> set[str]:
    return set(_STAGE_LITERAL.findall(predicate))


def test_every_stage_has_exactly_one_page():
    """No lead can be orphaned: each stage is claimed by exactly one segment."""
    claimed: dict[str, list[str]] = {}
    for seg, pred in SEGMENTS.items():
        for stage in _stages_named_in(pred):
            claimed.setdefault(stage, []).append(seg)

    missing = [s for s in STAGES if s not in claimed]
    assert not missing, f"stages with no page: {missing}"

    doubled = {s: segs for s, segs in claimed.items() if len(segs) > 1}
    assert not doubled, f"stages appearing on two pages: {doubled}"


def test_no_page_references_an_unknown_stage():
    """A typo'd or retired stage in a predicate yields a permanently empty page."""
    for seg, pred in SEGMENTS.items():
        unknown = _stages_named_in(pred) - set(STAGES)
        assert not unknown, f"segment '{seg}' references unknown stage(s): {unknown}"


def test_rejected_page_holds_rnr_too():
    """RNR keeps its own stage but has no page — it shares Rejected, badged."""
    assert _stages_named_in(SEGMENTS["rejected"]) == {"rejected", "rnr"}


def test_segments_are_pure_stage_predicates():
    """The point of the redesign: pages read `stage` and nothing else. A predicate
    mentioning confirmed/qualified_at/crm_visits means the derived model crept back."""
    for seg, pred in SEGMENTS.items():
        for banned in ("confirmed", "qualified_at", "crm_visits", "follow_up_at"):
            assert banned not in pred, f"segment '{seg}' still derives from {banned}"


def test_terminal_stages_are_real_stages():
    unknown = _stages_named_in(_TERMINAL) - set(STAGES)
    assert not unknown, f"_TERMINAL names unknown stage(s): {unknown}"


def test_every_stage_written_by_the_app_is_a_real_stage():
    """Scan the actual SQL for stage assignments. A transition writing a stage no page
    claims would strand that lead invisibly — the exact failure this model prevents."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "app"
    written: dict[str, set[str]] = {}
    for path in [src / "routers" / "leads.py", src / "routers" / "visits.py", src / "migrations.py"]:
        text = path.read_text()
        found = set()
        # "SET stage = 'x'" and every "THEN 'x'" inside a stage CASE expression
        found.update(re.findall(r"SET stage = '([a-z_]+)'", text))
        for case in re.findall(r"stage = CASE.*?END", text, re.S):
            # THEN and ELSE both — the "no-op guard" transitions put their real
            # target in the ELSE ("CASE WHEN terminal THEN stage ELSE 'qualified'")
            found.update(re.findall(r"(?:THEN|ELSE) '([a-z_]+)'", case))
        if found:
            written[path.name] = found

    # every one of these files performs at least one stage write; a file dropping to
    # zero means the scan stopped matching, not that the writes went away
    assert set(written) == {"leads.py", "visits.py", "migrations.py"}, \
        f"scan missed a file's stage writes: found {sorted(written)}"
    for name, stages in written.items():
        unknown = stages - set(STAGES)
        assert not unknown, f"{name} writes unknown stage(s): {unknown}"


def test_retired_stages_are_gone():
    """visit_planned and contacted were folded into qualified by the migration."""
    for retired in ("visit_planned", "contacted", "lost", "future_prospect", "timepass"):
        assert retired not in STAGES
        for seg, pred in SEGMENTS.items():
            assert retired not in pred, f"segment '{seg}' still references '{retired}'"
