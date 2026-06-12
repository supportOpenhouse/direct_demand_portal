"""initial schema (HANDOVER §5 + approved deltas)

Revision ID: 0001
Revises:
Create Date: 2026-06-11

Postgres-targeted (JSONB); local dev/tests use app.devdb (create_all on SQLite).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("cm_user_id", sa.Uuid(), nullable=True),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('admin','cm','rm')", name="ck_users_role"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    # circular FK teams.cm_user_id -> users.id, added after both tables exist
    op.create_foreign_key("fk_teams_cm_user_id_users", "teams", "users", ["cm_user_id"], ["id"])

    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("assigned_to", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("stage", sa.String(24), nullable=False, server_default="new"),
        sa.Column("tat_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_hot", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('meta','gads','99acres','magicbricks','youtube','whatsapp','api','webhook','sheets')",
            name="ck_leads_source",
        ),
        sa.CheckConstraint(
            "stage IN ('new','contacted','visit_scheduled','visit_feedback','negotiation',"
            "'won','lost','future_prospect','timepass')",
            name="ck_leads_stage",
        ),
    )
    op.create_index("ix_leads_assigned_to", "leads", ["assigned_to"])
    op.create_index("ix_leads_stage", "leads", ["stage"])
    op.create_index("ix_leads_city", "leads", ["city"])
    op.create_index("ix_leads_confirmed_qualified_at", "leads", ["confirmed", "qualified_at"])

    op.create_table(
        "lead_source_data",
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("budget_band", sa.String(64), nullable=True),
        sa.Column("budget_min_lacs", sa.Float(), nullable=True),
        sa.Column("budget_max_lacs", sa.Float(), nullable=True),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("society", sa.String(160), nullable=True),
        sa.Column("configuration", sa.String(32), nullable=True),
        sa.Column("plan_to_buy", sa.String(24), nullable=True),
        sa.CheckConstraint(
            "plan_to_buy IS NULL OR plan_to_buy IN ('within_30_days','1_3_months','3_6_months','just_exploring')",
            name="ck_lsd_plan",
        ),
    )

    op.create_table(
        "lead_confirmed_data",
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("purpose", sa.String(16), nullable=True),
        sa.Column("budget_value_lacs", sa.Float(), nullable=True),
        sa.Column("configuration", sa.String(32), nullable=True),
        sa.Column("office_willing", sa.String(8), nullable=True),
        sa.Column("office_preferred_date", sa.Date(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("purpose IS NULL OR purpose IN ('self_use','investment')", name="ck_lcd_purpose"),
        sa.CheckConstraint(
            "office_willing IS NULL OR office_willing IN ('yes','no','maybe')", name="ck_lcd_office"
        ),
    )

    op.create_table(
        "lead_shortlist_societies",
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("society", sa.String(160), primary_key=True),
    )

    op.create_table(
        "lead_preferred_localities",
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("locality", sa.String(160), primary_key=True),
    )

    op.create_table(
        "lead_activity",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lead_activity_lead_created", "lead_activity", ["lead_id", "created_at"])

    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "type IN ('follow_up','visit_schedule','visit_feedback','negotiation')",
            name="ck_reminders_type",
        ),
    )
    op.create_index("ix_reminders_done_due_at", "reminders", ["done", "due_at"])

    op.create_table(
        "inventory",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("society", sa.String(160), nullable=True),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("budget_band", sa.String(64), nullable=True),
        sa.Column("budget_min_lacs", sa.Float(), nullable=True),
        sa.Column("budget_max_lacs", sa.Float(), nullable=True),
        sa.Column("configuration", sa.String(32), nullable=True),
        sa.Column("price_lacs", sa.Float(), nullable=True),
        sa.Column("area_sqft", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("ext_source", sa.String(40), nullable=False, server_default="acquired_property"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "supply_units",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("society", sa.String(160), nullable=True),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("budget_band", sa.String(64), nullable=True),
        sa.Column("budget_min_lacs", sa.Float(), nullable=True),
        sa.Column("budget_max_lacs", sa.Float(), nullable=True),
        sa.Column("configuration", sa.String(32), nullable=True),
        sa.Column("price_lacs", sa.Float(), nullable=True),
        sa.Column("area_sqft", sa.Float(), nullable=True),
        sa.Column("eta", sa.String(64), nullable=True),
        sa.Column("supply_stage", sa.String(16), nullable=False, server_default="msi"),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("ext_source", sa.String(40), nullable=False, server_default="supply_tracker"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("supply_stage IN ('msi','token_paid','negotiating')", name="ck_supply_stage"),
    )

    op.create_table(
        "interests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("supply_unit_id", sa.Uuid(), sa.ForeignKey("supply_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rm_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "visits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trip_date", sa.Date(), nullable=False),
        sa.Column("rm_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("total_km", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_min", sa.Float(), nullable=False, server_default="0"),
        sa.Column("route_source", sa.String(8), nullable=False, server_default="est"),
        sa.Column("self_schedule_token", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
        sa.CheckConstraint("route_source IN ('est','google')", name="ck_visits_route_source"),
    )

    op.create_table(
        "visit_stops",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("visit_id", sa.Uuid(), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inventory_id", sa.Uuid(), sa.ForeignKey("inventory.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
    )

    op.create_table(
        "recordings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_id", sa.Uuid(), sa.ForeignKey("visits.id", ondelete="SET NULL"), nullable=True),
        sa.Column("file_ref", sa.String(512), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "buckets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("inventory_id", sa.Uuid(), sa.ForeignKey("inventory.id", ondelete="CASCADE"), nullable=True, unique=True),
        sa.Column("supply_unit_id", sa.Uuid(), sa.ForeignKey("supply_units.id", ondelete="CASCADE"), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "bucket_members",
        sa.Column("bucket_id", sa.Uuid(), sa.ForeignKey("buckets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_on", JSONB, nullable=False),
    )

    op.create_table(
        "society_insights",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("society", sa.String(160), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "societies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.UniqueConstraint("name", "city", name="uq_societies_name_city"),
    )

    op.create_table(
        "localities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.UniqueConstraint("name", "city", name="uq_localities_name_city"),
    )

    op.create_table(
        "settings_integrations",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", JSONB, nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("hash", sa.String(128), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "api_keys",
        "settings_integrations",
        "localities",
        "societies",
        "society_insights",
        "bucket_members",
        "buckets",
        "recordings",
        "visit_stops",
        "visits",
        "interests",
        "supply_units",
        "inventory",
        "reminders",
        "lead_activity",
        "lead_preferred_localities",
        "lead_shortlist_societies",
        "lead_confirmed_data",
        "lead_source_data",
        "leads",
    ):
        op.drop_table(table)
    op.drop_constraint("fk_teams_cm_user_id_users", "teams", type_="foreignkey")
    op.drop_table("users")
    op.drop_table("teams")
