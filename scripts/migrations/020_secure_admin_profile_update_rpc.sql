-- Atualização administrativa de perfis ativos sem reabrir UPDATE direto.
-- Somente o backend, autenticado com service_role, pode executar esta função.

create or replace function public.admin_update_user_profile(
    p_user_id uuid,
    p_changes jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_unknown_keys text[];
    v_updated public.profiles%rowtype;
begin
    if coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb->>'role', '') <> 'service_role' then
        raise exception 'Service role required' using errcode = '42501';
    end if;

    if p_user_id is null or p_changes is null
       or jsonb_typeof(p_changes) <> 'object' or p_changes = '{}'::jsonb then
        raise exception 'Target user and changes are required' using errcode = '22023';
    end if;

    select array_agg(key order by key)
      into v_unknown_keys
      from jsonb_object_keys(p_changes) as key
     where key not in (
        'full_name', 'username', 'status', 'role_id', 'role', 'sector',
        'cargo', 'comum', 'municipio', 'cidade', 'cadastro_origem',
        'cadastro_origem_label', 'cadastro_origem_rota',
        'cadastro_origem_setor_sugerido'
     );

    if v_unknown_keys is not null then
        raise exception 'Unsupported profile fields: %', array_to_string(v_unknown_keys, ', ')
            using errcode = '22023';
    end if;

    if p_changes ? 'status'
       and coalesce(p_changes->>'status', '') not in ('pending', 'approved', 'rejected') then
        raise exception 'Invalid profile status' using errcode = '22023';
    end if;

    if p_changes ? 'role_id'
       and not exists (
           select 1 from public.access_levels
            where id = (p_changes->>'role_id')::integer
       ) then
        raise exception 'Invalid access level' using errcode = '22023';
    end if;

    update public.profiles as p
       set full_name = case when p_changes ? 'full_name' then nullif(btrim(p_changes->>'full_name'), '') else p.full_name end,
           username = case when p_changes ? 'username' then nullif(btrim(p_changes->>'username'), '') else p.username end,
           status = case when p_changes ? 'status' then p_changes->>'status' else p.status end,
           role_id = case when p_changes ? 'role_id' then (p_changes->>'role_id')::integer else p.role_id end,
           role = case when p_changes ? 'role' then nullif(btrim(p_changes->>'role'), '') else p.role end,
           sector = case when p_changes ? 'sector' then nullif(btrim(p_changes->>'sector'), '') else p.sector end,
           cargo = case when p_changes ? 'cargo' then nullif(btrim(p_changes->>'cargo'), '') else p.cargo end,
           comum = case when p_changes ? 'comum' then nullif(btrim(p_changes->>'comum'), '') else p.comum end,
           municipio = case when p_changes ? 'municipio' then nullif(btrim(p_changes->>'municipio'), '') else p.municipio end,
           cidade = case when p_changes ? 'cidade' then nullif(btrim(p_changes->>'cidade'), '') else p.cidade end,
           cadastro_origem = case when p_changes ? 'cadastro_origem' then nullif(btrim(p_changes->>'cadastro_origem'), '') else p.cadastro_origem end,
           cadastro_origem_label = case when p_changes ? 'cadastro_origem_label' then nullif(btrim(p_changes->>'cadastro_origem_label'), '') else p.cadastro_origem_label end,
           cadastro_origem_rota = case when p_changes ? 'cadastro_origem_rota' then nullif(btrim(p_changes->>'cadastro_origem_rota'), '') else p.cadastro_origem_rota end,
           cadastro_origem_setor_sugerido = case when p_changes ? 'cadastro_origem_setor_sugerido' then nullif(btrim(p_changes->>'cadastro_origem_setor_sugerido'), '') else p.cadastro_origem_setor_sugerido end,
           updated_at = now()
     where p.user_id = p_user_id
     returning p.* into v_updated;

    if not found then
        raise exception 'Profile not found' using errcode = 'P0002';
    end if;

    return to_jsonb(v_updated);
end;
$$;

revoke all on function public.admin_update_user_profile(uuid, jsonb)
from public, anon, authenticated;

grant execute on function public.admin_update_user_profile(uuid, jsonb)
to service_role;

notify pgrst, 'reload schema';
