-- Shared security fix: allow APP_GLOBAL administrators to review pending users
-- without restoring direct UPDATE privileges on public.profiles.

-- The legacy trigger uses unaccent() without a schema qualification. Give only
-- that trigger function the schemas required to resolve the installed extension;
-- the SECURITY DEFINER review function below keeps its empty search_path.
alter function public.normalize_profile_access_fields()
set search_path = pg_catalog, extensions, public;

create or replace function public.review_pending_user(
    p_user_id uuid,
    p_role_id integer,
    p_role text,
    p_sector text,
    p_cargo text,
    p_comum text,
    p_status text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_reviewer_id uuid := auth.uid();
    v_reviewer_role_id integer;
    v_updated public.profiles%rowtype;
begin
    if v_reviewer_id is null then
        raise exception 'Authentication required' using errcode = '42501';
    end if;

    select p.role_id
      into v_reviewer_role_id
      from public.profiles as p
     where p.user_id = v_reviewer_id
       and p.status = 'approved';

    if coalesce(v_reviewer_role_id, 99) not in (1, 2) then
        raise exception 'Administrator permission required' using errcode = '42501';
    end if;

    if p_user_id is null then
        raise exception 'Target user is required' using errcode = '22023';
    end if;

    if p_status not in ('approved', 'rejected') then
        raise exception 'Invalid review status' using errcode = '22023';
    end if;

    if not exists (select 1 from public.access_levels where id = p_role_id) then
        raise exception 'Invalid access level' using errcode = '22023';
    end if;

    -- An Admin can manage ordinary access levels, but cannot create a Master.
    if v_reviewer_role_id = 2 and p_role_id = 1 then
        raise exception 'Only a Master can grant Master access' using errcode = '42501';
    end if;

    update public.profiles
       set role_id = p_role_id,
           role = nullif(btrim(p_role), ''),
           sector = nullif(btrim(p_sector), ''),
           cargo = nullif(btrim(p_cargo), ''),
           comum = nullif(btrim(p_comum), ''),
           status = p_status,
           updated_at = now()
     where user_id = p_user_id
       and status = 'pending'
     returning * into v_updated;

    if not found then
        raise exception 'Pending profile not found or already reviewed' using errcode = 'P0002';
    end if;

    insert into public.audit_logs (user_id, action, module, details)
    values (
        v_reviewer_id,
        case p_status
            when 'approved' then 'USER_APPROVAL_APPROVED'
            else 'USER_APPROVAL_REJECTED'
        end,
        'ADMIN',
        jsonb_build_object(
            'reviewed_user_id', p_user_id,
            'status', p_status,
            'role_id', p_role_id,
            'role', p_role,
            'sector', p_sector,
            'cargo', p_cargo,
            'comum', p_comum
        )
    );

    return to_jsonb(v_updated);
end;
$$;

revoke all on function public.review_pending_user(uuid, integer, text, text, text, text, text)
from public, anon, authenticated;

grant execute on function public.review_pending_user(uuid, integer, text, text, text, text, text)
to authenticated;

notify pgrst, 'reload schema';
