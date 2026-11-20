-- Exclusão administrativa com auditoria preservada. Aplicar após 062.
begin;
alter table public.musica_justificativas_vinculos_auditoria
    alter column justificativa_id drop not null;
alter table public.musica_justificativas_vinculos_auditoria
    drop constraint if exists musica_justificativas_vinculos_auditoria_justificativa_id_fkey;
alter table public.musica_justificativas_vinculos_auditoria
    add constraint musica_justificativas_vinculos_auditoria_justificativa_id_fkey
    foreign key(justificativa_id) references public.musica_justificativas_publicas(id) on delete set null;

create or replace function public.musica_justificativa_excluir(
    p_source text,p_id uuid,p_event uuid,p_person text,p_actor text,p_name text)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare v_before jsonb;
begin
    if nullif(btrim(p_actor),'') is null or nullif(btrim(p_name),'') is null then
        raise exception 'Identifique o responsável pela exclusão.';
    end if;
    if p_source='public' then
        select to_jsonb(j) into v_before from public.musica_justificativas_publicas j where id=p_id for update;
        if v_before is null then return jsonb_build_object('deleted',false); end if;
        insert into public.musica_justificativas_vinculos_auditoria
            (justificativa_id,anterior,posterior,usuario_id,usuario_nome)
        values(p_id,v_before,jsonb_build_object('operacao','EXCLUIR','id',p_id),p_actor,p_name);
        delete from public.musica_justificativas_publicas where id=p_id;
    elsif p_source='ministry' then
        select to_jsonb(j) into v_before from public.musica_ministerio_participacoes j
            where event_id=p_event and person_key=p_person and situacao='JUSTIFICOU' for update;
        if v_before is null then return jsonb_build_object('deleted',false); end if;
        insert into public.musica_ministerio_auditoria
            (event_id,person_key,operacao,anterior,posterior,usuario_id,usuario_nome)
        values(p_event,p_person,'EXCLUIR_JUSTIFICATIVA',v_before,'{}',p_actor,p_name);
        delete from public.musica_ministerio_participacoes
            where event_id=p_event and person_key=p_person and situacao='JUSTIFICOU';
    else
        raise exception 'Origem inválida.';
    end if;
    return jsonb_build_object('deleted',true);
end $$;
revoke all on function public.musica_justificativa_excluir(text,uuid,uuid,text,text,text) from public,anon,authenticated;
grant execute on function public.musica_justificativa_excluir(text,uuid,uuid,text,text,text) to service_role;
notify pgrst,'reload schema';
commit;
