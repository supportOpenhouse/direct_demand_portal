-- ============================================================================
-- Direct Demand Portal — full Postgres schema (Neon-ready)
-- Generated from backend Alembic migration 0001 (alembic upgrade head --sql).
--
-- Usage: paste into the Neon SQL editor (or psql) and run once on an empty DB.
-- It also stamps alembic_version = '0001', so Render's automatic
-- `alembic upgrade head` pre-deploy step becomes a no-op — both paths stay in sync.
--
-- After creating tables, seed demo data (optional) from backend:
--   DATABASE_URL=postgresql+asyncpg://... uv run python -m app.seed
-- ============================================================================

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE teams (
    id UUID NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    cm_user_id UUID, 
    PRIMARY KEY (id), 
    UNIQUE (name)
);

CREATE TABLE users (
    id UUID NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    phone VARCHAR(32), 
    email VARCHAR(254) NOT NULL, 
    role VARCHAR(16) NOT NULL, 
    team_id UUID, 
    active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_users_role CHECK (role IN ('admin','cm','rm')), 
    FOREIGN KEY(team_id) REFERENCES teams (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

ALTER TABLE teams ADD CONSTRAINT fk_teams_cm_user_id_users FOREIGN KEY(cm_user_id) REFERENCES users (id);

CREATE TABLE leads (
    id UUID NOT NULL, 
    name VARCHAR(160) NOT NULL, 
    phone VARCHAR(32) NOT NULL, 
    source VARCHAR(24) NOT NULL, 
    assigned_to UUID, 
    stage VARCHAR(24) DEFAULT 'new' NOT NULL, 
    tat_deadline TIMESTAMP WITH TIME ZONE, 
    confirmed BOOLEAN DEFAULT false NOT NULL, 
    qualified_at TIMESTAMP WITH TIME ZONE, 
    is_hot BOOLEAN DEFAULT false NOT NULL, 
    city VARCHAR(80), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_leads_source CHECK (source IN ('meta','gads','99acres','magicbricks','youtube','whatsapp','api','webhook','sheets')), 
    CONSTRAINT ck_leads_stage CHECK (stage IN ('new','contacted','visit_scheduled','visit_feedback','negotiation','won','lost','future_prospect','timepass')), 
    FOREIGN KEY(assigned_to) REFERENCES users (id)
);

CREATE INDEX ix_leads_assigned_to ON leads (assigned_to);

CREATE INDEX ix_leads_stage ON leads (stage);

CREATE INDEX ix_leads_city ON leads (city);

CREATE INDEX ix_leads_confirmed_qualified_at ON leads (confirmed, qualified_at);

CREATE TABLE lead_source_data (
    lead_id UUID NOT NULL, 
    budget_band VARCHAR(64), 
    budget_min_lacs FLOAT, 
    budget_max_lacs FLOAT, 
    city VARCHAR(80), 
    society VARCHAR(160), 
    configuration VARCHAR(32), 
    plan_to_buy VARCHAR(24), 
    PRIMARY KEY (lead_id), 
    CONSTRAINT ck_lsd_plan CHECK (plan_to_buy IS NULL OR plan_to_buy IN ('within_30_days','1_3_months','3_6_months','just_exploring')), 
    FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE
);

CREATE TABLE lead_confirmed_data (
    lead_id UUID NOT NULL, 
    purpose VARCHAR(16), 
    budget_value_lacs FLOAT, 
    configuration VARCHAR(32), 
    office_willing VARCHAR(8), 
    office_preferred_date DATE, 
    remark TEXT, 
    confirmed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (lead_id), 
    CONSTRAINT ck_lcd_purpose CHECK (purpose IS NULL OR purpose IN ('self_use','investment')), 
    CONSTRAINT ck_lcd_office CHECK (office_willing IS NULL OR office_willing IN ('yes','no','maybe')), 
    FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE
);

CREATE TABLE lead_shortlist_societies (
    lead_id UUID NOT NULL, 
    society VARCHAR(160) NOT NULL, 
    PRIMARY KEY (lead_id, society), 
    FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE
);

CREATE TABLE lead_preferred_localities (
    lead_id UUID NOT NULL, 
    locality VARCHAR(160) NOT NULL, 
    PRIMARY KEY (lead_id, locality), 
    FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE
);

CREATE TABLE lead_activity (
    id UUID NOT NULL, 
    lead_id UUID NOT NULL, 
    event VARCHAR(64) NOT NULL, 
    remark TEXT, 
    actor_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE, 
    FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_lead_activity_lead_created ON lead_activity (lead_id, created_at);

CREATE TABLE reminders (
    id UUID NOT NULL, 
    lead_id UUID NOT NULL, 
    type VARCHAR(24) NOT NULL, 
    note TEXT, 
    due_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    done BOOLEAN DEFAULT false NOT NULL, 
    auto_generated BOOLEAN DEFAULT false NOT NULL, 
    notified BOOLEAN DEFAULT false NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_reminders_type CHECK (type IN ('follow_up','visit_schedule','visit_feedback','negotiation')), 
    FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE
);

CREATE INDEX ix_reminders_done_due_at ON reminders (done, due_at);

CREATE TABLE inventory (
    id UUID NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    society VARCHAR(160), 
    city VARCHAR(80), 
    budget_band VARCHAR(64), 
    budget_min_lacs FLOAT, 
    budget_max_lacs FLOAT, 
    configuration VARCHAR(32), 
    price_lacs FLOAT, 
    area_sqft FLOAT, 
    status VARCHAR(32), 
    lat FLOAT, 
    lng FLOAT, 
    image_url VARCHAR(512), 
    ext_source VARCHAR(40) DEFAULT 'acquired_property' NOT NULL, 
    synced_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id)
);

CREATE TABLE supply_units (
    id UUID NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    society VARCHAR(160), 
    city VARCHAR(80), 
    budget_band VARCHAR(64), 
    budget_min_lacs FLOAT, 
    budget_max_lacs FLOAT, 
    configuration VARCHAR(32), 
    price_lacs FLOAT, 
    area_sqft FLOAT, 
    eta VARCHAR(64), 
    supply_stage VARCHAR(16) DEFAULT 'msi' NOT NULL, 
    lat FLOAT, 
    lng FLOAT, 
    image_url VARCHAR(512), 
    ext_source VARCHAR(40) DEFAULT 'supply_tracker' NOT NULL, 
    synced_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_supply_stage CHECK (supply_stage IN ('msi','token_paid','negotiating'))
);

CREATE TABLE interests (
    id UUID NOT NULL, 
    supply_unit_id UUID NOT NULL, 
    lead_id UUID, 
    rm_id UUID, 
    note TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(supply_unit_id) REFERENCES supply_units (id) ON DELETE CASCADE, 
    FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE SET NULL, 
    FOREIGN KEY(rm_id) REFERENCES users (id)
);

CREATE TABLE visits (
    id UUID NOT NULL, 
    lead_id UUID NOT NULL, 
    trip_date DATE NOT NULL, 
    rm_id UUID, 
    total_km FLOAT DEFAULT '0' NOT NULL, 
    total_min FLOAT DEFAULT '0' NOT NULL, 
    route_source VARCHAR(8) DEFAULT 'est' NOT NULL, 
    self_schedule_token VARCHAR(64), 
    status VARCHAR(24) DEFAULT 'planned' NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_visits_route_source CHECK (route_source IN ('est','google')), 
    FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE, 
    FOREIGN KEY(rm_id) REFERENCES users (id)
);

CREATE TABLE visit_stops (
    id UUID NOT NULL, 
    visit_id UUID NOT NULL, 
    inventory_id UUID NOT NULL, 
    seq INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(visit_id) REFERENCES visits (id) ON DELETE CASCADE, 
    FOREIGN KEY(inventory_id) REFERENCES inventory (id)
);

CREATE TABLE recordings (
    id UUID NOT NULL, 
    lead_id UUID NOT NULL, 
    visit_id UUID, 
    file_ref VARCHAR(512) NOT NULL, 
    duration_sec INTEGER DEFAULT '0' NOT NULL, 
    recorded_by UUID, 
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE, 
    FOREIGN KEY(visit_id) REFERENCES visits (id) ON DELETE SET NULL, 
    FOREIGN KEY(recorded_by) REFERENCES users (id)
);

CREATE TABLE buckets (
    id UUID NOT NULL, 
    inventory_id UUID, 
    supply_unit_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (inventory_id), 
    FOREIGN KEY(inventory_id) REFERENCES inventory (id) ON DELETE CASCADE, 
    UNIQUE (supply_unit_id), 
    FOREIGN KEY(supply_unit_id) REFERENCES supply_units (id) ON DELETE CASCADE
);

CREATE TABLE bucket_members (
    bucket_id UUID NOT NULL, 
    lead_id UUID NOT NULL, 
    score INTEGER DEFAULT '0' NOT NULL, 
    matched_on JSONB NOT NULL, 
    PRIMARY KEY (bucket_id, lead_id), 
    FOREIGN KEY(bucket_id) REFERENCES buckets (id) ON DELETE CASCADE, 
    FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE
);

CREATE TABLE society_insights (
    id UUID NOT NULL, 
    society VARCHAR(160) NOT NULL, 
    city VARCHAR(80) NOT NULL, 
    note TEXT NOT NULL, 
    created_by UUID, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE societies (
    id UUID NOT NULL, 
    name VARCHAR(160) NOT NULL, 
    city VARCHAR(80) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_societies_name_city UNIQUE (name, city)
);

CREATE TABLE localities (
    id UUID NOT NULL, 
    name VARCHAR(160) NOT NULL, 
    city VARCHAR(80) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_localities_name_city UNIQUE (name, city)
);

CREATE TABLE settings_integrations (
    key VARCHAR(64) NOT NULL, 
    value JSONB, 
    enabled BOOLEAN DEFAULT false NOT NULL, 
    PRIMARY KEY (key)
);

CREATE TABLE api_keys (
    id UUID NOT NULL, 
    label VARCHAR(120) NOT NULL, 
    hash VARCHAR(128) NOT NULL, 
    revoked BOOLEAN DEFAULT false NOT NULL, 
    created_by UUID, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by) REFERENCES users (id)
);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

