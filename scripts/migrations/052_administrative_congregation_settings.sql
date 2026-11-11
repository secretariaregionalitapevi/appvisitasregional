-- Guarda edições e arquivamento sem alterar o catálogo compartilhado de comuns.
begin;

create table if not exists public.administrative_congregation_settings (
    congregation_code text primary key,
    nome text not null,
    municipio text not null,
    administracao text not null default '',
    encarregados_regionais jsonb not null default '[]'::jsonb,
    examinadoras jsonb not null default '[]'::jsonb,
    secretarios_musica jsonb not null default '[]'::jsonb,
    encarregados_locais jsonb not null default '[]'::jsonb,
    secretarios_gem jsonb not null default '[]'::jsonb,
    archived_at timestamptz,
    updated_by text,
    updated_at timestamptz not null default now()
);

alter table public.administrative_congregation_settings enable row level security;
revoke all on table public.administrative_congregation_settings from public, anon, authenticated;
grant all on table public.administrative_congregation_settings to service_role;

comment on table public.administrative_congregation_settings is
    'Overrides e arquivamento da tela de Congregações, sem alterar o catálogo compartilhado de comuns.';

notify pgrst, 'reload schema';
commit;
