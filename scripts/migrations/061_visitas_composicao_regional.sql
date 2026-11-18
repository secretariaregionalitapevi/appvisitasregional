-- Composicao permanente municipal. Presencas e substituicoes continuam por data.
begin;
alter table public.visitas_equipes add column if not exists exige_confirmacao_data boolean not null default false;
create unique index if not exists visitas_equipes_id_municipio_idx on public.visitas_equipes(id,municipio);

create table if not exists public.visitas_integrantes_regionais (
    id uuid primary key default gen_random_uuid(),
    municipio text not null check(length(trim(municipio))>0),
    nome text not null check(length(trim(nome)) between 1 and 180),
    ministerio text not null default '',
    comum_origem text not null default '',
    ativo boolean not null default true,
    fonte text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(municipio,nome),unique(id,municipio)
);
create table if not exists public.visitas_funcoes_regionais (
    id uuid primary key default gen_random_uuid(),
    municipio text not null,
    integrante_id uuid not null,
    funcao text not null check(funcao in ('RESPONSAVEL','SECRETARIO','APOIO','COORDENADOR','PARTICIPANTE')),
    equipe_id uuid,
    ativo boolean not null default true,
    created_at timestamptz not null default now(),
    check(funcao<>'COORDENADOR' or equipe_id is not null),
    foreign key(integrante_id,municipio) references public.visitas_integrantes_regionais(id,municipio),
    foreign key(equipe_id,municipio) references public.visitas_equipes(id,municipio)
);
create unique index if not exists visitas_funcoes_regionais_vinculo_idx on public.visitas_funcoes_regionais
    (integrante_id,funcao,coalesce(equipe_id,'00000000-0000-0000-0000-000000000000'::uuid)) where ativo;
create unique index if not exists visitas_funcoes_regionais_coordenador_idx on public.visitas_funcoes_regionais(equipe_id)
    where ativo and funcao='COORDENADOR';
alter table public.visitas_participacao_regional add column if not exists coordenador_integrante_id uuid;
alter table public.visitas_participacao_regional drop constraint if exists visitas_participacao_integrante_municipio_fk;
alter table public.visitas_participacao_regional add constraint visitas_participacao_integrante_municipio_fk
    foreign key(coordenador_integrante_id,municipio) references public.visitas_integrantes_regionais(id,municipio);

-- Compatibilidade com o formulario atual, que ainda envia o nome: evita
-- conservar um ID antigo quando o operador troca o coordenador da data.
create or replace function public.visitas_vincular_integrante_participacao()
returns trigger language plpgsql set search_path=public as $$
begin
    perform pg_advisory_xact_lock(hashtextextended(new.data::text || ':' || new.municipio,0));
    select id into new.coordenador_integrante_id from public.visitas_integrantes_regionais
        where municipio=new.municipio and nome=trim(new.coordenador_nome) and ativo;
    if new.confirmado and new.coordenador_integrante_id is not null and exists(
        select 1 from public.visitas_participacao_regional where data=new.data and municipio=new.municipio
        and equipe_id<>new.equipe_id and confirmado
        and (coordenador_integrante_id=new.coordenador_integrante_id or coordenador_nome=new.coordenador_nome)) then
        raise exception 'Integrante ja confirmado em outro grupo nesta data';
    end if;
    return new;
end;
$$;
drop trigger if exists visitas_participacao_integrante_trigger on public.visitas_participacao_regional;
create trigger visitas_participacao_integrante_trigger before insert or update on public.visitas_participacao_regional
    for each row execute function public.visitas_vincular_integrante_participacao();

create table if not exists public.visitas_atribuicoes_regionais_auditoria (
    id uuid primary key default gen_random_uuid(),municipio text not null,data date not null,
    equipe_id uuid not null,integrante_id uuid not null,actor uuid not null,
    confirmado boolean not null,created_at timestamptz not null default now()
);
create or replace function public.visitas_atribuir_integrante_por_data(
    p_municipio text,p_data date,p_equipe_id uuid,p_integrante_id uuid,p_actor uuid,
    p_confirmado boolean,p_expected_updated_at timestamptz default null
) returns void language plpgsql set search_path=public as $$
declare person public.visitas_integrantes_regionais%rowtype;
begin
    if p_actor is null or p_confirmado is null then raise exception 'Informe operador e confirmacao'; end if;
    perform pg_advisory_xact_lock(hashtextextended(p_data::text || ':' || p_municipio,0));
    perform 1 from public.visitas_equipes where id=p_equipe_id and municipio=p_municipio and tipo='REGIONAL' and ativo for update;
    if not found then raise exception 'Grupo fora do municipio ou inativo'; end if;
    select * into person from public.visitas_integrantes_regionais where id=p_integrante_id and municipio=p_municipio and ativo for share;
    if not found then raise exception 'Integrante fora do municipio ou inativo'; end if;
    if (select updated_at from public.visitas_participacao_regional where data=p_data and municipio=p_municipio and equipe_id=p_equipe_id)
        is distinct from p_expected_updated_at then raise exception 'As confirmacoes mudaram. Carregue novamente.'; end if;
    if p_confirmado and exists(select 1 from public.visitas_participacao_regional
        where data=p_data and municipio=p_municipio and equipe_id<>p_equipe_id
        and confirmado and coordenador_integrante_id=p_integrante_id) then
        raise exception 'Integrante ja confirmado em outro grupo nesta data';
    end if;
    insert into public.visitas_participacao_regional(data,municipio,equipe_id,confirmado,coordenador_nome,coordenador_integrante_id,updated_by)
    values(p_data,p_municipio,p_equipe_id,p_confirmado,person.nome,person.id,p_actor)
    on conflict(data,municipio,equipe_id) do update set confirmado=excluded.confirmado,
        coordenador_nome=excluded.coordenador_nome,coordenador_integrante_id=excluded.coordenador_integrante_id,
        updated_by=excluded.updated_by,updated_at=clock_timestamp();
    insert into public.visitas_atribuicoes_regionais_auditoria(municipio,data,equipe_id,integrante_id,actor,confirmado)
    values(p_municipio,p_data,p_equipe_id,p_integrante_id,p_actor,p_confirmado);
end;
$$;

-- Transcricao do documento Ministerio_Visitas_Regional.jpeg. Cores NAO importam presencas.
do $$ declare s record; team_id uuid; person_id uuid; begin
    for s in select * from (values
('Laudelino Guimarães Lima Júnior','Ancião','JD Paulista','RESPONSAVEL',null),
('Anibal Enriquez Canonga','Ancião','Vila Santa Rita','RESPONSAVEL',null),
('Sidney de Aguiar Fogaça','Coop JM','JD Paulista','SECRETARIO',null),
('Alan Henrique Fernandes de Oliveira','Coop do Ofício','JD Alabama','SECRETARIO',null),
('Jean Carlos Nogueira de Oliveira','Coop JM','Nova Itapevi','SECRETARIO',null),
('Adriano Nogueira Jamas','Coop JM','JD Rosemary','SECRETARIO',null),
('Robison Rodrigues Ferreira','Diácono','JD Paulista','APOIO',null),
('José Figueiredo de Oliveira','Diácono','Central de Itapevi','APOIO',null),
('Emerson Nunes Moraes','Coop do Ofício','Alto do Bela Vista','COORDENADOR','A'),
('Isaac de Moraes','Coop do Ofício','Vila Belmira','COORDENADOR','B'),
('Alan Henrique Fernandes de Oliveira','Coop do Ofício','JD Alabama','COORDENADOR','C'),
('Sérgio Henrique de Melo','Coop do Ofício','JD Jurema','COORDENADOR','D'),
('Rafael Pedroso Vitolo','Coop JM','JD Alabama','COORDENADOR','E'),
('Eduardo Oliveira da Cruz','Coop JM','Alto do Paulista','COORDENADOR','F'),
('Adriano Nogueira Jamas','Coop JM','JD Rosemary','COORDENADOR','G'),
('Domenico Luciano Marques','Coop JM','PQ Suburbano I','COORDENADOR','H'),
('Jean Carlos Nogueira de Oliveira','Coop JM','Nova Itapevi','COORDENADOR','I'),
('Ítalo Alves Gançalves','Coop JM','Ambuitá','COORDENADOR','J'),
('Abraão Pereira Neves de Souza','Coop JM','São João','COORDENADOR','K'),
('Luciano Gonçalves Martins','Coop JM','Amador Bueno','COORDENADOR','L'),
('Danilo Cavalcante Coutinho','Coop JM','JD Santa Cecília','COORDENADOR','M'),
('Alex Oliveira dos Santos','Coop JM','PQ Suburbano IV','COORDENADOR','N'),
('Francisco Alves de Faria','Coop JM','JD Jurema','COORDENADOR','O')
    ) as seed(nome,ministerio,comum,funcao,grupo) loop
        insert into public.visitas_integrantes_regionais(municipio,nome,ministerio,comum_origem,fonte)
        values('ITAPEVI',s.nome,s.ministerio,s.comum,'Ministério_Visitas_Regional.jpeg')
        on conflict(municipio,nome) do nothing;
        select id into person_id from public.visitas_integrantes_regionais where municipio='ITAPEVI' and nome=s.nome;
        team_id=null;
        if s.grupo is not null then
            select id into team_id from public.visitas_equipes where upper(municipio)='ITAPEVI' and upper(nome)='GRUPO ' || s.grupo and tipo='REGIONAL';
            if team_id is null then
                insert into public.visitas_equipes(nome,tipo,municipio,ativo,coordenador_nome,exige_confirmacao_data)
                    values('Grupo ' || s.grupo,'REGIONAL','ITAPEVI',true,s.nome,true) returning id into team_id;
            end if;
            update public.visitas_equipes set coordenador_nome=s.nome,ativo=true,exige_confirmacao_data=true where id=team_id;
            update public.visitas_funcoes_regionais set ativo=false where equipe_id=team_id and funcao='COORDENADOR' and ativo and integrante_id<>person_id;
        end if;
        if not exists(select 1 from public.visitas_funcoes_regionais where integrante_id=person_id and funcao=s.funcao and equipe_id is not distinct from team_id and ativo) then
            insert into public.visitas_funcoes_regionais(municipio,integrante_id,funcao,equipe_id) values('ITAPEVI',person_id,s.funcao,team_id);
        end if;
    end loop;
end; $$;

alter table public.visitas_integrantes_regionais enable row level security;
alter table public.visitas_funcoes_regionais enable row level security;
alter table public.visitas_atribuicoes_regionais_auditoria enable row level security;
revoke all on public.visitas_integrantes_regionais,public.visitas_funcoes_regionais,public.visitas_atribuicoes_regionais_auditoria from public,anon,authenticated;
grant all on public.visitas_integrantes_regionais,public.visitas_funcoes_regionais,public.visitas_atribuicoes_regionais_auditoria to service_role;
revoke all on function public.visitas_atribuir_integrante_por_data(text,date,uuid,uuid,uuid,boolean,timestamptz) from public,anon,authenticated;
revoke all on function public.visitas_vincular_integrante_participacao() from public,anon,authenticated;
grant execute on function public.visitas_vincular_integrante_participacao() to service_role;
grant execute on function public.visitas_atribuir_integrante_por_data(text,date,uuid,uuid,uuid,boolean,timestamptz) to service_role;
notify pgrst,'reload schema';
commit;
