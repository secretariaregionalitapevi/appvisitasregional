-- Sincronização incremental de turmas, aulas e frequências do SAM.
create table if not exists public.sam_gem_classes (
    id uuid primary key default gen_random_uuid(),
    source_id bigint not null unique,
    turma_source_id bigint,
    congregacao text,
    curso text,
    turma text,
    data_aula date,
    inicio time,
    termino time,
    instrutor_responsavel text,
    instrutor_aula text,
    source_hash text not null,
    source_payload jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    synced_at timestamptz not null default now()
);

create table if not exists public.sam_gem_attendance (
    id uuid primary key default gen_random_uuid(),
    aula_id uuid not null references public.sam_gem_classes(id) on delete cascade,
    source_member_id bigint not null,
    source_frequency_id bigint,
    aluno_id uuid references public.musica_acompanhamento_aluno(id) on delete set null,
    nome_aluno text not null,
    presente boolean not null default false,
    source_hash text not null,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    synced_at timestamptz not null default now(),
    unique (aula_id, source_member_id)
);

create table if not exists public.sam_gem_sync_cursor (
    source text primary key,
    last_source_id bigint,
    last_event_at date,
    last_full_sync_at timestamptz,
    last_incremental_sync_at timestamptz,
    last_error text,
    updated_at timestamptz not null default now()
);

create index if not exists sam_gem_classes_date_idx on public.sam_gem_classes(data_aula desc);
create index if not exists sam_gem_classes_turma_idx on public.sam_gem_classes(turma_source_id, data_aula desc);
create index if not exists sam_gem_attendance_student_idx on public.sam_gem_attendance(aluno_id, aula_id);
create index if not exists sam_gem_attendance_member_idx on public.sam_gem_attendance(source_member_id);

alter table public.sam_gem_classes enable row level security;
alter table public.sam_gem_attendance enable row level security;
alter table public.sam_gem_sync_cursor enable row level security;
revoke all on public.sam_gem_classes, public.sam_gem_attendance, public.sam_gem_sync_cursor from anon, authenticated;
grant all on public.sam_gem_classes, public.sam_gem_attendance, public.sam_gem_sync_cursor to service_role;

comment on table public.sam_gem_classes is 'Base sincronizada de aulas encerradas do SAM, identificada por id_aula.';
comment on table public.sam_gem_attendance is 'Base sincronizada de chamadas do SAM por aula e id_membro.';
comment on table public.sam_gem_sync_cursor is 'Cursores e auditoria das cargas incrementais do SAM.';
