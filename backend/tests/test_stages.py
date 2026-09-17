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


def test_the_eight_pages_hold_exactly_the_stages_they_should():
    """The page system (16 Sep). Three pages hold two stages each, and each pairing is a
    decision, not an accident — so they're pinned here rather than left to drift:
      Call Not Received  + rnr             10 straight misses is the same problem further
                                           along, not a rejection
      Visited Leads      both visit stages a revisit is the same buyer at the same
                                           property — stronger, but not different work
      Rejected           rejected ONLY     future_prospect moved out to its own page; a
                                           buyer worth calling in three months is not dead
    """
    assert {seg: _stages_named_in(p) for seg, p in SEGMENTS.items()} == {
        "new": {"new"},
        "call_not_received": {"call_not_received", "rnr"},
        "followup": {"follow_up"},
        "qualified": {"qualified"},
        "future_prospect": {"future_prospect"},
        "visited": {"visit_scheduled", "revisit_scheduled"},
        "rejected": {"rejected"},
        "converted": {"converted"},
    }


def test_the_stage_is_converted_not_won():
    """Renamed 16 Sep — `won` is gone from the model entirely, so a leftover reference
    is a page that silently never matches. scripts/18 renames the rows to match."""
    assert "converted" in STAGES and "won" not in STAGES
    assert "won" not in _TERMINAL and "converted" in _stages_named_in(_TERMINAL)


def test_the_frontend_knows_the_same_stages_and_pages():
    """`ALL_STAGES` feeds the manual stage picker and is validated against STAGES by the
    endpoint — a value in one and not the other is a 422 nobody can explain. LEAD_SEGMENTS
    drives the nav, useAllLeads' parallel queries and the funnel's "bars + band = All"."""
    import pathlib

    ts = (pathlib.Path(__file__).parents[2] / "frontend" / "src" / "lib" / "leads.ts").read_text()
    stages = re.findall(r'"([a-z_]+)"', ts.split("export const ALL_STAGES = [", 1)[1].split("]", 1)[0])
    assert set(stages) == set(STAGES), f"frontend stages differ: {set(stages) ^ set(STAGES)}"

    segs = re.findall(r'seg: "([a-z_]+)"', ts.split("LEAD_SEGMENTS", 1)[1].split("];", 1)[0])
    assert segs == list(SEGMENTS), f"frontend segments differ: {segs} vs {list(SEGMENTS)}"


def test_future_prospect_is_parked_like_rnr():
    """A re-submitted qualify form or a saved callback must not silently pull a parked
    buyer back into the funnel. Bringing one back is the manual stage setter's job."""
    assert "future_prospect" in _stages_named_in(_TERMINAL)


def test_the_boot_migration_no_longer_folds_future_prospect():
    """The regression that would have shipped silently. run_migrations runs on EVERY
    boot, and it used to rewrite `future_prospect` → `rejected`. Left in, every future
    prospect set today would vanish on the next deploy — after testing had passed.

    Python comments are stripped first: the migration's own comment explains why
    future_prospect is no longer in the list, and would otherwise match."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1] / "app" / "migrations.py").read_text()
    code = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
    for in_list in re.findall(r"stage IN \(([^)]*)\)", code):
        assert "future_prospect" not in in_list, f"a migration still folds it: ({in_list})"


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
    # future_prospect was retired here once and revived 14 Sep — see the test above
    for retired in ("visit_planned", "contacted", "lost", "timepass"):
        assert retired not in STAGES
        for seg, pred in SEGMENTS.items():
            assert retired not in pred, f"segment '{seg}' still references '{retired}'"


# --- "No" spam guard ----------------------------------------------------------

def test_blocked_no_writes_nothing():
    """Every column the miss-UPDATE sets must have a `cur.blocked` branch that writes
    the value back unchanged. Miss one — miss_count especially — and a spammed "No"
    still counts toward the 10 that force a lead to RNR, which is the whole point of
    the guard."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1] / "app/routers/leads.py").read_text()
    # anchor on the CTE — several handlers contain "UPDATE leads SET", and the first
    # one in the file is the confirm handler, not this one
    assert "WITH cur AS" in src, "spam-guard CTE not found — did the SQL move?"
    body = src.split("WITH cur AS", 1)[1].split("UPDATE leads SET", 1)[1].split("FROM cur", 1)[0]

    # split into assignments: each starts at "<column> = " at the head of a line
    assignments: dict[str, list[str]] = {}
    current = None
    for line in body.splitlines():
        m = re.match(r"\s*(\w+) = ", line)
        if m:
            current = m.group(1)
            assignments[current] = []
        if current:
            assignments[current].append(line)

    assert "miss_count" in assignments, "miss-UPDATE not found — did the SQL move?"
    unguarded = [col for col, lines in assignments.items()
                 if "cur.blocked" not in "\n".join(lines)]
    assert not unguarded, f"columns written even when blocked: {unguarded}"


def test_cooldown_is_two_hours():
    from app.routers.leads import NO_COOLDOWN_HOURS
    assert NO_COOLDOWN_HOURS == 2


def test_stage_boxes_match_the_pages_that_hold_several_stages():
    """SEGMENT_STAGES (lib/leads.ts) drives the ALL + per-stage boxes on a page. It must
    list exactly the multi-stage pages, with exactly their stages: a missing stage leaves
    leads with no box to find them by, and an extra one is a box that always reads 0."""
    import pathlib

    ts = (pathlib.Path(__file__).parents[2] / "frontend" / "src" / "lib" / "leads.ts").read_text()
    block = ts.split("export const SEGMENT_STAGES", 1)[1].split("};", 1)[0]
    frontend = {seg: set(re.findall(r'"([a-z_]+)"', stages))
                for seg, stages in re.findall(r"(\w+):\s*\[([^\]]*)\]", block)}

    backend = {seg: _stages_named_in(p) for seg, p in SEGMENTS.items()
               if len(_stages_named_in(p)) > 1}
    assert frontend == backend, f"stage boxes drifted from SEGMENTS: {frontend} vs {backend}"
