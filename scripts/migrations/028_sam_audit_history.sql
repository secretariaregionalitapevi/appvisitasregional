-- Trilha permanente dos eventos produzidos pelo SAM original.
-- Os nomes e a localidade sao copiados no momento da captura: nenhuma FK pode
-- apagar ou descaracterizar o fato historico quando um usuario/aluno for removido.
create table if not exists public.sam_audit_events (
    id uuid primary key default gen_random_uuid(),
    source_fingerprint text not null unique,
    source_log_id bigint,
    occurred_at timestamptz not null,
    actor_source_id bigint,
    actor_name_snapshot text not null default 'USUARIO NAO IDENTIFICADO',
    congregation_snapshot text,
    action_raw text not null,
    action_type text not null default 'outro',
    target_type text,
    target_source_id bigint,
    target_name_snapshot text,
    device text,
    platform text,
    ip_address inet,
    parsed_refs jsonb not null default '{}'::jsonb,
    source_payload jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    synced_at timestamptz not null default now()
);

create table if not exists public.sam_audit_sync_cursor (
    source text primary key,
    last_occurred_at timestamptz,
    last_source_log_id bigint,
    last_full_sync_at timestamptz,
    last_incremental_sync_at timestamptz,
    imported_count integer not null default 0,
    last_error text,
    updated_at timestamptz not null default now()
);

create index if not exists sam_audit_events_occurred_idx on public.sam_audit_events(occurred_at desc);
create index if not exists sam_audit_events_actor_idx on public.sam_audit_events(actor_name_snapshot, occurred_at desc);
create index if not exists sam_audit_events_target_idx on public.sam_audit_events(target_type, target_source_id, occurred_at desc);
create index if not exists sam_audit_events_action_idx on public.sam_audit_events(action_type, occurred_at desc);
create index if not exists sam_audit_events_congregation_idx on public.sam_audit_events(congregation_snapshot, occurred_at desc);

alter table public.sam_audit_events enable row level security;
alter table public.sam_audit_sync_cursor enable row level security;
revoke all on public.sam_audit_events, public.sam_audit_sync_cursor from anon, authenticated;
grant all on public.sam_audit_events, public.sam_audit_sync_cursor to service_role;

comment on table public.sam_audit_events is
'Arquivo imutavel dos logs do SAM. Identidade, localidade e acao sao snapshots e sobrevivem a exclusoes na origem.';
comment on column public.sam_audit_events.source_fingerprint is
'Assinatura idempotente do evento original; impede duplicacao em reprocessamentos.';
