-- Execute no SQL Editor do Supabase com uma conta administrativa.
-- O backend usa service_role; clientes anon/authenticated ficam sem acesso
-- direto às tabelas sensíveis e ao bucket privado.

alter table public.visitas_agenda enable row level security;
alter table public.visitas_irmandade enable row level security;
alter table public.visitas_equipes enable row level security;
alter table public.profiles enable row level security;

revoke all on table public.visitas_agenda from anon, authenticated;
revoke all on table public.visitas_irmandade from anon, authenticated;
revoke all on table public.visitas_equipes from anon, authenticated;
revoke all on table public.profiles from anon, authenticated;

grant select on table public.profiles to authenticated;
drop policy if exists "read own profile" on public.profiles;
create policy "read own profile" on public.profiles
for select to authenticated
using (user_id = (select auth.uid()));

update storage.buckets
set public = false,
    file_size_limit = 5242880,
    allowed_mime_types = array['image/jpeg','image/png','image/webp']
where id = 'irmandade_fotos';

update public.visitas_irmandade
set url_foto = '/visitas/api/foto/' || substring(url_foto from '([^/]+)$') || '/'
where url_foto like '%/storage/v1/object/public/irmandade_fotos/%';

create table if not exists public.security_login_attempts (
    key text primary key,
    attempts integer not null default 0,
    window_started_at timestamptz not null default now()
);
alter table public.security_login_attempts enable row level security;
revoke all on table public.security_login_attempts from anon, authenticated;

create or replace function public.check_login_rate_limit(p_key text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare current_attempts integer;
begin
  insert into public.security_login_attempts as limits (key, attempts, window_started_at)
  values (p_key, 1, now())
  on conflict (key) do update set
    attempts = case
      when limits.window_started_at < now() - interval '15 minutes' then 1
      else limits.attempts + 1
    end,
    window_started_at = case
      when limits.window_started_at < now() - interval '15 minutes' then now()
      else limits.window_started_at
    end
  returning attempts into current_attempts;
  return current_attempts <= 5;
end;
$$;

create or replace function public.reset_login_rate_limit(p_key text)
returns void
language sql
security definer
set search_path = public
as $$ delete from public.security_login_attempts where key = p_key; $$;

revoke all on function public.check_login_rate_limit(text) from public, anon, authenticated;
revoke all on function public.reset_login_rate_limit(text) from public, anon, authenticated;
grant execute on function public.check_login_rate_limit(text) to service_role;
grant execute on function public.reset_login_rate_limit(text) to service_role;
