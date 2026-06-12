"""ORM -> wire-shape (docs/API_CONTRACT.md) serializers. snake_case dicts;
datetimes stay timezone-aware (TZDateTime) and FastAPI encodes them as ISO-8601 UTC."""
from datetime import datetime

from app.services.tat import compute_tat


def fmt_lacs(v: float | None) -> str | None:
    if v is None:
        return None
    v = float(v)
    return f"₹{int(v)}L" if v == int(v) else f"₹{v:g}L"


def budget_label(lead) -> str | None:
    conf = lead.confirmed_data
    if conf is not None and conf.budget_value_lacs is not None:
        return fmt_lacs(conf.budget_value_lacs)
    src = lead.source_data
    if src is None:
        return None
    if src.budget_band:
        return src.budget_band
    if src.budget_min_lacs is not None and src.budget_max_lacs is not None:
        return f"{fmt_lacs(src.budget_min_lacs)} – {fmt_lacs(src.budget_max_lacs)}"
    if src.budget_min_lacs is not None:
        return f"{fmt_lacs(src.budget_min_lacs)}+"
    if src.budget_max_lacs is not None:
        return f"Up to {fmt_lacs(src.budget_max_lacs)}"
    return None


def assigned_to_payload(user) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.id), "name": user.name}


def user_payload(user) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "team_id": str(user.team_id) if user.team_id else None,
        "team_name": user.team.name if user.team is not None else None,
        "active": user.active,
    }


def lead_row(lead, now: datetime) -> dict:
    src = lead.source_data
    conf = lead.confirmed_data
    configuration = None
    if conf is not None and conf.configuration:
        configuration = conf.configuration
    elif src is not None:
        configuration = src.configuration
    return {
        "id": str(lead.id),
        "name": lead.name,
        "phone": lead.phone,
        "source": lead.source,
        "stage": lead.stage,
        "is_hot": lead.is_hot,
        "confirmed": lead.confirmed,
        "city": lead.city or (src.city if src is not None else None),
        "society": src.society if src is not None else None,
        "configuration": configuration,
        "budget_label": budget_label(lead),
        "plan_to_buy": src.plan_to_buy if src is not None else None,
        "assigned_to": assigned_to_payload(lead.assignee),
        "tat": compute_tat(lead, now),
        "qualified_at": lead.qualified_at,
        "created_at": lead.created_at,
    }


def source_data_payload(src) -> dict:
    if src is None:
        return {
            "budget_band": None, "budget_min_lacs": None, "budget_max_lacs": None,
            "city": None, "society": None, "configuration": None, "plan_to_buy": None,
        }
    return {
        "budget_band": src.budget_band,
        "budget_min_lacs": src.budget_min_lacs,
        "budget_max_lacs": src.budget_max_lacs,
        "city": src.city,
        "society": src.society,
        "configuration": src.configuration,
        "plan_to_buy": src.plan_to_buy,
    }


def confirmed_data_payload(conf) -> dict | None:
    if conf is None:
        return None
    return {
        "purpose": conf.purpose,
        "budget_value_lacs": conf.budget_value_lacs,
        "configuration": conf.configuration,
        "office_willing": conf.office_willing,
        "office_preferred_date": conf.office_preferred_date,
        "remark": conf.remark,
        "confirmed_at": conf.confirmed_at,
    }


def activity_payload(a) -> dict:
    return {
        "id": str(a.id),
        "event": a.event,
        "remark": a.remark,
        "actor_name": a.actor.name if a.actor is not None else None,
        "created_at": a.created_at,
    }


def recording_payload(rec) -> dict:
    return {
        "id": str(rec.id),
        "visit_id": str(rec.visit_id) if rec.visit_id else None,
        "file_ref": rec.file_ref,
        "duration_sec": rec.duration_sec,
        "recorded_by_name": rec.recorded_by_user.name if rec.recorded_by_user is not None else None,
        "recorded_at": rec.recorded_at,
    }


def visit_payload(visit) -> dict:
    return {
        "id": str(visit.id),
        "trip_date": visit.trip_date,
        "rm": assigned_to_payload(visit.rm),
        "total_km": visit.total_km,
        "total_min": visit.total_min,
        "route_source": visit.route_source,
        "status": visit.status,
        "stops": [
            {
                "seq": s.seq,
                "inventory_id": str(s.inventory_id),
                "name": s.inventory.name if s.inventory is not None else "",
                "society": s.inventory.society if s.inventory is not None else None,
            }
            for s in visit.stops
        ],
    }


def lead_detail(lead, now: datetime) -> dict:
    out = lead_row(lead, now)
    out.update(
        {
            "source_data": source_data_payload(lead.source_data),
            "confirmed_data": confirmed_data_payload(lead.confirmed_data),
            "shortlist_societies": [s.society for s in lead.shortlist_societies],
            "preferred_localities": [l.locality for l in lead.preferred_localities],
            "activity": [activity_payload(a) for a in lead.activities],  # newest first
            "recordings": [recording_payload(r) for r in lead.recordings],
            "visits": [visit_payload(v) for v in lead.visits],
        }
    )
    return out


def unit_payload(unit, kind: str, interest_count: int = 0) -> dict:
    """kind: 'inventory' | 'supply' — both share the Unit wire shape."""
    return {
        "id": str(unit.id),
        "name": unit.name,
        "society": unit.society,
        "city": unit.city,
        "configuration": unit.configuration,
        "price_lacs": unit.price_lacs,
        "budget_min_lacs": unit.budget_min_lacs,
        "budget_max_lacs": unit.budget_max_lacs,
        "area_sqft": unit.area_sqft,
        "status": unit.status if kind == "inventory" else None,
        "supply_stage": unit.supply_stage if kind == "supply" else None,
        "eta": unit.eta if kind == "supply" else None,
        "interest_count": interest_count if kind == "supply" else 0,
        "lat": unit.lat,
        "lng": unit.lng,
        "image_url": unit.image_url,
        "ext_source": unit.ext_source,
    }


def reminder_payload(rem) -> dict:
    return {
        "id": str(rem.id),
        "lead_id": str(rem.lead_id),
        "lead_name": rem.lead.name if rem.lead is not None else "",
        "type": rem.type,
        "note": rem.note,
        "due_at": rem.due_at,
        "done": rem.done,
        "auto_generated": rem.auto_generated,
    }
