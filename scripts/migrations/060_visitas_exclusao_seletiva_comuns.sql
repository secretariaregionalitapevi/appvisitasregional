-- Remocao parcial do roteiro; limpeza opcional da agenda por comum e data.
begin;

create or replace function public.visitas_chave_comum_roteiro(value text)
returns text language sql immutable set search_path=public as $$
    select coalesce(substring(upper(value) from 'BR-[0-9]{2}-[0-9]{4}'),upper(trim(value)));
$$;

create or replace function public.visitas_previa_remocao_comuns_roteiro(
    p_id uuid,p_data date,p_municipio text
) returns jsonb language plpgsql set search_path=public as $$
declare route public.visitas_roteiros_regionais%rowtype; result jsonb; agenda_version text;
begin
    select * into route from public.visitas_roteiros_regionais
    where id=p_id and data=p_data and municipio=p_municipio and plano->>'deleted_at' is null;
    if not found then raise exception 'Roteiro nao encontrado ou excluido'; end if;
    select md5(route.plano::text || coalesce(jsonb_agg(to_jsonb(a) order by a.id)::text,'[]'))
        into agenda_version from public.visitas_agenda a where a.roteiro_regional_id=p_id;
    select jsonb_build_object('version',agenda_version,
        'commons',coalesce(jsonb_agg(jsonb_build_object('common',c.value,
            'scheduled',(select count(*) from public.visitas_agenda a
                where a.roteiro_regional_id=p_id and a.status='Marcada'
                and a.data_inicio>=p_data::timestamp at time zone 'America/Sao_Paulo'
                and a.data_inicio<(p_data+1)::timestamp at time zone 'America/Sao_Paulo'
                and exists(select 1 from jsonb_array_elements(route.plano->'houses') h,
                    lateral jsonb_array_elements(h->'members') m
                    where m->>'id'=a.irmandade_id::text and public.visitas_chave_comum_roteiro(coalesce(m->>'codigo_comum',m->>'comum'))=public.visitas_chave_comum_roteiro(c.value))))), '[]'))
    into result from jsonb_array_elements_text(route.plano->'commons') c;
    return result;
end;
$$;

create or replace function public.visitas_remover_comuns_roteiro(
    p_id uuid,p_data date,p_municipio text,p_actor uuid,p_expected_version text,
    p_comuns text[],p_agenda_comuns text[]
) returns jsonb language plpgsql set search_path=public as $$
declare route public.visitas_roteiros_regionais%rowtype; stats jsonb;
    remaining jsonb; houses jsonb; updated_house jsonb; house jsonb;
    members jsonb; visits jsonb; removed integer; result jsonb; updated_plan jsonb;
begin
    perform pg_advisory_xact_lock(hashtextextended(p_data::text || ':' || p_municipio,0));
    lock table public.visitas_agenda in share row exclusive mode;
    select * into route from public.visitas_roteiros_regionais
    where id=p_id and data=p_data and municipio=p_municipio for update;
    if not found or route.plano->>'deleted_at' is not null then
        raise exception 'Roteiro nao encontrado ou excluido';
    end if;
    if coalesce(cardinality(p_comuns),0)=0 or p_agenda_comuns is null
       or exists(select 1 from unnest(p_comuns) c where c is null or not (route.plano->'commons' ? c))
       or not p_agenda_comuns <@ p_comuns
       or array_position(p_agenda_comuns,null) is not null then
        raise exception 'Selecione somente comuns deste roteiro';
    end if;
    stats=public.visitas_previa_remocao_comuns_roteiro(p_id,p_data,p_municipio);
    if stats->>'version' is distinct from p_expected_version then
        raise exception 'O roteiro ou a agenda mudou. Carregue novamente antes de excluir.';
    end if;
    -- IDs dos moradores no snapshot, vinculo do roteiro e data: nenhuma
    -- consulta por nome livre pode alcancar agenda de outra comum/roteiro.
    delete from public.visitas_agenda a where a.roteiro_regional_id=p_id and a.status='Marcada'
        and a.data_inicio>=p_data::timestamp at time zone 'America/Sao_Paulo'
        and a.data_inicio<(p_data+1)::timestamp at time zone 'America/Sao_Paulo'
        and exists(select 1 from jsonb_array_elements(route.plano->'houses') h,
            lateral jsonb_array_elements(h->'members') m
            where m->>'id'=a.irmandade_id::text and exists(select 1 from unnest(p_agenda_comuns) c
                where public.visitas_chave_comum_roteiro(coalesce(m->>'codigo_comum',m->>'comum'))=public.visitas_chave_comum_roteiro(c)));
    get diagnostics removed=row_count;
    select coalesce(jsonb_agg(c.value),'[]') into remaining
        from jsonb_array_elements_text(route.plano->'commons') c where not c.value=any(p_comuns);
    houses='[]'::jsonb;
    for house in select value from jsonb_array_elements(route.plano->'houses') loop
        select coalesce(jsonb_agg(m.value),'[]') into members from jsonb_array_elements(house->'members') m
            where not exists(select 1 from unnest(p_comuns) c
                where public.visitas_chave_comum_roteiro(coalesce(m.value->>'codigo_comum',m.value->>'comum'))=public.visitas_chave_comum_roteiro(c));
        if jsonb_array_length(members)=0 then continue; end if;
        select coalesce(jsonb_agg(v.value),'[]') into visits
            from jsonb_array_elements(coalesce(house->'visit_ids','[]')) v
            where exists(select 1 from public.visitas_agenda a where a.id::text=v.value#>>'{}'
                and exists(select 1 from jsonb_array_elements(members) m where m->>'id'=a.irmandade_id::text));
        updated_house=house || jsonb_build_object('members',members,'visit_ids',visits);
        houses=houses || jsonb_build_array(updated_house);
    end loop;
    updated_plan=route.plano || jsonb_build_object('commons',remaining,'houses',houses,
        'records_in_plan',(select coalesce(sum(jsonb_array_length(h->'members')),0) from jsonb_array_elements(houses) h),
        'coverage',(select coalesce(jsonb_agg(c.value),'[]') from jsonb_array_elements(coalesce(route.plano->'coverage','[]')) c
            where not c.value->>'common'=any(p_comuns)),
        'origins',(select coalesce(jsonb_object_agg(key,value),'{}') from jsonb_each(coalesce(route.plano->'origins','{}'))
            where not key=any(p_comuns)),
        'groups',(select coalesce(jsonb_agg(
            (case when g.value->>'origin_common'=any(p_comuns) then g.value-'origin_common'-'origin' else g.value end)
            || jsonb_build_object('origins',(select coalesce(jsonb_object_agg(key,value),'{}')
                from jsonb_each(coalesce(g.value->'origins','{}')) where not key=any(p_comuns)))),'[]') from jsonb_array_elements(route.plano->'groups') g
            where exists(select 1 from jsonb_array_elements(houses) h where h->>'group_id'=g.value->>'id')),
        'removals',coalesce(route.plano->'removals','[]') || jsonb_build_array(jsonb_build_object(
            'at',clock_timestamp(),'actor',p_actor,'commons',to_jsonb(p_comuns),
            'agenda_commons',to_jsonb(p_agenda_comuns),'deleted_visits',removed)));
    if jsonb_array_length(remaining)=0 then
        updated_plan=updated_plan || jsonb_build_object('deleted_at',clock_timestamp(),'deleted_by',p_actor);
    end if;
    update public.visitas_roteiros_regionais set plano=updated_plan where id=p_id;
    result=jsonb_build_object('deleted',removed,'remaining_commons',remaining,'removed_commons',to_jsonb(p_comuns));
    return result;
end;
$$;

revoke all on function public.visitas_previa_remocao_comuns_roteiro(uuid,date,text) from public,anon,authenticated;
revoke all on function public.visitas_chave_comum_roteiro(text) from public,anon,authenticated;
grant execute on function public.visitas_chave_comum_roteiro(text) to service_role;
revoke all on function public.visitas_remover_comuns_roteiro(uuid,date,text,uuid,text,text[],text[]) from public,anon,authenticated;
grant execute on function public.visitas_previa_remocao_comuns_roteiro(uuid,date,text) to service_role;
grant execute on function public.visitas_remover_comuns_roteiro(uuid,date,text,uuid,text,text[],text[]) to service_role;
notify pgrst,'reload schema';
commit;
