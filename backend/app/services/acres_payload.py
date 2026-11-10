"""A Demand Dashboard property → the 99acres listing payload. Pure: no network, no DB.

The field map is docs/99acres-api.md, checked against the one payload 99acres has
accepted (E95607134, 5 Nov). Spec: docs/superpowers/specs/2026-11-05-99acres-listing-design.md.

`build_payload` returns (payload, problems). A problem makes the property not postable and
is shown to the admin as written; an OPTIONAL field that is blank is simply left out. Every
value is a string (as in the accepted payload) except PhotosData, which is a list.

Map pin and age come from the properties DB's master_societies (latitude, longitude,
possession_year — the user fills them), never from a guess: a public listing with an
invented age or a sector-centroid pin is worse than one that waits.
"""
import json
import re

AGE_IDS = {"6": "0–1 yrs", "1": "1–5 yrs", "2": "5–10 yrs", "3": "10+ yrs"}
OWNTYPE_IDS = {"1": "Freehold", "2": "Leasehold", "3": "Co-operative society", "4": "Power of attorney"}

# The book files these under city "Noida"; 99acres has Greater Noida as its own city (user, 5 Nov).
# Gr Noida Expressway stays Noida — those sectors are Noida's.
GREATER_NOIDA_MARKETS = frozenset({"Gr Noida West - 1", "Gr Noida West - 2", "Gaur City", "Gr Noida"})
CITY_IDS = {"noida": "7", "gurgaon": "8", "ghaziabad": "9"}

FACING_IDS = {"north": "1", "south": "2", "east": "3", "west": "4",
              "north-east": "5", "north-west": "6", "south-east": "7", "south-west": "8"}
FURNISH_IDS = {"fully furnished": "1", "semi-furnished": "4", "unfurnished": "2"}

SLOT_ORDER = ("living_room", "bedrooms", "kitchen", "bathrooms", "balconies", "extra_area")
# ponytail: guessed tags — the only one 99acres has ever documented is BUILDING (their tag
# lookup API is 404 now). 99acres refuses a bad tag before saving, so the first photo post
# settles this dict; fix it here and nowhere else.
SLOT_TAG = {"living_room": "LIVING_ROOM", "bedrooms": "BEDROOM", "kitchen": "KITCHEN",
            "bathrooms": "BATHROOM", "balconies": "BALCONY", "extra_area": "OTHERS"}

PRICE_MIN, PRICE_MAX = 25_000, 9_999_999_999
# A possession year after this year (under construction) is listed as 2024 — user ruling 10 Nov.
# Applied here only; master_societies keeps the real year.
FUTURE_POSSESSION_AS = 2024
_NOT_ALLOWED = re.compile(r"[^A-Za-z0-9 .;'/\\\-()]")   # 99acres: only . ; ' / \ - ( ) in Description
_BHK = re.compile(r"^(\d+(?:\.5)?)(?:\.0)?\s*BHK", re.IGNORECASE)


def city_id(city: str | None, micro_market: str | None) -> str | None:
    c = (city or "").strip().lower()
    if c == "noida" and (micro_market or "").strip() in GREATER_NOIDA_MARKETS:
        return "222"
    return CITY_IDS.get(c)


def age_band(possession_year: int | None, year: int) -> str | None:
    if possession_year is None:
        return None
    years = year - int(possession_year)
    if years < 0:
        return None
    return "6" if years < 1 else "1" if years < 5 else "2" if years < 10 else "3"


def _config(configuration: str | None) -> str:
    """'2.0BHK' → '2 BHK', '2 BHK + Study' → '2 BHK with Study' ('+' is not allowed text)."""
    return _BHK.sub(r"\1 BHK", (configuration or "").strip()).replace(" + ", " with ")


def _alnum(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def lookalike_key(p: dict) -> tuple[str, str, float | None]:
    """Different flats 99acres may still call duplicates: same society, BHK and area."""
    return (_alnum(p.get("society_name")), _alnum(_config(p.get("configuration"))), p.get("area_sqft"))


def _floor(floor, total: int | None) -> tuple[str | None, str | None]:
    """(Floor_Num, description clause) — None when the floor can't be read."""
    s = str(floor or "").strip().lower()
    if s.isdigit() and int(s) > 0:
        n = int(s)
        return ("41" if n > 40 else str(n)), (f"Floor {n} of {total}" if total else f"Floor {n}")
    if s in ("ground", "0"):
        return "G", (f"Ground floor of {total}" if total else "Ground floor")
    if s == "top" and total:
        return str(min(total, 41)), f"Floor {total} of {total}"
    return None, None


def _parking(wording: str | None) -> tuple[str | None, str | None, str | None]:
    """(Reserved_Parking JSON string, description clause, problem)."""
    s = (wording or "").strip()
    if not s or s.lower() == "no parking":
        return None, None, None
    if s.lower() == "stilt parking":
        return '{"C":1}', "stilt parking", None   # stilt is covered (my call, spec)
    counts: dict[str, int] = {}
    for part in s.split("+"):
        m = re.fullmatch(r"\s*(\d+)\s+(open|closed|covered)\s*", part, re.IGNORECASE)
        if not m:
            return None, None, f"Parking wording '{s}' not understood"
        key = "O" if m[2].lower() == "open" else "C"
        counts[key] = counts.get(key, 0) + int(m[1])
    ordered = {k: counts[k] for k in ("C", "O") if k in counts}
    c, o = ordered.get("C"), ordered.get("O")
    clause = (f"{o} open and {c} covered parking" if c and o
              else f"{c} covered parking" if c else f"{o} open parking")
    return json.dumps(ordered, separators=(",", ":")), clause, None


def _photos(photos: list[dict]) -> list[dict]:
    def key(ph):
        kind, _, rest = (ph.get("slot_id") or "").partition(":")
        m = re.match(r"(\d+)", rest)
        rank = SLOT_ORDER.index(kind) if kind in SLOT_ORDER else len(SLOT_ORDER)
        return (rank, int(m[1]) if m else 0, rest.endswith("-view"))

    shots = sorted((ph for ph in photos if str(ph.get("url") or "").startswith("https://")), key=key)
    return [{"path": ph["url"], "type": SLOT_TAG.get((ph.get("slot_id") or "").partition(":")[0], "OTHERS"),
             "cover_photo": "Y" if i == 0 else "N"} for i, ph in enumerate(shots)]


def build_payload(p: dict, *, photos: list[dict], owntype: str | None, society: dict | None,
                  year: int) -> tuple[dict[str, str | list], list[str]]:
    problems: list[str] = []
    pay: dict[str, str | list] = {"Res_Com": "R", "Mode": "S", "Type": "1", "Transact_Type": "1",
                                  "Availability": "I", "Is_Price_Negotiable": "Y"}

    city = city_id(p.get("city"), p.get("micro_market"))
    if city:
        pay["City"] = city
    else:
        problems.append(f"City '{p.get('city')}' has no 99acres id")

    locality = (p.get("locality") or "").strip()
    if 2 <= len(locality) <= 75:
        pay["Locality"] = locality
    else:
        problems.append("Locality missing or longer than 75 characters")
    name = (p.get("society_name") or "").strip()
    if name and len(name) <= 50:
        pay["Prop_Name"] = name
    else:
        problems.append("Society name missing or longer than 50 characters")

    if society is None:
        problems.append("Society not found in master_societies")
    else:
        lat, lng = society.get("latitude"), society.get("longitude")
        if lat is None or lng is None:
            problems.append("No map pin in master_societies")
        else:
            pay |= {"Latitude": str(lat), "Longitude": str(lng), "Map_Source": "user_moves",
                    "Map_Status": "MAPPED", "ZoomLevel": "16"}
        py = society.get("possession_year")
        if py is not None and int(py) > year:
            py = FUTURE_POSSESSION_AS   # user ruling 10 Nov; master_societies keeps the real year
        band = age_band(py, year)
        if py is None:
            problems.append("No possession year in master_societies")
        else:
            pay["Age"] = band

    if owntype in OWNTYPE_IDS:
        pay["Owntype"] = owntype
    else:
        problems.append("Ownership not set")

    m = re.match(r"\s*(\d+)", p.get("configuration") or "")
    if m and int(m[1]) > 0:
        pay["Bedroom_Num"] = str(min(int(m[1]), 10))
    else:
        problems.append(f"Configuration '{p.get('configuration')}' not understood")
    if p.get("bathrooms"):
        pay["Bathroom_Num"] = str(int(p["bathrooms"]))
    else:
        problems.append("Bathrooms missing")
    if p.get("balconies") is not None:
        pay["Balcony_Num"] = str(min(int(p["balconies"]), 4))

    total = p.get("total_floors_tower")
    total = int(total) if total is not None else None
    if total and total >= 1:
        pay["Total_Floor"] = str(min(total, 41))
    else:
        problems.append("Total floors missing")
    floor_num, floor_clause = _floor(p.get("floor"), total)
    if floor_num:
        pay["Floor_Num"] = floor_num
    else:
        problems.append("Floor missing or not understood")

    parking, parking_clause, problem = _parking(p.get("parking"))
    if parking:
        pay["Reserved_Parking"] = parking
    if problem:
        problems.append(problem)

    furnishing = (p.get("furnishing") or "").strip()
    if furnishing:
        if furnishing.lower() in FURNISH_IDS:
            pay["Furnish"] = FURNISH_IDS[furnishing.lower()]
        else:
            problems.append(f"Furnishing '{furnishing}' not understood")

    lp = p.get("listing_price")
    if lp is None:
        problems.append("Price missing")
    else:
        # listing_price is REAL (float4): 156.6 arrives as 156.600006…, which would list at
        # ₹1,56,60,001. Rounding the lakh figure to ₹100 first keeps the price as entered.
        rupees = round(round(float(lp), 3) * 100_000)
        if PRICE_MIN <= rupees <= PRICE_MAX:
            pay["Price"] = str(rupees)
        else:
            problems.append(f"Price ₹{rupees:,} is outside 99acres' range")

    area = p.get("area_sqft")
    if area and area > 0:
        pay |= {"Superbuiltup_Area": str(round(area)), "Superbuiltuparea_Unit": "1"}
    else:
        problems.append("Area missing")
    if p.get("carpet_area") and p["carpet_area"] > 0:
        pay |= {"Carpet_Area": str(round(p["carpet_area"])), "Carpetarea_Unit": "1"}

    facing = (p.get("exit_facing") or "").strip()
    if facing.lower() in FACING_IDS:
        pay["Facing"] = FACING_IDS[facing.lower()]
    else:
        problems.append(f"Facing '{facing}' not understood")

    head = " ".join(x for x in (_config(p.get("configuration")), furnishing.lower(), "apartment in", name) if x)
    clauses = "; ".join(x for x in (floor_clause, f"{facing} facing" if facing else None, parking_clause) if x)
    # City 222 is filed as "Noida" in the book; a public listing must not say so.
    place = "Greater Noida" if city == "222" else (p.get("city") or "").strip()
    desc = f"{head}; {locality} {place}." + (f" {clauses}." if clauses else "")
    desc = re.sub(r"\s+", " ", _NOT_ALLOWED.sub(" ", desc)).strip()
    if 30 <= len(desc) <= 5000:
        pay["Description"] = desc
    else:
        problems.append("Description shorter than 30 characters")

    shots = _photos(photos)
    if shots:
        pay["PhotosData"] = shots
    return pay, problems
