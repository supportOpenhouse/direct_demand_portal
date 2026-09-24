"""Demand Dashboard: it reads, and it only reads.

The source app writes these properties while listing them (it back-fills listing_price
and normalises possession on a GET). Ours must not, for any role — two apps writing the
same row with no rule about who wins is how they end up disagreeing.
"""
import ast
import re
from pathlib import Path

from app.routers import demand_dashboard as router_mod
from app.services import demand_dashboard as svc

SERVICE = Path(svc.__file__).read_text()
ROUTER = Path(router_mod.__file__).read_text()


def _sql_only(text_: str) -> str:
    """The module's SQL and code with comments and docstrings stripped — prose about a
    write is not a write, and asserting on it fails on our own explanation."""
    tree = ast.parse(text_)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                node.body = node.body[1:]
    return re.sub(r"#.*", "", ast.unparse(tree))


def test_nothing_in_the_service_writes():
    body = _sql_only(SERVICE).upper()
    for verb in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER ", "DROP ", "RETURNING"):
        assert verb not in body, f"{verb.strip()} in a read-only service"


def test_the_router_exposes_no_write_route():
    for route in router_mod.router.routes:
        assert set(route.methods) <= {"GET", "HEAD"}, f"{route.path} allows {route.methods}"
    # and nothing may sneak one in under a decorator we didn't check
    assert not re.search(r"@router\.(post|put|patch|delete)", ROUTER)


def test_every_projected_column_is_unique_and_typed():
    aliases = [alias for _p, _l, alias, _t in svc.UNIFIED_COLS]
    assert len(aliases) == len(set(aliases)), "two columns share an output name"
    assert all(typ.isupper() for *_x, typ in svc.UNIFIED_COLS), "UNION needs an explicit type"
    # the page's own columns, so a rename upstream fails here rather than blanking a cell
    for needed in ("uid", "society_name", "unit_no", "city", "configuration", "area_sqft",
                   "locality", "poc", "ama_date", "key_handover_date"):
        assert needed in aliases


def test_both_union_sides_project_the_same_columns_in_the_same_order():
    """A UNION matches by POSITION, not by name: one column missing on the legacy side
    would silently shift every later value into the wrong field."""
    columns = {"properties": {p for p, _l, _a, _t in svc.UNIFIED_COLS} | {"replicated"},
               "legacy_properties": {lc for _p, lc, _a, _t in svc.UNIFIED_COLS if lc}}
    left = re.findall(r'AS "(\w+)"', svc._side(columns, "properties", "p", 0))
    right = re.findall(r'AS "(\w+)"', svc._side(columns, "legacy_properties", "lp", 1))
    assert left == right == [a for _p, _l, a, _t in svc.UNIFIED_COLS]


PAGE = Path(__file__).parents[2] / "frontend" / "src" / "pages" / "DemandDashboard.tsx"


def _fields_the_page_reads() -> set[str]:
    """Every column name the page names: `p.<field>`, and the `["Label", "column"]` pairs
    the popup's sections are written as."""
    src = PAGE.read_text()
    used = set(re.findall(r"\bp\.([a-z_][a-z0-9_]*)", src))
    used |= set(re.findall(r'"([a-z_][a-z0-9_]*)"\]', src))
    used |= set(re.findall(r',\s*"([a-z_][a-z0-9_]*)",\s*(?:num|day|money)\]', src))
    return used


def test_the_api_sends_only_what_the_page_reads():
    """No column travels that nothing renders. The seller's identity, the guaranteed sale
    price and the pipeline dates were removed from the page on purpose (23 Sep); leaving
    them in the payload would keep shipping them to every browser that opens devtools."""
    sent = {alias for _p, _l, alias, _t in svc.UNIFIED_COLS} | set(svc.JOINED_COLS)
    read = _fields_the_page_reads()
    assert not (sent - read), f"sent but never rendered: {sorted(sent - read)}"
    for removed in ("owner_name", "contact_no", "co_owner", "seller_location",
                    "guaranteed_sale_price", "loan_status", "sold_date", "buyer_visit_date",
                    "supply_internal_remarks"):
        assert removed not in sent, f"{removed} is back in the payload"


def test_the_page_asks_for_nothing_the_api_does_not_send():
    """The other direction: a field the page renders but the query never selects is a
    column of blanks nobody notices."""
    sent = {alias for _p, _l, alias, _t in svc.UNIFIED_COLS} | set(svc.JOINED_COLS)
    # The default layout `DEMAND_COLS = [...]` lists the page's COLUMN ids, not database
    # fields ("remarks", "brochure") — its last entry matches the `"name"]` pattern the
    # scan uses for section fields. Every id in that list is excluded as a group, rather
    # than special-casing whichever one happens to be last.
    layout = re.search(r"const DEMAND_COLS = \[([^\]]*)\]", PAGE.read_text()).group(1)
    column_ids = set(re.findall(r'"(\w+)"', layout))
    missing = _fields_the_page_reads() - sent - column_ids
    assert not missing, f"rendered but never sent: {sorted(missing)}"


def test_dead_properties_never_leave_the_backend():
    """'Dead' is the source app's soft delete. Their UI shows it to admins only; here
    nobody edits anything, so a deleted property is simply not part of the book."""
    sql = svc.build_sql({"properties": {"replicated"}, "legacy_properties": set()})
    assert "<> 'Dead'" in sql


def test_only_supply_ready_properties_are_listed():
    assert svc.SUPPLY_READY_STATUSES == ("AMA Signed", "Key Handover Done")
    sql = svc.build_sql({"properties": set(), "legacy_properties": set()})
    assert "apd.status = ANY(:ready)" in sql
