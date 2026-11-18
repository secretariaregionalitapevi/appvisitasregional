-- Coordenador do cadastro separado da disponibilidade e do historico por data.
begin;
alter table public.visitas_equipes add column if not exists coordenador_nome text;
alter table public.visitas_equipes drop constraint if exists visitas_equipes_coordenador_tamanho;
alter table public.visitas_equipes add constraint visitas_equipes_coordenador_tamanho
    check (coordenador_nome is null or length(coordenador_nome)<=180);

-- Resgata a atribuicao mais recente ja salva pelo planejador, sem tocar roteiros.
update public.visitas_equipes e set coordenador_nome=p.coordenador_nome
from (select distinct on (equipe_id) equipe_id,coordenador_nome
      from public.visitas_participacao_regional order by equipe_id,updated_at desc,data desc) p
where e.id=p.equipe_id and e.tipo='REGIONAL' and e.coordenador_nome is null;

create or replace function public.visitas_salvar_participacao_regional(
    p_data date,p_municipio text,p_actor uuid,p_grupos jsonb
) returns void language plpgsql set search_path=public as $$
declare g jsonb; current_coordinator text;
begin
    perform pg_advisory_xact_lock(hashtextextended(p_data::text || ':' || p_municipio,0));
    for g in select value from jsonb_array_elements(p_grupos) order by value->>'id' loop
        select e.coordenador_nome into current_coordinator from public.visitas_equipes e
        where e.id=(g->>'id')::uuid and e.tipo='REGIONAL' and e.municipio=p_municipio and e.ativo for update;
        if not found then raise exception 'Grupo fora do municipio ou inativo'; end if;
        if (select p.updated_at from public.visitas_participacao_regional p
            where p.data=p_data and p.municipio=p_municipio and p.equipe_id=(g->>'id')::uuid)
            is distinct from nullif(g->>'expected_updated_at','')::timestamptz then
            raise exception 'As confirmacoes mudaram. Carregue os grupos novamente.';
        end if;
        if coalesce((g->>'atualizar_cadastro')::boolean,false) then
            if current_coordinator is distinct from g->>'expected_coordenador_cadastrado' then
                raise exception 'O coordenador cadastrado mudou. Carregue os grupos novamente.';
            end if;
            update public.visitas_equipes set coordenador_nome=trim(g->>'coordenador_nome'),updated_at=now()
            where id=(g->>'id')::uuid;
        end if;
        insert into public.visitas_participacao_regional(data,municipio,equipe_id,confirmado,coordenador_nome,updated_by)
        values(p_data,p_municipio,(g->>'id')::uuid,(g->>'confirmado')::boolean,trim(g->>'coordenador_nome'),p_actor)
        on conflict(data,municipio,equipe_id) do update set confirmado=excluded.confirmado,
            coordenador_nome=excluded.coordenador_nome,updated_by=excluded.updated_by,updated_at=clock_timestamp();
    end loop;
end;
$$;
revoke all on function public.visitas_salvar_participacao_regional(date,text,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.visitas_salvar_participacao_regional(date,text,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
