-- app_visit_data: the verbatim `data` JSON, projected into real columns.
-- Run top to bottom on prod; idempotent, and safe to re-run after a refill.
--
-- `data` STAYS. It is the record of what Core returned; these columns are a projection
-- of it, the same way leads' mapped columns project `leads.raw`. Re-deriving a column
-- later costs an UPDATE, not another API call.
--
-- Shapes verified against all 336 rows (15 Sep): every key present on every row;
-- data->>'id' = visit_id everywhere; homeId and salesManagerId are numeric strings;
-- selectedDate / visitDate / buyerRegistrationDate are all YYYY-MM-DD; allFeedback is
-- always []; brokerAltContact, buyerFeedback and companyName are always null;
-- demandSmFeedback is null on 215 rows and an object with exactly 6 keys on 121.
-- The columns therefore carry types, not text: a date is a DATE, a count an INTEGER.

-- 0. confirm prod
SELECT current_database(), inet_server_addr();

-- 1. columns
ALTER TABLE app_visit_data
    ADD COLUMN IF NOT EXISTS status                  TEXT,
    ADD COLUMN IF NOT EXISTS lead_status             TEXT,
    ADD COLUMN IF NOT EXISTS source                  TEXT,
    ADD COLUMN IF NOT EXISTS city                    TEXT,
    ADD COLUMN IF NOT EXISTS society_name            TEXT,
    ADD COLUMN IF NOT EXISTS selected_date           DATE,
    ADD COLUMN IF NOT EXISTS selected_time           TEXT,
    ADD COLUMN IF NOT EXISTS visit_date              DATE,
    ADD COLUMN IF NOT EXISTS crm_created_at          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS buyer_name              TEXT,
    ADD COLUMN IF NOT EXISTS buyer_contact           TEXT,
    ADD COLUMN IF NOT EXISTS buyer_registration_date DATE,
    ADD COLUMN IF NOT EXISTS profession              TEXT,
    ADD COLUMN IF NOT EXISTS buyer_feedback          TEXT,
    ADD COLUMN IF NOT EXISTS sales_feedback          TEXT,
    ADD COLUMN IF NOT EXISTS broker_name             TEXT,
    ADD COLUMN IF NOT EXISTS broker_contact          TEXT,
    ADD COLUMN IF NOT EXISTS broker_alt_contact      TEXT,
    ADD COLUMN IF NOT EXISTS cp_code                 TEXT,
    ADD COLUMN IF NOT EXISTS company_name            TEXT,
    ADD COLUMN IF NOT EXISTS sales_manager           TEXT,
    ADD COLUMN IF NOT EXISTS sales_manager_id        INTEGER,
    ADD COLUMN IF NOT EXISTS added_by                TEXT,
    ADD COLUMN IF NOT EXISTS first_added_by          TEXT,
    ADD COLUMN IF NOT EXISTS home_id                 INTEGER,
    ADD COLUMN IF NOT EXISTS floor                   INTEGER,
    ADD COLUMN IF NOT EXISTS furnishing_status       TEXT,
    ADD COLUMN IF NOT EXISTS unit_address_line1      TEXT,
    ADD COLUMN IF NOT EXISTS unit_address_line2      TEXT,
    ADD COLUMN IF NOT EXISTS lead_key                TEXT,
    ADD COLUMN IF NOT EXISTS lead_occurrence_count   INTEGER,
    -- demandSmFeedback, flattened. Six fixed keys; null on a visit with no SM feedback.
    ADD COLUMN IF NOT EXISTS sm_time_spent_on_site    TEXT,
    ADD COLUMN IF NOT EXISTS sm_society_amenity_tour  TEXT,
    ADD COLUMN IF NOT EXISTS sm_price_discussion      TEXT,
    ADD COLUMN IF NOT EXISTS sm_client_queries        TEXT,
    ADD COLUMN IF NOT EXISTS sm_closing_signal        TEXT,
    ADD COLUMN IF NOT EXISTS sm_buyer_primary_concern TEXT,
    -- a list, so it stays JSON. Empty on every visit so far.
    ADD COLUMN IF NOT EXISTS all_feedback            JSONB;

-- 2. data: project `data` into them. `->>` yields NULL for a JSON null, so the
--    always-null fields land as NULL rather than the text "null".
UPDATE app_visit_data SET
    status                  = data->>'status',
    lead_status             = data->>'leadStatus',
    source                  = data->>'source',
    city                    = data->>'city',
    society_name            = data->>'societyName',
    selected_date           = (data->>'selectedDate')::date,
    selected_time           = data->>'selectedTime',
    visit_date              = (data->>'visitDate')::date,
    crm_created_at          = (data->>'createdAt')::timestamptz,
    buyer_name              = data->>'buyerName',
    buyer_contact           = data->>'buyerContact',
    buyer_registration_date = (data->>'buyerRegistrationDate')::date,
    profession              = data->>'profession',
    buyer_feedback          = data->>'buyerFeedback',
    sales_feedback          = data->>'salesFeedback',
    broker_name             = data->>'brokerName',
    broker_contact          = data->>'brokerContact',
    broker_alt_contact      = data->>'brokerAltContact',
    cp_code                 = data->>'cpCode',
    company_name            = data->>'companyName',
    sales_manager           = data->>'salesManager',
    sales_manager_id        = (data->>'salesManagerId')::int,
    added_by                = data->>'addedBy',
    first_added_by          = data->>'firstAddedBy',
    home_id                 = (data->>'homeId')::int,
    floor                   = (data->>'floor')::int,
    furnishing_status       = data->>'furnishingStatus',
    unit_address_line1      = data->>'unitAddressLine1',
    unit_address_line2      = data->>'unitAddressLine2',
    lead_key                = data->>'leadKey',
    lead_occurrence_count   = (data->>'leadOccurrenceCount')::int,
    sm_time_spent_on_site    = data->'demandSmFeedback'->>'timeSpentOnSite',
    sm_society_amenity_tour  = data->'demandSmFeedback'->>'societyAmenityTour',
    sm_price_discussion      = data->'demandSmFeedback'->>'priceDiscussion',
    sm_client_queries        = data->'demandSmFeedback'->>'clientQueries',
    sm_closing_signal        = data->'demandSmFeedback'->>'closingSignal',
    sm_buyer_primary_concern = data->'demandSmFeedback'->>'buyerPrimaryConcern',
    all_feedback            = data->'allFeedback'
 WHERE found;   -- a missing visit has no data to project

-- 3. check: filled counts, and that nothing disagrees with the JSON it came from
SELECT count(*) AS rows,
       count(status) AS with_status,
       count(visit_date) AS with_visit_date,
       count(sales_feedback) AS with_sales_feedback,
       count(sm_closing_signal) AS with_sm_feedback,
       count(*) FILTER (WHERE status IS DISTINCT FROM data->>'status'
                           OR home_id IS DISTINCT FROM (data->>'homeId')::int) AS mismatched
  FROM app_visit_data;
