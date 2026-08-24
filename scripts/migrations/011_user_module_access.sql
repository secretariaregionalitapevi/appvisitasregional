create table if not exists public.user_module_access (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.profiles(user_id) on delete cascade,
    module text not null check (module in ('visitas', 'musicalizacao')),
    active boolean not null default true,
    granted_by uuid references public.profiles(user_id) on delete set null,
    granted_at timestamptz not null default now(),
    revoked_at timestamptz,
    updated_at timestamptz not null default now(),
    unique (user_id, module)
);
create index if not exists user_module_access_user_active_idx on public.user_module_access (user_id, active);
alter table public.user_module_access enable row level security;
revoke all on table public.user_module_access from anon, authenticated;
grant all on table public.user_module_access to service_role;
comment on table public.user_module_access is 'Concessoes explicitas de pastas, administradas somente por usuarios globais via backend.';
