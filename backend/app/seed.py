"""Idempotent demo seed (check-before-insert) — `python -m app.seed`.

Creates: provisioned users (incl. support@openhouse.in as admin so the owner's
Google login works), Delhi-NCR societies/localities, ~25 leads across every
segment / TAT state / stage, inventory + supply units with coords & images,
reminders (incl. due-today), a completed visit with stops + a recording,
settings rows, an API key — then runs a full Gold Mine rematch.
"""
import asyncio
import hashlib
import secrets
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utcnow
from app.models import (
    ApiKey,
    Bucket,
    Interest,
    Inventory,
    Lead,
    LeadActivity,
    LeadConfirmedData,
    LeadPreferredLocality,
    LeadShortlistSociety,
    LeadSourceData,
    Locality,
    Recording,
    Reminder,
    SettingsIntegration,
    Society,
    SupplyUnit,
    Team,
    User,
    Visit,
    VisitStop,
)
from app.services import goldmine

UNSPLASH = "https://images.unsplash.com/{pid}?w=400"

USERS = [
    # (email, name, phone, role, in_team)
    ("support@openhouse.in", "Openhouse Support", "+91 9800000000", "admin", False),
    ("admin@openhouse.in", "Aditi Rathi", "+91 9800000001", "admin", False),
    ("cm@openhouse.in", "Chetan Madan", "+91 9800000002", "cm", True),
    ("rm1@openhouse.in", "Ravi Mishra", "+91 9800000003", "rm", True),
    ("rm2@openhouse.in", "Ritu Malhotra", "+91 9800000004", "rm", True),
    ("rm3@openhouse.in", "Raghav Mehra", "+91 9800000005", "rm", False),
]

SOCIETIES = [
    # (name, city, lat, lng)
    ("DLF The Crest", "Gurgaon", 28.4329, 77.1025),
    ("DLF Magnolias", "Gurgaon", 28.4536, 77.0980),
    ("M3M Golf Estate", "Gurgaon", 28.4090, 77.0648),
    ("Ireo Skyon", "Gurgaon", 28.4163, 77.0598),
    ("Pioneer Park", "Gurgaon", 28.4052, 77.0520),
    ("Emaar Palm Hills", "Gurgaon", 28.4233, 76.9648),
    ("ATS One Hamlet", "Noida", 28.5412, 77.3854),
    ("Gulshan Ikebana", "Noida", 28.4956, 77.4356),
    ("Godrej Woods", "Noida", 28.5663, 77.3452),
    ("Jaypee Greens Wish Town", "Noida", 28.5121, 77.3672),
    ("Gaur City 2", "Ghaziabad", 28.6071, 77.4300),
    ("ATS Advantage", "Ghaziabad", 28.6420, 77.3702),
    ("Prateek Grand City", "Ghaziabad", 28.6740, 77.3880),
]

LOCALITIES = [
    ("Golf Course Road", "Gurgaon"), ("Golf Course Extension", "Gurgaon"),
    ("Sohna Road", "Gurgaon"), ("Dwarka Expressway", "Gurgaon"),
    ("MG Road", "Gurgaon"), ("New Gurgaon", "Gurgaon"),
    ("Noida Expressway", "Noida"), ("Central Noida", "Noida"),
    ("Sector 150", "Noida"), ("Sector 104", "Noida"),
    ("Indirapuram", "Ghaziabad"), ("Raj Nagar Extension", "Ghaziabad"),
    ("Vaishali", "Ghaziabad"), ("Crossings Republik", "Ghaziabad"),
]

INVENTORY = [
    # (name, society, city, config, price, bmin, bmax, area, status, unsplash photo id)
    ("The Crest — 3 BHK Tower B", "DLF The Crest", "Gurgaon", "3 BHK", 195, 175, 215, 2010, "available", "photo-1560448204-e02f11c3d0e2"),
    ("The Crest — 4 BHK High Floor", "DLF The Crest", "Gurgaon", "4 BHK", 340, 320, 380, 2900, "resale", "photo-1512917774080-9991f1c4c750"),
    ("M3M Golf Estate — 3.5 BHK Fairway", "M3M Golf Estate", "Gurgaon", "3.5 BHK", 250, 230, 270, 2450, "available", "photo-1600596542815-ffad4c1539a9"),
    ("Ireo Skyon — 3 BHK Park View", "Ireo Skyon", "Gurgaon", "3 BHK", 145, 130, 160, 1850, "available", "photo-1568605114967-8130f3a36994"),
    ("Pioneer Park — 2 BHK", "Pioneer Park", "Gurgaon", "2 BHK", 98, 90, 110, 1380, "resale", "photo-1570129477492-45c003edd2be"),
    ("Emaar Palm Hills — 2 BHK Garden", "Emaar Palm Hills", "Gurgaon", "2 BHK", 92, 85, 105, 1310, "available", "photo-1580587771525-78b9dba3b914"),
    ("ATS One Hamlet — 2 BHK", "ATS One Hamlet", "Noida", "2 BHK", 88, 80, 95, 1250, "available", "photo-1600585154340-be6161a56a0c"),
    ("ATS One Hamlet — 3 BHK Corner", "ATS One Hamlet", "Noida", "3 BHK", 135, 120, 150, 1850, "resale", "photo-1600607687939-ce8a6c25118c"),
    ("Gulshan Ikebana — 3 BHK", "Gulshan Ikebana", "Noida", "3 BHK", 112, 100, 125, 1640, "available", "photo-1600566753190-17f0baa2a6c3"),
    ("Godrej Woods — 3 BHK Forest View", "Godrej Woods", "Noida", "3 BHK", 165, 150, 185, 1980, "available", "photo-1600585154526-990dced4db0d"),
    ("Gaur City 2 — 2 BHK", "Gaur City 2", "Ghaziabad", "2 BHK", 52, 45, 60, 1050, "available", "photo-1605276374104-dee2a0ed3cd6"),
    ("ATS Advantage — 3 BHK", "ATS Advantage", "Ghaziabad", "3 BHK", 98, 88, 112, 1550, "resale", "photo-1613490493576-7fde63acd811"),
]

SUPPLY = [
    # (name, society, city, config, price, bmin, bmax, area, stage, eta, photo id)
    ("DLF Magnolias — 4 BHK Resale", "DLF Magnolias", "Gurgaon", "4 BHK", 360, 330, 390, 3050, "negotiating", "Jul 2026", "photo-1613977257363-707ba9348227"),
    ("M3M Golf Estate — 3 BHK", "M3M Golf Estate", "Gurgaon", "3 BHK", 215, 200, 235, 2200, "msi", "Aug 2026", "photo-1564013799919-ab600027ffc6"),
    ("Ireo Skyon — 2 BHK", "Ireo Skyon", "Gurgaon", "2 BHK", 105, 95, 115, 1350, "token_paid", "Jul 2026", "photo-1494526585095-c41746248156"),
    ("Emaar Palm Hills — 3 BHK", "Emaar Palm Hills", "Gurgaon", "3 BHK", 118, 108, 130, 1690, "negotiating", "Jul 2026", "photo-1493809842364-78817add7ffb"),
    ("Jaypee Wish Town — 3 BHK", "Jaypee Greens Wish Town", "Noida", "3 BHK", 125, 115, 140, 1720, "negotiating", "Aug 2026", "photo-1522708323590-d24dbb6b0267"),
    ("Godrej Woods — 2 BHK", "Godrej Woods", "Noida", "2 BHK", 95, 88, 105, 1280, "token_paid", "Oct 2026", "photo-1560185007-cde436f6a4d0"),
    ("Gaur City 2 — 3 BHK", "Gaur City 2", "Ghaziabad", "3 BHK", 68, 60, 75, 1390, "msi", "Sep 2026", "photo-1560185127-6ed189bf02f4"),
    ("Prateek Grand City — 3 BHK", "Prateek Grand City", "Ghaziabad", "3 BHK", 72, 65, 80, 1480, "msi", "Sep 2026", "photo-1502672260266-1c1ef2d93688"),
]

# d = created days ago, h = created hours ago, m = created minutes ago; q = qualified days ago
LEADS = [
    # --- fresh / unconfirmed (segment: new) — TAT ok / warn / breach variety ---
    dict(name="Aarav Mehta", phone="+91 9810000001", source="meta", rm="rm1", stage="new", m=10,
         city="Gurgaon", society="DLF The Crest", config="3 BHK", band=(160, 220), plan="within_30_days"),
    dict(name="Priya Sharma", phone="+91 9810000002", source="gads", rm="rm2", stage="new", m=50,
         city="Gurgaon", society="M3M Golf Estate", config="3.5 BHK", band=(180, 260), plan="1_3_months"),
    dict(name="Rohit Verma", phone="+91 9810000003", source="99acres", rm="rm1", stage="new", h=3,
         city="Noida", society="ATS One Hamlet", config="2 BHK", band=(70, 90), plan="3_6_months"),
    dict(name="Sneha Kapoor", phone="+91 9810000004", source="magicbricks", rm="rm3", stage="new", h=26,
         city="Ghaziabad", society="Gaur City 2", config="2 BHK", band=(45, 60), plan="just_exploring"),
    dict(name="Vikram Singh", phone="+91 9810000005", source="whatsapp", rm="rm2", stage="new", m=30,
         city="Gurgaon", society="Ireo Skyon", config="3 BHK", band=(120, 160), plan="within_30_days"),
    dict(name="Ananya Iyer", phone="+91 9810000006", source="youtube", rm="rm3", stage="new", m=55,
         city="Noida", society="Gulshan Ikebana", config="3 BHK", band=(90, 120), plan="1_3_months"),
    dict(name="Karan Malhotra", phone="+91 9810000007", source="sheets", rm="rm1", stage="new", h=5,
         city="Gurgaon", society="Emaar Palm Hills", config="2 BHK", band=(80, 100), plan="3_6_months"),
    dict(name="Divya Nair", phone="+91 9810000008", source="api", rm="rm2", stage="new", m=20,
         city="Noida", society="Godrej Woods", config="3 BHK", band=(140, 180), plan="1_3_months"),
    dict(name="Harsh Gupta", phone="+91 9810000009", source="webhook", rm="rm1", stage="contacted", d=2,
         city="Ghaziabad", society="ATS Advantage", config="3 BHK", band=(85, 110), plan="just_exploring"),
    # --- qualified (<7 days since confirm) ---
    dict(name="Meera Joshi", phone="+91 9810000010", source="meta", rm="rm1", stage="contacted", d=3, q=2,
         city="Gurgaon", society="DLF The Crest", config="3 BHK", band=(170, 210), plan="within_30_days",
         conf=("self_use", 190, "3 BHK", "yes", 4), shortlist=["DLF The Crest", "DLF Magnolias"],
         localities=["Golf Course Road", "MG Road"]),
    dict(name="Arjun Reddy", phone="+91 9810000011", source="gads", rm="rm2", stage="visit_scheduled", d=5, q=3,
         city="Noida", society="ATS One Hamlet", config="2 BHK", band=(75, 95), plan="1_3_months",
         conf=("self_use", 85, "2 BHK", "maybe", 6), shortlist=["ATS One Hamlet", "Godrej Woods"],
         localities=["Noida Expressway", "Central Noida"]),
    dict(name="Ishaan Khanna", phone="+91 9810000012", source="99acres", rm="rm1", stage="negotiation", d=6, q=1,
         city="Gurgaon", society="M3M Golf Estate", config="3.5 BHK", band=(220, 280), plan="within_30_days",
         conf=("investment", 240, "3.5 BHK", "yes", 2), shortlist=["M3M Golf Estate", "Ireo Skyon"],
         localities=["Golf Course Extension", "Sohna Road"]),
    dict(name="Tanvi Desai", phone="+91 9810000013", source="magicbricks", rm="rm3", stage="contacted", d=6, q=4,
         city="Ghaziabad", society="Prateek Grand City", config="3 BHK", band=(65, 85), plan="3_6_months",
         conf=("self_use", 75, "3 BHK", "no", None), shortlist=["Prateek Grand City"],
         localities=["Raj Nagar Extension"]),
    dict(name="Nikhil Bansal", phone="+91 9810000014", source="whatsapp", rm="rm2", stage="visit_feedback", d=7, q=2,
         city="Noida", society="Gulshan Ikebana", config="3 BHK", band=(100, 125), plan="1_3_months",
         conf=("self_use", 110, "3 BHK", "yes", 3), shortlist=["Gulshan Ikebana", "Godrej Woods"],
         localities=["Noida Expressway", "Sector 150"]),
    dict(name="Riya Chopra", phone="+91 9810000015", source="meta", rm="rm1", stage="contacted", d=8, q=6,
         city="Gurgaon", society="Pioneer Park", config="2 BHK", band=(85, 105), plan="1_3_months",
         conf=("investment", 95, "2 BHK", "maybe", 5), shortlist=["Pioneer Park", "Emaar Palm Hills"],
         localities=["Sohna Road"]),
    # --- pipeline (>=7 days since confirm, auto-aged) ---
    dict(name="Aditya Rao", phone="+91 9810000016", source="gads", rm="rm2", stage="negotiation", d=10, q=8,
         city="Gurgaon", society="Ireo Skyon", config="3 BHK", band=(135, 165), plan="1_3_months",
         conf=("self_use", 150, "3 BHK", "yes", None), shortlist=["Ireo Skyon"],
         localities=["Golf Course Extension"]),
    dict(name="Kavya Menon", phone="+91 9810000017", source="meta", rm="rm1", stage="contacted", d=14, q=12,
         city="Noida", society="Godrej Woods", config="3 BHK", band=(150, 185), plan="3_6_months",
         conf=("self_use", 160, "3 BHK", "maybe", 9), shortlist=["Godrej Woods", "Jaypee Greens Wish Town"],
         localities=["Central Noida"]),
    dict(name="Saurabh Jain", phone="+91 9810000018", source="99acres", rm="rm3", stage="visit_feedback", d=16, q=15,
         city="Ghaziabad", society="Gaur City 2", config="2 BHK", band=(48, 62), plan="3_6_months",
         conf=("investment", 55, "2 BHK", "no", None), shortlist=["Gaur City 2"],
         localities=["Crossings Republik"]),
    dict(name="Pooja Agarwal", phone="+91 9810000019", source="magicbricks", rm="rm2", stage="contacted", d=22, q=20,
         city="Gurgaon", society="Emaar Palm Hills", config="2 BHK", band=(82, 100), plan="just_exploring",
         conf=("self_use", 90, "2 BHK", "maybe", 12), shortlist=["Emaar Palm Hills", "Pioneer Park"],
         localities=["New Gurgaon", "Dwarka Expressway"]),
    dict(name="Dhruv Saxena", phone="+91 9810000020", source="whatsapp", rm="rm1", stage="visit_scheduled", d=11, q=9,
         city="Noida", society="ATS One Hamlet", config="2 BHK", band=(80, 96), plan="1_3_months", hot=True,
         conf=("self_use", 88, "2 BHK", "yes", 1), shortlist=["ATS One Hamlet"],
         localities=["Sector 104"]),
    # --- converted / terminal ---
    dict(name="Neha Kulkarni", phone="+91 9810000021", source="meta", rm="rm1", stage="won", d=30, q=25,
         city="Gurgaon", society="DLF Magnolias", config="4 BHK", band=(320, 400), plan="within_30_days",
         conf=("self_use", 350, "4 BHK", "yes", None), shortlist=["DLF Magnolias", "DLF The Crest"],
         localities=["Golf Course Road"]),
    dict(name="Rajat Khurana", phone="+91 9810000022", source="gads", rm="rm2", stage="won", d=45, q=40,
         city="Noida", society="Jaypee Greens Wish Town", config="3 BHK", band=(115, 145), plan="1_3_months",
         conf=("investment", 130, "3 BHK", "yes", None), shortlist=["Jaypee Greens Wish Town"],
         localities=["Noida Expressway"]),
    dict(name="Simran Kaur", phone="+91 9810000023", source="99acres", rm="rm3", stage="lost", d=20, q=18,
         city="Ghaziabad", society="ATS Advantage", config="3 BHK", band=(85, 105), plan="1_3_months",
         conf=("self_use", 95, "3 BHK", "no", None), shortlist=["ATS Advantage"],
         localities=["Indirapuram"]),
    dict(name="Manish Tiwari", phone="+91 9810000024", source="youtube", rm="rm2", stage="timepass", d=12,
         city="Gurgaon", society="M3M Golf Estate", config="2 BHK", band=(60, 80), plan="just_exploring"),
    dict(name="Alok Pandey", phone="+91 9810000025", source="sheets", rm="rm1", stage="future_prospect", d=35, q=30,
         city="Noida", society="Gulshan Ikebana", config="3 BHK", band=(95, 120), plan="3_6_months",
         conf=("investment", 105, "3 BHK", "maybe", 45), shortlist=["Gulshan Ikebana"],
         localities=["Sector 150"]),
]

INSIGHTS = [
    ("DLF The Crest", "Gurgaon", "Buyers repeatedly ask for RERA status, exact possession date and club-membership costs."),
    ("Gaur City 2", "Ghaziabad", "Strong first-time-buyer demand; home-loan pre-approval support closes faster."),
    ("ATS One Hamlet", "Noida", "Buyers prefer high floors and park-facing units; east-facing sells at a premium."),
]

SETTINGS_ROWS = [
    ("meta", {"label": "Meta Lead Ads"}, True),
    ("gads", {"label": "Google Ads"}, True),
    ("99acres", {"label": "99acres"}, False),
    ("magicbricks", {"label": "MagicBricks"}, True),
    ("youtube", {"label": "YouTube"}, False),
    ("whatsapp", {"label": "WhatsApp Cloud API"}, True),
    ("sheets", {"label": "Google Sheets"}, True),
    ("webhook_url", {"url": "https://api.openhouse.in/v1/leads/ingest"}, True),
    ("assignment", {"method": "round_robin"}, True),
    ("tat_config", {"default": 60, "per_source": {"whatsapp": 30}}, True),
]

_COORDS = {name: (lat, lng) for name, _, lat, lng in SOCIETIES}


def _band_label(band: tuple | None) -> str | None:
    if band is None:
        return None
    return f"₹{band[0]}L – ₹{band[1]}L"


async def seed(session: AsyncSession) -> dict:
    now = utcnow()

    # --- team + users ---
    team = (await session.execute(select(Team).where(Team.name == "Team Gurgaon"))).scalar_one_or_none()
    if team is None:
        team = Team(name="Team Gurgaon")
        session.add(team)
        await session.flush()

    users: dict[str, User] = {}
    for email, name, phone, role, in_team in USERS:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(name=name, phone=phone, email=email, role=role,
                        team_id=team.id if in_team else None, active=True)
            session.add(user)
            await session.flush()
        users[email.split("@")[0]] = user
    if team.cm_user_id is None:
        team.cm_user_id = users["cm"].id

    # --- reference societies / localities ---
    for name, city, _lat, _lng in SOCIETIES:
        exists_ = (
            await session.execute(select(Society).where(Society.name == name, Society.city == city))
        ).scalar_one_or_none()
        if exists_ is None:
            session.add(Society(name=name, city=city))
    for name, city in LOCALITIES:
        exists_ = (
            await session.execute(select(Locality).where(Locality.name == name, Locality.city == city))
        ).scalar_one_or_none()
        if exists_ is None:
            session.add(Locality(name=name, city=city))

    # --- settings + api key ---
    for key, value, enabled in SETTINGS_ROWS:
        row = await session.get(SettingsIntegration, key)
        if row is None:
            session.add(SettingsIntegration(key=key, value=value, enabled=enabled))
    has_key = (await session.execute(select(ApiKey).limit(1))).scalar_one_or_none()
    if has_key is None:
        session.add(
            ApiKey(
                label="Production key",
                hash=hashlib.sha256(b"oh_live_demo_key").hexdigest(),
                revoked=False,
                created_by=users["admin"].id,
            )
        )

    # --- inventory / supply units ---
    inv_by_name: dict[str, Inventory] = {}
    for i, (name, society, city, config, price, bmin, bmax, area, status, pid) in enumerate(INVENTORY):
        unit = (await session.execute(select(Inventory).where(Inventory.name == name))).scalar_one_or_none()
        if unit is None:
            lat, lng = _COORDS[society]
            unit = Inventory(
                name=name, society=society, city=city, configuration=config,
                price_lacs=float(price), budget_min_lacs=float(bmin), budget_max_lacs=float(bmax),
                budget_band=_band_label((bmin, bmax)), area_sqft=float(area), status=status,
                lat=lat + (i % 5) * 0.0011, lng=lng + (i % 7) * 0.0009,
                image_url=UNSPLASH.format(pid=pid), ext_source="acquired_property", synced_at=now,
            )
            session.add(unit)
            await session.flush()
        inv_by_name[name] = unit

    supply_by_name: dict[str, SupplyUnit] = {}
    for i, (name, society, city, config, price, bmin, bmax, area, stage, eta, pid) in enumerate(SUPPLY):
        unit = (await session.execute(select(SupplyUnit).where(SupplyUnit.name == name))).scalar_one_or_none()
        if unit is None:
            lat, lng = _COORDS[society]
            unit = SupplyUnit(
                name=name, society=society, city=city, configuration=config,
                price_lacs=float(price), budget_min_lacs=float(bmin), budget_max_lacs=float(bmax),
                budget_band=_band_label((bmin, bmax)), area_sqft=float(area),
                supply_stage=stage, eta=eta,
                lat=lat - (i % 4) * 0.0013, lng=lng - (i % 6) * 0.0008,
                image_url=UNSPLASH.format(pid=pid), ext_source="supply_tracker", synced_at=now,
            )
            session.add(unit)
            await session.flush()
        supply_by_name[name] = unit

    # --- leads ---
    leads_by_phone: dict[str, Lead] = {}
    for spec in LEADS:
        lead = (await session.execute(select(Lead).where(Lead.phone == spec["phone"]))).scalar_one_or_none()
        if lead is None:
            created_at = now - timedelta(
                days=spec.get("d", 0), hours=spec.get("h", 0), minutes=spec.get("m", 0)
            )
            confirmed = "conf" in spec
            qualified_at = now - timedelta(days=spec["q"]) if "q" in spec else None
            is_hot = bool(spec.get("hot")) or spec.get("plan") == "within_30_days"
            lead = Lead(
                name=spec["name"], phone=spec["phone"], source=spec["source"],
                assigned_to=users[spec["rm"]].id, stage=spec["stage"],
                tat_deadline=None if confirmed else created_at + timedelta(minutes=60),
                confirmed=confirmed, qualified_at=qualified_at, is_hot=is_hot,
                city=spec["city"], created_at=created_at,
            )
            session.add(lead)
            await session.flush()
            session.add(
                LeadSourceData(
                    lead_id=lead.id, budget_band=_band_label(spec.get("band")),
                    budget_min_lacs=float(spec["band"][0]) if spec.get("band") else None,
                    budget_max_lacs=float(spec["band"][1]) if spec.get("band") else None,
                    city=spec["city"], society=spec.get("society"),
                    configuration=spec.get("config"), plan_to_buy=spec.get("plan"),
                )
            )
            session.add(
                LeadActivity(
                    lead_id=lead.id, event="lead_ingested",
                    remark=f"Lead captured from {spec['source']}", created_at=created_at,
                )
            )
            if confirmed:
                purpose, value, config, office, office_days = spec["conf"]
                session.add(
                    LeadConfirmedData(
                        lead_id=lead.id, purpose=purpose, budget_value_lacs=float(value),
                        configuration=config, office_willing=office,
                        office_preferred_date=(
                            (now + timedelta(days=office_days)).date() if office_days is not None else None
                        ),
                        remark="Confirmed on qualification call", confirmed_at=qualified_at,
                    )
                )
                for society in spec.get("shortlist", []):
                    session.add(LeadShortlistSociety(lead_id=lead.id, society=society))
                for locality in spec.get("localities", []):
                    session.add(LeadPreferredLocality(lead_id=lead.id, locality=locality))
                session.add(
                    LeadActivity(
                        lead_id=lead.id, event="confirmed",
                        remark="Lead confirmed & qualified on call (Q1–Q6)",
                        actor_id=users[spec["rm"]].id, created_at=qualified_at,
                    )
                )
                if spec["stage"] not in ("contacted",):
                    session.add(
                        LeadActivity(
                            lead_id=lead.id, event="stage_changed",
                            remark=f"contacted → {spec['stage']}: progressed after follow-up",
                            actor_id=users[spec["rm"]].id,
                            created_at=qualified_at + timedelta(hours=8),
                        )
                    )
        leads_by_phone[spec["phone"]] = lead

    def lead_of(name: str) -> Lead:
        spec = next(s for s in LEADS if s["name"] == name)
        return leads_by_phone[spec["phone"]]

    # --- reminders (incl. due-today + overdue) ---
    reminder_specs = [
        (lead_of("Meera Joshi"), "follow_up", "Send Crest brochure and call back", now + timedelta(minutes=45), False, False),
        (lead_of("Ishaan Khanna"), "negotiation", "Confirm token amount with seller", now + timedelta(hours=2), False, False),
        (lead_of("Aditya Rao"), "negotiation", "Re-negotiate Skyon asking price", now - timedelta(hours=26), False, False),
        (lead_of("Arjun Reddy"), "visit_schedule", "Plan ATS One Hamlet site visit", now + timedelta(days=1), False, False),
        (lead_of("Nikhil Bansal"), "visit_feedback", "Collect visit feedback from Nikhil Bansal", now - timedelta(days=2) + timedelta(hours=2), True, True),
    ]
    for lead, rtype, note, due_at, done, auto in reminder_specs:
        exists_ = (
            await session.execute(
                select(Reminder).where(Reminder.lead_id == lead.id, Reminder.type == rtype).limit(1)
            )
        ).scalar_one_or_none()
        if exists_ is None:
            session.add(
                Reminder(lead_id=lead.id, type=rtype, note=note, due_at=due_at,
                         done=done, auto_generated=auto, notified=done)
            )

    # --- a completed visit with stops + a recording ---
    nikhil = lead_of("Nikhil Bansal")
    visit = (
        await session.execute(select(Visit).where(Visit.lead_id == nikhil.id).limit(1))
    ).scalar_one_or_none()
    if visit is None:
        visit = Visit(
            lead_id=nikhil.id, trip_date=(now - timedelta(days=2)).date(), rm_id=users["rm2"].id,
            total_km=14.2, total_min=38, route_source="est",
            self_schedule_token=secrets.token_urlsafe(16), status="completed",
        )
        session.add(visit)
        await session.flush()
        session.add(VisitStop(visit_id=visit.id, inventory_id=inv_by_name["Gulshan Ikebana — 3 BHK"].id, seq=1))
        session.add(VisitStop(visit_id=visit.id, inventory_id=inv_by_name["Godrej Woods — 3 BHK Forest View"].id, seq=2))
        session.add(
            LeadActivity(
                lead_id=nikhil.id, event="visit_scheduled",
                remark="2-stop visit planned (14.2 km, 38 min, est)", actor_id=users["rm2"].id,
                created_at=now - timedelta(days=3),
            )
        )
    has_rec = (
        await session.execute(select(Recording).where(Recording.lead_id == nikhil.id).limit(1))
    ).scalar_one_or_none()
    if has_rec is None:
        session.add(
            Recording(
                lead_id=nikhil.id, visit_id=visit.id,
                file_ref="recordings/visit-nikhil-bansal.mp3", duration_sec=412,
                recorded_by=users["rm2"].id, recorded_at=now - timedelta(days=2) + timedelta(hours=3),
            )
        )

    # --- buyer interests on supply units ---
    interest_specs = [
        (supply_by_name["M3M Golf Estate — 3 BHK"], lead_of("Ishaan Khanna"), users["rm1"], "Buyer ready at ₹2.3 Cr"),
        (supply_by_name["Jaypee Wish Town — 3 BHK"], lead_of("Kavya Menon"), users["rm1"], "Wants possession this year"),
        (supply_by_name["Gaur City 2 — 3 BHK"], None, users["rm3"], "Two walk-in buyers asking for this tower"),
    ]
    for unit, lead, rm, note in interest_specs:
        exists_ = (
            await session.execute(
                select(Interest).where(Interest.supply_unit_id == unit.id, Interest.rm_id == rm.id).limit(1)
            )
        ).scalar_one_or_none()
        if exists_ is None:
            session.add(Interest(supply_unit_id=unit.id, lead_id=lead.id if lead else None, rm_id=rm.id, note=note))

    # --- society insights ---
    from app.models import SocietyInsight

    for society, city, note in INSIGHTS:
        exists_ = (
            await session.execute(
                select(SocietyInsight).where(SocietyInsight.society == society, SocietyInsight.note == note)
            )
        ).scalar_one_or_none()
        if exists_ is None:
            session.add(SocietyInsight(society=society, city=city, note=note, created_by=users["cm"].id))

    await session.commit()

    # --- gold mine: full rematch over everything just seeded ---
    buckets = await goldmine.rematch(session)

    async def count(model) -> int:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()

    return {
        "users": await count(User),
        "leads": await count(Lead),
        "inventory": await count(Inventory),
        "supply_units": await count(SupplyUnit),
        "reminders": await count(Reminder),
        "buckets": buckets,
        "societies": await count(Society),
        "localities": await count(Locality),
    }


async def _main() -> None:
    from app.db import SessionLocal, engine

    async with SessionLocal() as session:
        summary = await seed(session)
    await engine.dispose()
    print("Seed complete:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(_main())
