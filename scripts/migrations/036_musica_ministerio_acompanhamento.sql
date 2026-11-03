-- Histórico individual do Ministério da Música. Não altera ensaios e RTs existentes.
begin;
create table if not exists public.musica_ministerio_pessoas (
    person_key text primary key check(btrim(person_key)<>''),
    nome text not null,
    comum text not null,
    municipio text not null,
    roles jsonb not null,
    created_at timestamptz not null default now()
);
create table if not exists public.musica_ministerio_eventos (
    id uuid primary key default gen_random_uuid(),
    titulo text not null check(length(btrim(titulo)) between 1 and 140),
    tipo text not null check(tipo in ('REUNIAO_MINISTERIO','ENSAIO_REGIONAL','ENSAIO_MUNICIPAL','REUNIAO_TECNICA','CAPACITACAO')),
    data_evento date not null,
    modalidade text not null check(modalidade in ('PRESENCIAL','ONLINE','HIBRIDO')),
    local text not null check(length(btrim(local)) between 1 and 120),
    familia text not null default 'GERAL' check(familia in ('GERAL','CORDAS','MADEIRAS','METAIS')),
    municipios jsonb not null check(jsonb_typeof(municipios)='array' and jsonb_array_length(municipios)>0),
    cargos jsonb not null check(jsonb_typeof(cargos)='array' and jsonb_array_length(cargos)>0),
    lista_completa boolean not null default false,
    arquivo_sha256 text unique check(arquivo_sha256 ~ '^[a-f0-9]{64}$'),
    arquivo_nome text,
    created_at timestamptz not null default now(),
    created_by_user_id text not null check(btrim(created_by_user_id)<>''),
    created_by_name text not null check(btrim(created_by_name)<>'')
);
create unique index if not exists musica_ministerio_encontro_uidx
    on public.musica_ministerio_eventos(data_evento,tipo,modalidade,lower(titulo));
create table if not exists public.musica_ministerio_participacoes (
    event_id uuid not null references public.musica_ministerio_eventos(id),
    person_key text not null check(btrim(person_key)<>''),
    nome text not null check(btrim(nome)<>''),
    comum text not null check(btrim(comum)<>''),
    municipio text not null check(btrim(municipio)<>''),
    roles jsonb not null check(jsonb_typeof(roles)='array' and jsonb_array_length(roles)>0),
    situacao text not null check(situacao in ('PRESENTE','JUSTIFICOU','SEM_REGISTRO','CONFERIR','SEM_DADOS','NAO_APLICA')),
    observacoes text not null default '' check(length(observacoes)<=1000),
    source jsonb not null default '{}',
    version integer not null default 1,
    updated_at timestamptz not null default now(),
    primary key(event_id,person_key),
    check(situacao<>'JUSTIFICOU' or btrim(observacoes)<>'')
);
create table if not exists public.musica_ministerio_auditoria (
    id bigint generated always as identity primary key,
    event_id uuid references public.musica_ministerio_eventos(id),
    legacy_event_id uuid references public.musica_eventos(id),
    person_key text,
    operacao text not null,
    anterior jsonb,
    posterior jsonb not null,
    usuario_id text not null,
    usuario_nome text not null,
    created_at timestamptz not null default now(),
    check((event_id is not null)<>(legacy_event_id is not null))
);
create table if not exists public.musica_ministerio_legado_conferencias (
    event_id uuid not null references public.musica_eventos(id),
    person_key text not null,
    nome text not null,
    comum text not null,
    municipio text not null,
    roles jsonb not null,
    situacao text not null check(situacao in ('PRESENTE','JUSTIFICOU','SEM_REGISTRO','CONFERIR','SEM_DADOS','NAO_APLICA')),
    observacoes text not null default '' check(length(observacoes)<=1000),
    version integer not null default 1,
    updated_at timestamptz not null default now(),
    primary key(event_id,person_key),
    check(situacao<>'JUSTIFICOU' or btrim(observacoes)<>'')
);
alter table public.musica_ministerio_legado_conferencias enable row level security;
revoke all on public.musica_ministerio_legado_conferencias from anon,authenticated;
grant select,insert,update on public.musica_ministerio_legado_conferencias to service_role;
alter table public.musica_ministerio_eventos enable row level security;
alter table public.musica_ministerio_pessoas enable row level security;
alter table public.musica_ministerio_participacoes enable row level security;
alter table public.musica_ministerio_auditoria enable row level security;
revoke all on public.musica_ministerio_eventos,public.musica_ministerio_participacoes,public.musica_ministerio_auditoria from anon,authenticated;
revoke all on public.musica_ministerio_pessoas from anon,authenticated;
grant select,insert on public.musica_ministerio_pessoas to service_role;
grant select,insert on public.musica_ministerio_eventos to service_role;
grant select,insert,update on public.musica_ministerio_participacoes to service_role;
grant select,insert on public.musica_ministerio_auditoria to service_role;
grant usage,select on sequence public.musica_ministerio_auditoria_id_seq to service_role;

create or replace function public.musica_ministerio_salvar(p_evento jsonb,p_hash text,p_arquivo text,p_usuario_id text,p_usuario_nome text)
returns jsonb language plpgsql set search_path=public,pg_temp as $$
declare v_id uuid; r jsonb;
begin
    if nullif(btrim(p_usuario_id),'') is null or nullif(btrim(p_usuario_nome),'') is null then
        raise exception 'Responsável obrigatório.';
    end if;
    if p_hash is not null then
        perform pg_advisory_xact_lock(hashtextextended(p_hash,0));
        select id into v_id from public.musica_ministerio_eventos where arquivo_sha256=p_hash;
        if v_id is not null then return jsonb_build_object('id',v_id,'existing',true); end if;
    end if;
    if nullif(p_evento->>'event_id','') is not null then
        select id into strict v_id from public.musica_ministerio_eventos where id=(p_evento->>'event_id')::uuid and arquivo_sha256 is null for update;
        update public.musica_ministerio_eventos set arquivo_sha256=p_hash,arquivo_nome=p_arquivo,
            lista_completa=(p_evento->>'lista_completa')::boolean where id=v_id;
    else
    insert into public.musica_ministerio_eventos(titulo,tipo,data_evento,modalidade,local,familia,municipios,cargos,lista_completa,
        arquivo_sha256,arquivo_nome,created_by_user_id,created_by_name)
    values(p_evento->>'titulo',p_evento->>'tipo',(p_evento->>'data_evento')::date,p_evento->>'modalidade',p_evento->>'local',
        p_evento->>'familia',p_evento->'municipios',p_evento->'cargos',(p_evento->>'lista_completa')::boolean,
        p_hash,p_arquivo,p_usuario_id,p_usuario_nome) returning id into v_id;
    end if;
    for r in select * from jsonb_array_elements(p_evento->'registros') loop
        insert into public.musica_ministerio_pessoas(person_key,nome,comum,municipio,roles)
        values(r->>'person_key',r->>'nome',r->>'comum',r->>'municipio',r->'roles') on conflict(person_key) do nothing;
        insert into public.musica_ministerio_participacoes(event_id,person_key,nome,comum,municipio,roles,situacao,observacoes,source)
        values(v_id,r->>'person_key',r->>'nome',r->>'comum',r->>'municipio',r->'roles',r->>'situacao',coalesce(r->>'observacoes',''),coalesce(r->'source','{}'))
        on conflict(event_id,person_key) do update set situacao=excluded.situacao,source=excluded.source,
            observacoes=excluded.observacoes,version=musica_ministerio_participacoes.version+1,updated_at=now();
    end loop;
    insert into public.musica_ministerio_auditoria(event_id,operacao,posterior,usuario_id,usuario_nome)
    values(v_id,case when nullif(p_evento->>'event_id','') is not null then 'IMPORTAR_LISTA' else 'CRIAR' end,p_evento,p_usuario_id,p_usuario_nome);
    return jsonb_build_object('id',v_id,'existing',false);
end $$;

create or replace function public.musica_ministerio_conferir_legado(p_evento uuid,p_pessoa jsonb,p_version integer,p_usuario_id text,p_usuario_nome text)
returns jsonb language plpgsql set search_path=public,pg_temp as $$
declare v_old jsonb; v_new jsonb;
begin
    if nullif(btrim(p_usuario_id),'') is null or nullif(btrim(p_usuario_nome),'') is null then raise exception 'Responsável obrigatório.'; end if;
    perform pg_advisory_xact_lock(hashtextextended(p_evento::text || (p_pessoa->>'person_key'),0));
    select to_jsonb(p) into v_old from public.musica_ministerio_legado_conferencias p
        where event_id=p_evento and person_key=p_pessoa->>'person_key' for update;
    if coalesce((v_old->>'version')::integer,0)<>p_version then raise exception 'Registro alterado por outro usuário. Atualize a página.'; end if;
    insert into public.musica_ministerio_legado_conferencias as saved(event_id,person_key,nome,comum,municipio,roles,situacao,observacoes)
    values(p_evento,p_pessoa->>'person_key',p_pessoa->>'nome',p_pessoa->>'comum',p_pessoa->>'municipio',p_pessoa->'roles',p_pessoa->>'situacao',p_pessoa->>'observacoes')
    on conflict(event_id,person_key) do update set situacao=excluded.situacao,observacoes=excluded.observacoes,
        version=saved.version+1,updated_at=now() returning to_jsonb(saved) into v_new;
    insert into public.musica_ministerio_auditoria(legacy_event_id,person_key,operacao,anterior,posterior,usuario_id,usuario_nome)
    values(p_evento,p_pessoa->>'person_key','CONFERIR_LEGADO',v_old,v_new,p_usuario_id,p_usuario_nome);
    return v_new;
end $$;
revoke all on function public.musica_ministerio_conferir_legado(uuid,jsonb,integer,text,text) from public,anon,authenticated;
grant execute on function public.musica_ministerio_conferir_legado(uuid,jsonb,integer,text,text) to service_role;

create or replace function public.musica_ministerio_conferir(p_evento uuid,p_pessoa text,p_situacao text,p_observacoes text,p_version integer,p_usuario_id text,p_usuario_nome text)
returns jsonb language plpgsql set search_path=public,pg_temp as $$
declare v_old jsonb; v_new jsonb;
begin
    if nullif(btrim(p_usuario_id),'') is null or nullif(btrim(p_usuario_nome),'') is null then raise exception 'Responsável obrigatório.'; end if;
    select to_jsonb(p) into strict v_old from public.musica_ministerio_participacoes p
        where event_id=p_evento and person_key=p_pessoa for update;
    if (v_old->>'version')::integer<>p_version then raise exception 'Registro alterado por outro usuário. Atualize a página.'; end if;
    update public.musica_ministerio_participacoes p set situacao=p_situacao,observacoes=p_observacoes,version=version+1,updated_at=now()
        where event_id=p_evento and person_key=p_pessoa returning to_jsonb(p) into v_new;
    insert into public.musica_ministerio_auditoria(event_id,person_key,operacao,anterior,posterior,usuario_id,usuario_nome)
    values(p_evento,p_pessoa,'CONFERIR',v_old,v_new,p_usuario_id,p_usuario_nome);
    return v_new;
end $$;
revoke all on function public.musica_ministerio_salvar(jsonb,text,text,text,text) from public,anon,authenticated;
revoke all on function public.musica_ministerio_conferir(uuid,text,text,text,integer,text,text) from public,anon,authenticated;
grant execute on function public.musica_ministerio_salvar(jsonb,text,text,text,text) to service_role;
grant execute on function public.musica_ministerio_conferir(uuid,text,text,text,integer,text,text) to service_role;
grant update on public.musica_ministerio_eventos to service_role;
notify pgrst,'reload schema';
commit;
