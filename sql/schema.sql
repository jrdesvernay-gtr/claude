-- Multi-Unit Franchisee Pipeline — Supabase schema
--
-- Design notes:
--   * franchisees.total_units / brand_count / brand_list / operating_states are
--     derived from `units` via trigger (refresh_franchisee_rollup) — never written
--     directly by application code.
--   * confidence columns are numeric [0,1]; thresholds live in pipeline/config.py,
--     not in the DB, so they can be tuned without a migration.
--   * No array-of-unit-ids column on franchisees — franchisee_units_view covers that.

create extension if not exists "pgcrypto";
create extension if not exists "pg_trgm";

-- ---------------------------------------------------------------------------
-- franchisors
-- ---------------------------------------------------------------------------
create table if not exists franchisors (
    id          uuid primary key default gen_random_uuid(),
    name        text not null unique,
    website     text,
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- fdd_filings — one row per document pulled, for provenance/versioning
-- ---------------------------------------------------------------------------
create type document_type as enum ('final_fdd', 'clean_fdd', 'marked_fdd', 'unknown');

create table if not exists fdd_filings (
    id                    uuid primary key default gen_random_uuid(),
    franchisor_id         uuid not null references franchisors(id) on delete cascade,
    state                 text not null,               -- 'WI', 'MN', ...
    filing_year           int,
    source_url            text not null,
    document_type         document_type not null default 'unknown',
    downloaded_at         timestamptz not null default now(),
    handler_id_used        text,                        -- registry key, see parsing.handlers
    handler_confidence     numeric(3,2),                -- 0.00-1.00, probationary handlers start low
    table1_outlet_count    int,                          -- Item 20 Table No. 1 self-disclosed total
    parsed_row_count       int,                          -- rows actually parsed from the exhibit
    table1_match           boolean,                      -- table1_outlet_count = parsed_row_count
    review_flag            boolean not null default false, -- set true on Table 1 mismatch; blocks unit load
    raw_document_path      text,                         -- object storage path for the source PDF
    created_at             timestamptz not null default now(),
    unique (franchisor_id, state, source_url)
);

create index if not exists idx_fdd_filings_franchisor on fdd_filings(franchisor_id);
create index if not exists idx_fdd_filings_review_flag on fdd_filings(review_flag) where review_flag;

-- ---------------------------------------------------------------------------
-- franchisees — one row per resolved legal entity
-- ---------------------------------------------------------------------------
create table if not exists franchisees (
    id                    uuid primary key default gen_random_uuid(),
    legal_name            text not null,
    entity_type           text,                          -- LLC, Corp, Inc, LP, ...
    hq_full_address        text,
    hq_phone               text,
    hq_email                text,
    domain                text,
    linkedin_url           text,
    guarantor_names         text[] not null default '{}',

    contact_first_name      text,
    contact_last_name       text,
    contact_name             text,
    contact_title            text,
    contact_email            text,
    contact_linkedin_url     text,
    contact_confidence       numeric(3,2),               -- hard gate before syncing to Instantly/Pipedrive

    merge_confidence         numeric(3,2),               -- from entity resolution; null = unambiguous auto-match

    -- derived/rollup columns, maintained ONLY by refresh_franchisee_rollup()
    brand_list               text[] not null default '{}',
    brand_count               int not null default 0,
    total_units                int not null default 0,
    operating_states           text[] not null default '{}',

    created_at                timestamptz not null default now(),
    updated_at                timestamptz not null default now()
);

-- match-before-insert key: case/whitespace-insensitive uniqueness on legal_name
create unique index if not exists idx_franchisees_legal_name_ci
    on franchisees (lower(regexp_replace(legal_name, '\s+', ' ', 'g')));
create index if not exists idx_franchisees_legal_name_trgm
    on franchisees using gin (legal_name gin_trgm_ops);
create index if not exists idx_franchisees_contact_confidence on franchisees(contact_confidence);

-- contact fields must clear the enrichment gate before outbound sync; enforced in
-- application code (contact_confidence >= CONTACT_SYNC_THRESHOLD), not here, since
-- the threshold is expected to be tuned without a migration.

-- ---------------------------------------------------------------------------
-- units — one row per outlet, as listed in Item 20
-- ---------------------------------------------------------------------------
create table if not exists units (
    id                uuid primary key default gen_random_uuid(),
    fdd_filing_id      uuid not null references fdd_filings(id) on delete cascade,
    franchisor_id       uuid not null references franchisors(id) on delete cascade,
    franchisee_id        uuid references franchisees(id) on delete set null,

    franchisee_raw        text not null,   -- verbatim Item 20 franchisee field, incl. guarantor names
    address                text,
    city                   text,
    state                  text,
    zip                     text,
    phone                    text,
    status                   text,          -- e.g. operating / transferred / terminated, as disclosed

    created_at                timestamptz not null default now()
);

create index if not exists idx_units_fdd_filing on units(fdd_filing_id);
create index if not exists idx_units_franchisor on units(franchisor_id);
create index if not exists idx_units_franchisee on units(franchisee_id);

-- ---------------------------------------------------------------------------
-- handler_registry — Item 20 table-format parsers (deterministic + agent-drafted)
-- ---------------------------------------------------------------------------
create table if not exists handler_registry (
    id                  text primary key,           -- e.g. 'wi_standard_v1', 'mn_pipe_delim_v1'
    state                text not null,
    description           text,
    source                text not null default 'deterministic' check (source in ('deterministic', 'agent_drafted')),
    probation_runs_remaining int not null default 0,  -- >0 while probationary; agent-drafted handlers start at 3
    confidence_score       numeric(3,2) not null default 1.00,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- rollup trigger: franchisees.brand_list / brand_count / total_units / operating_states
-- ---------------------------------------------------------------------------
create or replace function refresh_franchisee_rollup(p_franchisee_id uuid)
returns void
language plpgsql
as $$
begin
    if p_franchisee_id is null then
        return;
    end if;

    update franchisees f
    set brand_list       = coalesce(agg.brand_list, '{}'),
        brand_count        = coalesce(agg.brand_count, 0),
        total_units          = coalesce(agg.total_units, 0),
        operating_states       = coalesce(agg.operating_states, '{}'),
        updated_at              = now()
    from (
        select
            u.franchisee_id,
            array_agg(distinct fr.name order by fr.name)  as brand_list,
            count(distinct fr.id)                          as brand_count,
            count(*)                                          as total_units,
            array_agg(distinct u.state order by u.state)        as operating_states
        from units u
        join franchisors fr on fr.id = u.franchisor_id
        where u.franchisee_id = p_franchisee_id
        group by u.franchisee_id
    ) agg
    where f.id = agg.franchisee_id
       or f.id = p_franchisee_id;

    -- franchisee has zero units left (e.g. last unit reassigned) — zero it out
    update franchisees
    set brand_list = '{}', brand_count = 0, total_units = 0, operating_states = '{}', updated_at = now()
    where id = p_franchisee_id
      and not exists (select 1 from units where franchisee_id = p_franchisee_id);
end;
$$;

create or replace function trg_units_rollup()
returns trigger
language plpgsql
as $$
begin
    if tg_op = 'DELETE' then
        perform refresh_franchisee_rollup(old.franchisee_id);
        return old;
    end if;

    perform refresh_franchisee_rollup(new.franchisee_id);
    if tg_op = 'UPDATE' and old.franchisee_id is distinct from new.franchisee_id then
        perform refresh_franchisee_rollup(old.franchisee_id);
    end if;
    return new;
end;
$$;

drop trigger if exists units_rollup on units;
create trigger units_rollup
    after insert or update of franchisee_id or delete on units
    for each row execute function trg_units_rollup();

-- ---------------------------------------------------------------------------
-- convenience view — replaces an array-of-unit-ids column on franchisees
-- ---------------------------------------------------------------------------
create or replace view franchisee_units_view as
select
    f.id as franchisee_id,
    f.legal_name,
    u.id as unit_id,
    u.franchisor_id,
    fr.name as brand_name,
    u.address, u.city, u.state, u.zip, u.phone, u.status
from franchisees f
join units u on u.franchisee_id = f.id
join franchisors fr on fr.id = u.franchisor_id;

create or replace function trg_touch_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists franchisees_touch on franchisees;
create trigger franchisees_touch
    before update on franchisees
    for each row execute function trg_touch_updated_at();
