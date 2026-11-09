-- Pasta Música independente para a gestão municipal no APP_CARTAS.
-- Aprovação, município e nível continuam sendo geridos na trilha de auditoria existente.
begin;
-- Também atende bancos que ainda não receberam a migração 011.
-- Não altera nem concede automaticamente permissões dos usuários existentes.
create table if not exists public.user_module_access (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null,
 module text not null,
 active boolean not null default true,
 granted_by uuid,
 granted_at timestamptz not null default now(),
 revoked_at timestamptz,
 updated_at timestamptz not null default now(),
 unique (user_id, module)
);
create index if not exists user_module_access_user_active_idx
 on public.user_module_access (user_id, active);
alter table public.user_module_access drop constraint if exists user_module_access_module_check;
alter table public.user_module_access add constraint user_module_access_module_check
 check(module in ('visitas','musicalizacao','darpe','musica'));
alter table public.user_module_access enable row level security;
revoke all on table public.user_module_access from public, anon, authenticated;
grant all on table public.user_module_access to service_role;
comment on table public.user_module_access is 'Pastas independentes aprovadas na trilha de auditoria: Visitas, Musicalização, D.A.R.P.E e Música (gestão de cartas).';
notify pgrst,'reload schema';
commit;
