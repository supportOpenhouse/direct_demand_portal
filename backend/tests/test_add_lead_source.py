"""Add lead asks where the buyer came from.

A hand-added lead's `source` is whatever was picked — Meta, 99acres, … or free text.
Its origin_key and source_category stay `manual`: that is how the row ENTERED, and it
keeps a real Meta/sheet arrival for the same number merging into it rather than
colliding with a hand-made `meta:<phone>` key.
"""
import re
from pathlib import Path

from app.routers.leads import KNOWN_SOURCES, NewLead, canonical_source

LEADS_TS = Path(__file__).parents[2] / "frontend" / "src" / "lib" / "leads.ts"


def test_blank_means_manual_so_an_older_frontend_still_works():
    # a client deployed before this change sends no `source` at all
    assert NewLead(name="A", phone="9876543210").source is None
    for blank in (None, "", "   "):
        assert canonical_source(blank) == "manual"


def test_a_known_source_in_any_spelling_maps_onto_its_key():
    """Otherwise a typed "Meta" is a second Meta no filter groups with the first."""
    for raw, key in [("meta", "meta"), ("Meta", "meta"), ("META", "meta"),
                     ("Magic Bricks", "magicbricks"), ("magic-bricks", "magicbricks"),
                     ("99acres", "99acres"), ("Google Ads", "gads"), ("WhatsApp", "whatsapp")]:
        assert canonical_source(raw) == key, raw


def test_a_new_source_is_kept_as_typed():
    assert canonical_source("Walk-in") == "Walk-in"
    assert canonical_source("  Channel   partner ") == "Channel partner"


def test_the_row_is_still_recognisably_hand_added():
    src = Path(__file__).parents[1].joinpath("app", "routers", "leads.py").read_text()
    assert "async def create_lead" in src, "handler renamed — point this test at it"
    body = src.split("async def create_lead", 1)[1].split("\n@router", 1)[0]
    assert 'key = f"manual:{phone10}"' in body
    assert 'source_category="manual", source=canonical_source(payload.source)' in body


def test_the_backend_knows_every_source_the_frontend_labels():
    """KNOWN_SOURCES mirrors SRC_LABEL. A key in one and not the other is a source the
    form offers that the server stores as free text, or a label the chips never use."""
    ts = LEADS_TS.read_text()
    block = ts.split("const SRC_LABEL", 1)[1].split("};", 1)[0]
    ts_keys = set(re.findall(r'^\s*"?([\w]+)"?\s*:', block, re.M))
    assert ts_keys == set(KNOWN_SOURCES), f"drift: {ts_keys ^ set(KNOWN_SOURCES)}"
