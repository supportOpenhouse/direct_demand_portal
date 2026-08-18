"""RM performance summaries — served at /v1/analytics/rm-summary.

An on-demand, Claude-written paragraph about one RM's funnel performance over a chosen
date range. The frontend already computes the numbers shown in the RM performance table,
so it POSTs that exact metric bundle here; we only shape it into a grounded prompt and
relay Claude's answer. That keeps the words consistent with the table (no second source
of truth) and keeps this endpoint stateless — no DB query, no alias-matching.

Switched on by ANTHROPIC_API_KEY. Unset → 503 with a plain reason rather than a 500, so
an un-provisioned deploy tells you what's missing. Calls the Anthropic Messages REST API
directly over httpx (already a dependency) — no extra SDK to install or pin.
"""
import hashlib
import json
import logging
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..core.auth import current_user

log = logging.getLogger("rm_summary")

router = APIRouter(tags=["analytics"])

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Human labels for the stage segments the frontend sends, in funnel order.
STAGE_LABELS = [
    ("new", "New (awaiting first call)"),
    ("call_not_received", "Call not received"),
    ("followup", "Call back again (callback scheduled)"),
    ("qualified", "Qualified (requirement captured)"),
    ("pipeline", "Visited"),
    ("revisit", "Pipeline (revisit booked)"),
    ("converted", "Converted (token)"),
    ("rejected", "Rejected / RNR"),
]

# Extra derived signals the frontend may send, with human labels.
EXTRA_LABELS = {
    "qualified_reached": "Leads that reached qualification or beyond",
    "ever_connected": "Leads ever connected on call",
    "miss_total": "Total not-connected call attempts (persistence)",
    "hot": "Hot (starred) leads",
    "followups_overdue": "Overdue callbacks",
    "active_days": "Distinct days with a new lead created",
    "leads_per_active_day": "Avg new leads per active day",
}

SYSTEM_PROMPT = (
    "You are a sales-operations coach for a real-estate demand team. You write terse, "
    "manager-facing, ACTIONABLE performance notes about a single Relationship Manager (RM) "
    "— the reader wants to know how the RM is doing and exactly what to do to improve their "
    "numbers. Use ONLY the numbers provided; never invent metrics, names, or trends you "
    "cannot derive from them. Be specific and quantitative — cite the actual figures and the "
    "simple rates you compute from them, and tie every recommendation to a figure and a "
    "concrete target."
)


class RMSummaryReq(BaseModel):
    rm: str = Field(..., max_length=120)
    range_label: str = Field(..., max_length=60)
    total: int = Field(..., ge=0)
    stages: dict[str, int] = Field(default_factory=dict)
    extras: dict[str, float] = Field(default_factory=dict)


class RMSummaryResp(BaseModel):
    rm: str
    range_label: str
    summary: str
    model: str
    cached: bool
    generated_at: str


# tiny per-process cache so re-expanding the same row (same range, same numbers) is free.
_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 600.0  # 10 minutes
_CACHE_MAX = 256


def _cache_key(req: RMSummaryReq, model: str) -> str:
    raw = json.dumps(
        {"rm": req.rm, "r": req.range_label, "t": req.total, "s": req.stages, "e": req.extras, "m": model},
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _build_user_prompt(req: RMSummaryReq) -> str:
    lines = [
        f"RM: {req.rm}",
        f"Date range: {req.range_label}",
        f"Total leads owned in range: {req.total}",
        "",
        "Stage breakdown (count in each stage — a lead sits in exactly one):",
    ]
    for seg, label in STAGE_LABELS:
        if seg in req.stages:
            n = req.stages[seg]
            share = round(n / req.total * 100) if req.total else 0
            lines.append(f"  - {label}: {n} ({share}% of their total)")
    if req.extras:
        lines.append("")
        lines.append("Additional activity signals:")
        for key, label in EXTRA_LABELS.items():
            if key in req.extras:
                val = req.extras[key]
                val_s = f"{val:.1f}" if isinstance(val, float) and not val.is_integer() else str(int(val))
                lines.append(f"  - {label}: {val_s}")
    lines.append("")
    lines.append(
        "Respond in exactly two labelled parts, and nothing else:\n\n"
        "Assessment: 2–3 sentences rating how this RM is performing — name their clearest "
        "strength and the funnel stage where they leak most, each backed by a figure or a "
        "rate you compute (e.g. connect rate, qualification rate, conversion rate, overdue-"
        "callback share).\n\n"
        "Actions to improve:\n"
        "- 3 to 4 prioritised, concrete steps to lift their numbers, ordered by impact. Each "
        "step must reference the metric it targets, its current figure, and a specific target "
        "or tactic (e.g. 'Only 112 of 778 leads reached qualification (14%) — rework the "
        "first-call pitch to push qualification rate above 25%'). Make them things a manager "
        "could hold the RM accountable to this week.\n\n"
        "Use only the figures above. Do not add any heading other than 'Assessment:' and "
        "'Actions to improve:'. Start action lines with '- '."
    )
    return "\n".join(lines)


@router.post("/analytics/rm-summary", response_model=RMSummaryResp)
async def rm_summary(req: RMSummaryReq, _: dict = Depends(current_user)) -> RMSummaryResp:
    settings = get_settings()
    key = settings.ANTHROPIC_API_KEY
    model = settings.RM_SUMMARY_MODEL
    now_iso = datetime.now(timezone.utc).isoformat()

    if not key:
        raise HTTPException(
            status_code=503,
            detail="AI summaries aren't switched on — set ANTHROPIC_API_KEY on the backend.",
        )

    ck = _cache_key(req, model)
    hit = _CACHE.get(ck)
    if hit and (time.monotonic() - hit[0]) < _CACHE_TTL:
        return RMSummaryResp(
            rm=req.rm, range_label=req.range_label, summary=hit[1],
            model=model, cached=True, generated_at=now_iso,
        )

    payload = {
        "model": model,
        "max_tokens": 600,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _build_user_prompt(req)}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(ANTHROPIC_URL, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        log.warning("Anthropic request failed for RM=%s: %s", req.rm, exc)
        raise HTTPException(status_code=502, detail="Couldn't reach the AI service. Try again.") from exc

    if resp.status_code != 200:
        # surface the provider's message without leaking the key
        detail = "AI service error."
        try:
            body = resp.json()
            detail = body.get("error", {}).get("message", detail)
        except Exception:  # noqa: BLE001 — best-effort
            pass
        log.warning("Anthropic %s for RM=%s: %s", resp.status_code, req.rm, detail)
        raise HTTPException(status_code=502, detail=f"AI service error: {detail}")

    data = resp.json()
    text = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    ).strip()
    if not text:
        raise HTTPException(status_code=502, detail="AI service returned an empty summary.")

    # remember it (with naive size cap)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[ck] = (time.monotonic(), text)

    return RMSummaryResp(
        rm=req.rm, range_label=req.range_label, summary=text,
        model=model, cached=False, generated_at=now_iso,
    )
