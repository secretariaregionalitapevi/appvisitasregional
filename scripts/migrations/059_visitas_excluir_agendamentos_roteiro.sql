-- Exclui os agendamentos de uma distribuicao, mantendo o registro de auditoria.
begin;

create or replace function public.visitas_previa_exclusao_roteiro_regional(
    p_id uuid,p_data date,p_municipio text
) returns jsonb language plpgsql set search_path=public as $$
declare result jsonb;
begin
    if not exists(select 1 from public.visitas_roteiros_regionais
        where id=p_id and data=p_data and municipio=p_municipio and plano->>'deleted_at' is null) then
        raise exception 'Roteiro nao encontrado ou excluido';
    end if;
    select jsonb_build_object('agendamentos',count(*),
        'protegidos',count(*) filter(where coalesce(status,'') <> 'Marcada'),
        'version',md5(coalesce(jsonb_agg(to_jsonb(a) order by a.id)::text,'[]')))
    into result from public.visitas_agenda a where a.roteiro_regional_id=p_id;
    return result;
end;
$$;

create or replace function public.visitas_excluir_agendamentos_roteiro_regional(
    p_id uuid,p_data date,p_municipio text,p_actor uuid,p_expected_version text
) returns integer language plpgsql set search_path=public as $$
declare current_plan public.visitas_roteiros_regionais%rowtype;
        current_version text; removed integer;
begin
    perform pg_advisory_xact_lock(hashtextextended(p_data::text || ':' || p_municipio,0));
    lock table public.visitas_agenda in share row exclusive mode;
    select * into current_plan from public.visitas_roteiros_regionais
    where id=p_id and data=p_data and municipio=p_municipio for update;
    if not found then raise exception 'Roteiro fora do municipio ou inexistente'; end if;
    if current_plan.plano->>'deleted_at' is not null then return 0; end if;
    if exists(select 1 from public.visitas_agenda
        where roteiro_regional_id=p_id and coalesce(status,'') <> 'Marcada') then
        raise exception 'O roteiro possui visitas encerradas ou em andamento. Exclusao bloqueada.';
    end if;
    select md5(coalesce(jsonb_agg(to_jsonb(a) order by a.id)::text,'[]')) into current_version
    from public.visitas_agenda a where a.roteiro_regional_id=p_id;
    if current_version is distinct from p_expected_version then
        raise exception 'Os agendamentos mudaram. Carregue o roteiro novamente antes de excluir.';
    end if;
    delete from public.visitas_agenda where roteiro_regional_id=p_id and status='Marcada';
    get diagnostics removed=row_count;
    update public.visitas_roteiros_regionais set plano=plano || jsonb_build_object(
        'deleted_at',clock_timestamp(),'deleted_by',p_actor,'deleted_visits',removed)
    where id=p_id;
    return removed;
end;
$$;

revoke all on function public.visitas_previa_exclusao_roteiro_regional(uuid,date,text) from public,anon,authenticated;
revoke all on function public.visitas_excluir_agendamentos_roteiro_regional(uuid,date,text,uuid,text) from public,anon,authenticated;
grant execute on function public.visitas_previa_exclusao_roteiro_regional(uuid,date,text) to service_role;
grant execute on function public.visitas_excluir_agendamentos_roteiro_regional(uuid,date,text,uuid,text) to service_role;
notify pgrst,'reload schema';
commit;
