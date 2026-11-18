-- Coordenadores por data e distribuicao regional atomica, preservando equipes locais.
begin;

create table if not exists public.visitas_participacao_regional (
    data date not null,
    municipio text not null,
    equipe_id uuid not null references public.visitas_equipes(id),
    confirmado boolean not null default false,
    coordenador_nome text not null default '',
    updated_by uuid not null,
    updated_at timestamptz not null default now(),
    primary key (data, municipio, equipe_id),
    check (not confirmado or length(trim(coordenador_nome)) between 1 and 180)
);

create table if not exists public.visitas_roteiros_regionais (
    id uuid primary key,
    data date not null,
    municipio text not null,
    criado_por uuid not null,
    created_at timestamptz not null default now(),
    substituido_em timestamptz,
    plano jsonb not null
);
alter table public.visitas_roteiros_regionais add column if not exists substituido_em timestamptz;

alter table public.visitas_agenda add column if not exists roteiro_regional_id uuid
    references public.visitas_roteiros_regionais(id);
create index if not exists visitas_roteiros_regionais_data_idx
    on public.visitas_roteiros_regionais(data, municipio);
create index if not exists visitas_agenda_roteiro_regional_idx
    on public.visitas_agenda(roteiro_regional_id);

alter table public.visitas_participacao_regional enable row level security;
alter table public.visitas_roteiros_regionais enable row level security;
revoke all on public.visitas_participacao_regional, public.visitas_roteiros_regionais from public, anon, authenticated;
grant all on public.visitas_participacao_regional, public.visitas_roteiros_regionais to service_role;

create or replace function public.visitas_versao_agenda_regional(p_data date)
returns text language sql stable set search_path = public as $$
    select md5(coalesce(jsonb_agg(to_jsonb(a) order by a.id)::text, '[]'))
    from public.visitas_agenda a
    where a.data_inicio >= (p_data::timestamp at time zone 'America/Sao_Paulo')
      and a.data_inicio < ((p_data+1)::timestamp at time zone 'America/Sao_Paulo');
$$;

create or replace function public.visitas_salvar_participacao_regional(
    p_data date, p_municipio text, p_actor uuid, p_grupos jsonb
) returns void language plpgsql set search_path = public as $$
declare g jsonb;
begin
    perform pg_advisory_xact_lock(hashtextextended(p_data::text || ':' || p_municipio, 0));
    for g in select value from jsonb_array_elements(p_grupos) loop
        if not exists(select 1 from public.visitas_equipes e where e.id=(g->>'id')::uuid
            and e.tipo='REGIONAL' and e.municipio=p_municipio and e.ativo) then
            raise exception 'Grupo fora do municipio ou inativo';
        end if;
        if (select p.updated_at from public.visitas_participacao_regional p
            where p.data=p_data and p.municipio=p_municipio and p.equipe_id=(g->>'id')::uuid)
            is distinct from nullif(g->>'expected_updated_at','')::timestamptz then
            raise exception 'As confirmacoes mudaram. Carregue os grupos novamente.';
        end if;
        insert into public.visitas_participacao_regional(data,municipio,equipe_id,confirmado,coordenador_nome,updated_by)
        values(p_data,p_municipio,(g->>'id')::uuid,(g->>'confirmado')::boolean,trim(g->>'coordenador_nome'),p_actor)
        on conflict(data,municipio,equipe_id) do update set
            confirmado=excluded.confirmado, coordenador_nome=excluded.coordenador_nome,
            updated_by=excluded.updated_by, updated_at=now();
    end loop;
end;
$$;

create or replace function public.visitas_confirmar_roteiro_regional(
    p_id uuid, p_data date, p_municipio text, p_actor uuid, p_versao text, p_plano jsonb
) returns uuid language plpgsql set search_path = public as $$
declare h jsonb; g jsonb; m jsonb; v_id text; current_member public.visitas_irmandade%rowtype;
begin
    perform pg_advisory_xact_lock(hashtextextended(p_data::text || ':' || p_municipio, 0));
    -- Chave idempotente: repetir uma confirmacao nao duplica agendamentos.
    if exists(select 1 from public.visitas_roteiros_regionais where id=p_id and criado_por=p_actor) then
        return p_id;
    end if;
    -- Bloqueia escritas concorrentes enquanto confere e grava o lote inteiro.
    lock table public.visitas_agenda in share row exclusive mode;
    lock table public.visitas_participacao_regional in share mode;
    if public.visitas_versao_agenda_regional(p_data) <> p_versao then
        raise exception 'A agenda mudou. Gere uma nova previa.';
    end if;
    for g in select value from jsonb_array_elements(p_plano->'groups') loop
        perform 1 from public.visitas_equipes where id=(g->>'id')::uuid for share;
        if not exists(select 1 from public.visitas_participacao_regional p
            join public.visitas_equipes e on e.id=p.equipe_id
            where p.data=p_data and p.municipio=p_municipio and p.equipe_id=(g->>'id')::uuid
              and p.confirmado and p.coordenador_nome=g->>'coordenador_nome'
              and e.ativo and e.tipo='REGIONAL' and e.municipio=p_municipio and e.nome=g->>'nome') then
            raise exception 'A confirmacao ou o coordenador mudou. Gere uma nova previa.';
        end if;
    end loop;
    for h in select value from jsonb_array_elements(p_plano->'houses') loop
        for m in select value from jsonb_array_elements(h->'members') loop
            select * into current_member from public.visitas_irmandade where id=(m->>'id')::uuid for share;
            if not found or current_member.comum is distinct from m->>'comum'
                or coalesce(current_member.endereco,'') <> coalesce(m->>'endereco','') then
                raise exception 'O cadastro de uma familia mudou. Gere uma nova previa.';
            end if;
        end loop;
    end loop;
    insert into public.visitas_roteiros_regionais(id,data,municipio,criado_por,plano)
        values(p_id,p_data,p_municipio,p_actor,p_plano);
    update public.visitas_roteiros_regionais set substituido_em=now()
    where id <> p_id and id in (
        select a.roteiro_regional_id from public.visitas_agenda a
        where a.id in (select visit_item.value::uuid
                      from jsonb_array_elements(p_plano->'houses') as house_item(value),
                      lateral jsonb_array_elements_text(house_item.value->'visit_ids') as visit_item(value))
    );
    for h in select value from jsonb_array_elements(p_plano->'houses') loop
        select value into g from jsonb_array_elements(p_plano->'groups') where value->>'id'=h->>'group_id';
        if g is null then raise exception 'Grupo nao confirmado'; end if;
        if jsonb_array_length(h->'visit_ids') > 0 then
            for v_id in select jsonb_array_elements_text(h->'visit_ids') loop
                update public.visitas_agenda set equipe_id=(g->>'id')::uuid, equipe_responsavel=g->>'nome',
                    equipe_tipo='REGIONAL', data_inicio=(h->>'start')::timestamptz,
                    data_fim=(h->>'end')::timestamptz, roteiro_regional_id=p_id
                where id=v_id::uuid and status='Marcada'
                    and data_inicio >= (p_data::timestamp at time zone 'America/Sao_Paulo')
                    and data_inicio < ((p_data+1)::timestamp at time zone 'America/Sao_Paulo');
                if not found then raise exception 'Visita alterada. Gere uma nova previa.'; end if;
            end loop;
        end if;
        -- Uma parada por casa, com vinculo individual para cada cadastro.
        -- Completa tambem os vinculos ausentes em agendamentos legados.
        for m in select value from jsonb_array_elements(h->'members') loop
            if not exists(select 1 from public.visitas_agenda a
                where a.roteiro_regional_id=p_id and a.irmandade_id=(m->>'id')::uuid) then
                insert into public.visitas_agenda(irmandade_id,titulo,setor,endereco_visitado,categoria,
                    equipe_id,equipe_responsavel,equipe_tipo,data_inicio,data_fim,status,observacoes,roteiro_regional_id)
                values((m->>'id')::uuid,m->>'nome',h->>'bairro',m->>'endereco',
                    coalesce(nullif(m->>'categoria',''),'GVI'),(g->>'id')::uuid,g->>'nome','REGIONAL',
                    (h->>'start')::timestamptz,(h->>'end')::timestamptz,'Marcada','',p_id);
            end if;
        end loop;
    end loop;
    return p_id;
end;
$$;

revoke all on function public.visitas_versao_agenda_regional(date) from public, anon, authenticated;
revoke all on function public.visitas_salvar_participacao_regional(date,text,uuid,jsonb) from public, anon, authenticated;
revoke all on function public.visitas_confirmar_roteiro_regional(uuid,date,text,uuid,text,jsonb) from public, anon, authenticated;
grant execute on function public.visitas_versao_agenda_regional(date) to service_role;
grant execute on function public.visitas_salvar_participacao_regional(date,text,uuid,jsonb) to service_role;
grant execute on function public.visitas_confirmar_roteiro_regional(uuid,date,text,uuid,text,jsonb) to service_role;
notify pgrst, 'reload schema';
commit;
