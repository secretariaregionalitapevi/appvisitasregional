create table if not exists public.sam_sync_runs (
    id uuid primary key default gen_random_uuid(),
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    status text not null default 'running' check (status in ('running', 'success', 'partial', 'failed')),
    discovered_students integer not null default 0,
    changed_students integer not null default 0,
    imported_events integer not null default 0,
    error_count integer not null default 0,
    details jsonb not null default '{}'::jsonb
);

create table if not exists public.sam_student_sync_state (
    id uuid primary key default gen_random_uuid(),
    source_key text not null unique,
    aluno_id uuid references public.musica_acompanhamento_aluno(id) on delete set null,
    source_name text not null,
    source_common text,
    source_instrument text,
    source_level text,
    source_fingerprint text not null,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    last_changed_at timestamptz not null default now(),
    last_history_sync_at timestamptz,
    missing_since timestamptz,
    sync_status text not null default 'pending' check (sync_status in ('pending', 'synced', 'unmatched', 'ambiguous', 'failed')),
    last_error text,
    source_payload jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.sam_level_history (
    id uuid primary key default gen_random_uuid(),
    aluno_id uuid not null references public.musica_acompanhamento_aluno(id) on delete cascade,
    sync_state_id uuid references public.sam_student_sync_state(id) on delete set null,
    previous_level text,
    new_level text not null,
    effective_at timestamptz not null,
    source_date timestamptz,
    date_basis text not null check (date_basis in ('sam', 'detected_at_sync', 'manual')),
    detected_at timestamptz not null default now(),
    sync_run_id uuid references public.sam_sync_runs(id) on delete set null,
    evidence jsonb not null default '{}'::jsonb,
    unique (aluno_id, new_level, effective_at)
);

create index if not exists sam_student_sync_state_status_idx on public.sam_student_sync_state(sync_status, last_seen_at);
create index if not exists sam_level_history_aluno_idx on public.sam_level_history(aluno_id, effective_at desc);
create index if not exists sam_sync_runs_started_idx on public.sam_sync_runs(started_at desc);

alter table public.sam_sync_runs enable row level security;
alter table public.sam_student_sync_state enable row level security;
alter table public.sam_level_history enable row level security;
revoke all on table public.sam_sync_runs, public.sam_student_sync_state, public.sam_level_history from anon, authenticated;
grant all on table public.sam_sync_runs, public.sam_student_sync_state, public.sam_level_history to service_role;

comment on table public.sam_student_sync_state is 'Último estado observado no catálogo SAM; permite detectar inclusões e alterações sem duplicidade.';
comment on table public.sam_level_history is 'Histórico imutável de mudanças de nível; detected_at_sync é usado quando o SAM não informa a data.';
