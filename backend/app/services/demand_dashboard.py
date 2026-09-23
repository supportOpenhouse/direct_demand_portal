"""Demand Dashboard — the supply team's property book, READ-ONLY.

A rebuild of github.com/oh/Demand-Dashboard's list screen inside this portal. That app
owns the data and is the only thing that writes it; we show it. Same database: its
DATABASE_URL is our PROPERTIES_DATABASE_URL (verified 23 Sep, same Neon endpoint).

⚠️ Their `api/list.js` WRITES on a GET — it back-fills demand_details.listing_price and
normalises possession/occupancy while listing. None of that is copied: this reads. A
property whose auto price their app hasn't computed yet simply shows no listing price.

The projection is exactly what `pages/DemandDashboard.tsx` renders — nothing else is
sent. The seller's identity (owner, contact, co-owner, seller location), the guaranteed
sale price and the demand pipeline dates were dropped on request; a column nobody shows
is one that leaks the moment somebody opens devtools.
`tests/test_demand_dashboard.py::test_the_api_sends_only_what_the_page_reads` parses the
page and fails if the two drift apart.

Two sources, one list, exactly as they have it:
  * `properties` gated to ap_details.status IN (AMA Signed, Key Handover Done) — the
    homes actually ready to sell (358 today)
  * `legacy_properties` — 49 rows imported from the old sheet, no ap_details row at all
Both carry the same column names, so the UNION projects one shape; a column missing on
either side becomes NULL of the right type, which is what makes the UNION legal.
"""
import logging

from sqlalchemy import text

from ..db import properties_engine

log = logging.getLogger("demand_dashboard")

# Their SUPPLY_READY_STATUSES. A property is offerable only at these two.
SUPPLY_READY_STATUSES = ("AMA Signed", "Key Handover Done")

# (column on properties, column on legacy_properties or None, output name, pg type).
# Generated from their UNIFIED_COLS so the two lists can't drift by a typo.
# ⚠️ `floor` is TEXT and holds 'Top' / 'Ground' — never cast it to INTEGER.
UNIFIED_COLS: list[tuple[str, str | None, str, str]] = [
    ("uid", "uid", "uid", "TEXT"),
    ("society_name", "society_name", "society_name", "TEXT"),
    ("unit_no", "unit_no", "unit_no", "TEXT"),
    ("tower_no", "tower_no", "tower_no", "TEXT"),
    ("floor", "floor", "floor", "TEXT"),
    ("city", "city", "city", "TEXT"),
    ("locality", "locality", "locality", "TEXT"),
    ("source", "source", "source", "TEXT"),
    ("assigned_by", "assigned_by", "poc", "TEXT"),
    ("configuration", "configuration", "configuration", "TEXT"),
    ("area_sqft", "area_sqft", "area_sqft", "REAL"),
    ("super_area", "super_area", "super_area", "REAL"),
    ("carpet_area", "carpet_area", "carpet_area", "REAL"),
    ("extra_area", "extra_area", "extra_area", "JSONB"),
    ("bathrooms", "bathrooms", "bathrooms", "INTEGER"),
    ("balconies", "balconies", "balconies", "INTEGER"),
    ("balcony_details", "balcony_details", "balcony_details", "JSONB"),
    ("total_lifts", None, "total_lifts", "INTEGER"),
    ("total_floors_tower", "total_floors_tower", "total_floors_tower", "INTEGER"),
    ("total_flats_floor", "total_flats_floor", "total_flats_floor", "INTEGER"),
    ("society_age_years", "society_age_years", "society_age_years", "REAL"),
    ("total_units", "total_units", "total_units", "INTEGER"),
    ("exit_facing", "exit_facing", "exit_facing", "TEXT"),
    ("exit_compass_image", "exit_compass_image", "exit_compass_image", "TEXT"),
    ("possession_status", "possession_status", "possession_status", "TEXT"),
    ("occupancy_status", "occupancy_status", "occupancy_status", "TEXT"),
    ("current_occupancy_pct", "current_occupancy_pct", "current_occupancy_pct", "REAL"),
    ("key_handover_date", "key_handover_date", "key_handover_date", "DATE"),
    ("tentative_handover_date", "tentative_handover_date", "tentative_handover_date", "DATE"),
    ("maintenance_charges", "maintenance_charges", "maintenance_charges", "REAL"),
    ("society_move_in_charges", "society_move_in_charges", "society_move_in_charges", "REAL"),
    ("electricity_charges", "electricity_charges", "electricity_charges", "REAL"),
    ("dg_charges", "dg_charges", "dg_charges", "REAL"),
    ("circle_rate", "circle_rate", "circle_rate", "REAL"),
    ("alpha_beta", "alpha_beta", "alpha_beta", "TEXT"),
    ("beta_pct", "beta_pct", "beta_pct", "REAL"),
    ("ama_payment_structure", None, "ama_payment_structure", "TEXT"),
    ("ama_beta_min_pct", "ama_beta_min_pct", "ama_beta_min_pct", "REAL"),
    ("ama_beta_max_pct", "ama_beta_max_pct", "ama_beta_max_pct", "REAL"),
    ("listing_asking_price", "listing_asking_price", "listing_asking_price", "REAL"),
    ("demand_price", "demand_price", "demand_price", "REAL"),
    ("gas_pipeline", "gas_pipeline", "gas_pipeline", "TEXT"),
    ("club_facility", "club_facility", "club_facility", "TEXT"),
    ("parking", "parking", "parking", "TEXT"),
    ("furnishing", "furnishing", "furnishing", "TEXT"),
    ("furnishing_details", "furnishing_details", "furnishing_details", "JSONB"),
    ("outstanding_loan", "outstanding_loan", "outstanding_loan", "REAL"),
    ("bank_name_loan", "bank_name_loan", "bank_name_loan", "TEXT"),
    ("documents_available", "documents_available", "documents_available", "JSONB"),
    ("ama_date", "ama_date", "ama_date", "DATE"),
    ("additional_images", "additional_images", "additional_images", "JSONB"),
    ("video_link", "video_link", "video_link", "TEXT"),
]

# Columns that come from the joined tables rather than the property itself.
JOINED_COLS = (
    "supply_status", "parking_number", "property_tax_status", "origin",
    "availability_status", "listing_price", "demand_status", "internal_remarks",
    "affordable", "micro_market",
)

TABLE_COLUMNS = text("""
    SELECT table_name, column_name FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name IN ('properties', 'legacy_properties')
""")


def _side(columns: dict[str, set[str]], table: str, sql_alias: str, which: int) -> str:
    """One side of the UNION: every output column, NULL-typed where the table lacks it."""
    have = columns[table]
    out = []
    for props_col, legacy_col, alias, typ in UNIFIED_COLS:
        col = props_col if which == 0 else legacy_col
        out.append(f'{sql_alias}."{col}"::{typ} AS "{alias}"' if col and col in have
                   else f'NULL::{typ} AS "{alias}"')
    return ",\n           ".join(out)


def build_sql(columns: dict[str, set[str]]) -> str:
    """The whole list, in one statement. Filtering and paging happen client-side, the
    way every other list page here works — 407 rows is not worth a query per keystroke."""
    # Their list hides a property they have replaced with a newer row.
    real_gate = "p.replicated IS NOT TRUE" if "replicated" in columns["properties"] else "TRUE"
    return f"""
        WITH unified AS (
            SELECT {_side(columns, 'properties', 'p', 0)},
                   apd.status::TEXT AS supply_status,
                   apd.parking_number::TEXT AS parking_number,
                   apd.property_tax_status::TEXT AS property_tax_status,
                   'real'::TEXT AS origin
              FROM properties p
              JOIN ap_details apd ON apd.uid = p.uid
             WHERE apd.status = ANY(:ready) AND {real_gate}
            UNION ALL
            SELECT {_side(columns, 'legacy_properties', 'lp', 1)},
                   lp.legacy_status::TEXT AS supply_status,
                   lp.parking_number::TEXT AS parking_number,
                   NULL::TEXT AS property_tax_status,
                   'legacy'::TEXT AS origin
              FROM legacy_properties lp
        )
        SELECT u.*,
               COALESCE(dd.availability_status, 'Available') AS availability_status,
               dd.listing_price, dd.demand_status, dd.internal_remarks,
               ms.affordable, ms.micro_market
          FROM unified u
          LEFT JOIN demand_details dd ON dd.uid = u.uid
          LEFT JOIN LATERAL (
              SELECT ms.affordable, ms.micro_market FROM master_societies ms
               WHERE LOWER(TRIM(ms.society_name)) = LOWER(TRIM(u.society_name)) LIMIT 1
          ) ms ON TRUE
         WHERE COALESCE(dd.availability_status, 'Available') <> 'Dead'
         ORDER BY u.society_name NULLS LAST, u.unit_no
    """


async def fetch_properties() -> dict:
    """Every ready-to-sell property with its demand-side row. One query, no writes."""
    engine = properties_engine()
    if engine is None:
        return {"status": "not_configured", "items": []}
    async with engine.connect() as conn:
        columns: dict[str, set[str]] = {"properties": set(), "legacy_properties": set()}
        for table, column in await conn.execute(TABLE_COLUMNS):
            columns[table].add(column)
        rows = (await conn.execute(text(build_sql(columns)),
                                   {"ready": list(SUPPLY_READY_STATUSES)})).mappings().all()
    return {"status": "ok", "items": [dict(r) for r in rows]}
