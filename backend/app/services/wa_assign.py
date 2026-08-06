"""Who owns a WhatsApp conversation.

Three rules, in order:

  1. The number already has a lead with an owner  → the same RM.
  2. Otherwise, the active RM with the fewest open conversations.
  3. Ties → whoever was assigned longest ago (never-assigned first).

Rule 1 is the important one. Plain round-robin would hand a thread to a different RM
than the one already working that customer's lead, so two people end up talking to the
same buyer on two channels — worse than an uneven split.

Rules 2+3 give round-robin behaviour whenever load is level, and self-correct when it
isn't: an RM who is inactive, on leave, or sitting on a pile of conversations stops
collecting new ones, which a turn-counter never notices.

Contacts tagged `rejected` are never assigned — dead numbers shouldn't consume anyone's
share — and tagging an existing one clears its owner.
"""
import logging

from sqlalchemy import text

log = logging.getLogger("wa_assign")

# Names are the assignment currency across the app (leads.assigned_to holds a free-text
# name, canonicalised by build_assignee_canon_map). wa_contacts follows suit so filters,
# analytics and reassignment all work on one convention.

_LEAD_OWNER = text("""
    SELECT assigned_to FROM leads
    WHERE right(regexp_replace(phone, '\\D', '', 'g'), 10) = :p10
      AND assigned_to IS NOT NULL AND btrim(assigned_to) <> ''
    ORDER BY created_at DESC LIMIT 1
""")

_LEAST_LOADED = text("""
    SELECT u.name
    FROM users u
    LEFT JOIN wa_contacts c
      ON lower(c.assigned_to) = lower(u.name)
     AND (c.tag IS NULL OR c.tag <> 'rejected')
    -- Exactly 'rm', deliberately NOT core.auth.CALLING_ROLES: a test_rm is dialled by
    -- campaigns but must never be handed a real customer conversation. A test account
    -- silently owning a live WhatsApp thread is worse than leaving it unassigned.
    WHERE u.active AND u.role = 'rm' AND u.name IS NOT NULL AND btrim(u.name) <> ''
    GROUP BY u.name
    -- fewest conversations first; then longest since last assigned (never-assigned
    -- sorts first via NULLS FIRST); then name, so the choice is deterministic
    ORDER BY count(c.phone10), max(c.assigned_at) NULLS FIRST, u.name
    LIMIT 1
""")


async def pick_owner(conn, phone10: str) -> str | None:
    """The RM who should own this conversation, or None if there are no active RMs."""
    row = (await conn.execute(_LEAD_OWNER, {"p10": phone10})).first()
    if row and row[0]:
        return row[0]
    row = (await conn.execute(_LEAST_LOADED)).first()
    return row[0] if row else None


async def assign_if_unassigned(conn, phone10: str) -> str | None:
    """Give a conversation an owner the first time we see it.

    Only fills blanks: an existing owner — auto or hand-picked — is never overwritten,
    because reshuffling a live conversation confuses the customer more than it helps.
    """
    row = (await conn.execute(
        text("SELECT assigned_to, tag FROM wa_contacts WHERE phone10 = :p"), {"p": phone10}
    )).first()
    if row and (row[0] or row[1] == "rejected"):
        return row[0]

    owner = await pick_owner(conn, phone10)
    if owner is None:
        log.warning("no active RM to assign WhatsApp contact %s", phone10[-4:])
        return None

    await conn.execute(text("""
        INSERT INTO wa_contacts (phone10, tag, assigned_to, assigned_at)
        VALUES (:p, NULL, :owner, now())
        ON CONFLICT (phone10) DO UPDATE
           SET assigned_to = EXCLUDED.assigned_to, assigned_at = now()
         WHERE wa_contacts.assigned_to IS NULL
    """), {"p": phone10, "owner": owner})
    return owner


async def backfill(conn) -> int:
    """Distribute conversations that predate assignment. Runs one at a time so each
    pick sees the previous one's effect on load — a set-based update would hand every
    unowned thread to whoever is currently least loaded."""
    rows = (await conn.execute(text("""
        SELECT DISTINCT right(m.phone, 10) AS p10
        FROM wa_messages m
        LEFT JOIN wa_contacts c ON c.phone10 = right(m.phone, 10)
        WHERE length(m.phone) >= 10
          AND (c.phone10 IS NULL OR (c.assigned_to IS NULL AND c.tag IS DISTINCT FROM 'rejected'))
    """))).all()
    done = 0
    for (p10,) in rows:
        if await assign_if_unassigned(conn, p10):
            done += 1
    if done:
        log.info("wa_assign: back-filled %d conversation(s)", done)
    return done
