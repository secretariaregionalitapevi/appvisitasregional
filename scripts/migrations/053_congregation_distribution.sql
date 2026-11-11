-- Vínculos por comum, separados da residência dos cadastros oficiais.
begin;
create table if not exists public.administrative_congregation_distribution (
    congregation_code text primary key check (congregation_code ~ '^BR-[0-9]{2}-[0-9]{4}$'),
    assignments jsonb not null default '[]'::jsonb check (jsonb_typeof(assignments) = 'array'),
    revision integer not null default 1 check (revision > 0),
    updated_by text not null,
    updated_at timestamptz not null default now()
);
alter table public.administrative_congregation_distribution enable row level security;
revoke all on public.administrative_congregation_distribution from public, anon, authenticated;
grant all on public.administrative_congregation_distribution to service_role;
comment on table public.administrative_congregation_distribution is
    'Ajustes da distribuição oficial de anciães, regionais e Secretaria da Música; alterações auditadas pelo servidor.';
notify pgrst, 'reload schema';
commit;
