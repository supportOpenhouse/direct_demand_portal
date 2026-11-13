"""Listing Demand Dashboard properties on 99acres — admin only, every route.

Spec: docs/superpowers/specs/2026-11-05-99acres-listing-design.md. The work is in
services/acres_listings.py; this file is validation and HTTP status codes.
"""
import re
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from ..config import get_settings
from ..core.auth import require_admin
from ..services import acres_client, acres_listings

router = APIRouter(tags=["acres"], dependencies=[Depends(require_admin)])


class Item(BaseModel):
    uid: str = Field(min_length=1, max_length=40)
    owntype: Literal["1", "2", "3", "4"] | None = None


class CheckIn(BaseModel):
    items: list[Item] = Field(min_length=1, max_length=300)
    photos: bool = True


class PostIn(BaseModel):
    # Small on purpose: the browser loops calls, so each answer lands as it happens.
    items: list[Item] = Field(min_length=1, max_length=5)
    photos: bool = True


class MarkIn(BaseModel):
    status: Literal["live", "failed", "removed"]
    prop_id: str | None = None

    @field_validator("prop_id", mode="before")
    @classmethod
    def _normalise(cls, v):
        return v.strip().upper() or None if isinstance(v, str) else v

    @field_validator("prop_id")
    @classmethod
    def _shape(cls, v):
        if v is not None and not re.fullmatch(r"[A-Z]\d{6,}", v):
            raise ValueError("a 99acres listing id looks like E95607134")
        return v

    @model_validator(mode="after")
    def _live_needs_an_id(self):
        if self.status == "live" and not self.prop_id:
            raise ValueError("recording a listing as live needs its 99acres listing id")
        return self


@router.get("/acres/listings")
async def listings() -> dict:
    return {"items": await acres_listings.list_listings()}


@router.post("/acres/check")
async def check(body: CheckIn) -> dict:
    try:
        return {"items": await acres_listings.check([i.model_dump() for i in body.items], photos=body.photos)}
    except acres_client.AcresNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/acres/post")
async def post(body: PostIn, user: dict = Depends(require_admin)) -> dict:
    try:
        items = await acres_listings.post([i.model_dump() for i in body.items], photos=body.photos, user=user)
    except acres_client.AcresNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except acres_client.AcresError as e:
        raise HTTPException(status_code=502, detail=str(e))
    # `halt`: the run must stop — an answer was lost, or 99acres / its edge / the proxy refused us.
    return {"items": items, "halt": any(i["halt"] for i in items)}


@router.patch("/acres/listings/{uid}")
async def mark(uid: str, body: MarkIn, user: dict = Depends(require_admin)) -> dict:
    try:
        return await acres_listings.mark(uid, body.status, body.prop_id, user)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/acres/health")
async def health(login: bool = False) -> dict:
    """Is the droplet still sending from the whitelisted IP — and, with ?login=true, will
    99acres log us in? Never returns the token."""
    s = get_settings()
    try:
        ip = await acres_client.egress_ip()
    except acres_client.AcresNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"proxy unreachable ({type(e).__name__})")
    out = {"egress_ip": ip, "expected_ip": s.DROPLET_STATIC_IP or None,
           "egress_matches": ip == s.DROPLET_STATIC_IP, "login": None}
    if login:
        try:
            await acres_client.token(force=True)
            out["login"] = {"ok": True, "error": None}
        except acres_client.AcresError as e:
            out["login"] = {"ok": False, "error": str(e)}
    return out
