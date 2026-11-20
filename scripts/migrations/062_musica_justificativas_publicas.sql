-- Formulário público: somente o servidor acessa a tabela. Aplicar após 036 e 056.
begin;
create table if not exists public.musica_justificativas_publicas (
    id uuid primary key default gen_random_uuid(),
    agenda_id text not null check(agenda_id ~ '^[a-f0-9]{24}$'),
    evento_titulo text not null,
    data_evento date not null,
    hora text not null default '',
    tipo text not null check(tipo in ('ENSAIO_REGIONAL','REUNIAO_TECNICA','REUNIAO_MINISTERIO')),
    familia text not null check(familia in ('GERAL','CORDAS','MADEIRAS','METAIS')),
    local text not null default '',
    municipios jsonb not null check(jsonb_typeof(municipios)='array'),
    comum_codigo text not null,
    comum text not null,
    municipio text not null,
    person_key text not null,
    pessoa_identidade text not null check(pessoa_identidade ~ '^[a-f0-9]{64}$'),
    nome text not null,
    motivo text not null check(length(btrim(motivo)) between 5 and 500),
    evento_id uuid references public.musica_eventos(id),
    ministerio_evento_id uuid references public.musica_ministerio_eventos(id),
    vinculado_por_id text,
    vinculado_por_nome text,
    created_at timestamptz not null default now(),
    unique(agenda_id,pessoa_identidade),
    check(not(evento_id is not null and ministerio_evento_id is not null)),
    check(evento_id is null or tipo<>'REUNIAO_MINISTERIO'),
    check(ministerio_evento_id is null or tipo='REUNIAO_MINISTERIO')
);
create index if not exists musica_justificativas_publicas_data_idx
    on public.musica_justificativas_publicas(data_evento,tipo,municipio);
alter table public.musica_justificativas_publicas enable row level security;
revoke all on public.musica_justificativas_publicas from anon,authenticated;
grant select,insert,update on public.musica_justificativas_publicas to service_role;

create table if not exists public.musica_justificativas_vinculos_auditoria (
    id bigint generated always as identity primary key,
    justificativa_id uuid not null references public.musica_justificativas_publicas(id),
    anterior jsonb not null,
    posterior jsonb not null,
    usuario_id text not null,
    usuario_nome text not null,
    created_at timestamptz not null default now()
);
alter table public.musica_justificativas_vinculos_auditoria enable row level security;
revoke all on public.musica_justificativas_vinculos_auditoria from anon,authenticated;
grant select,insert on public.musica_justificativas_vinculos_auditoria to service_role;
grant usage,select on sequence public.musica_justificativas_vinculos_auditoria_id_seq to service_role;

create or replace function public.musica_justificativa_publica_validar()
returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
    if tg_op='INSERT' then
        if new.data_evento < (now() at time zone 'America/Sao_Paulo')::date then
            raise exception 'Prazo de justificativas encerrado.';
        end if;
        new.created_at=now();
    else
        if (to_jsonb(new)-array['evento_id','ministerio_evento_id','vinculado_por_id','vinculado_por_nome'])
            is distinct from (to_jsonb(old)-array['evento_id','ministerio_evento_id','vinculado_por_id','vinculado_por_nome']) then
            raise exception 'Justificativa original é imutável.';
        end if;
        if nullif(btrim(new.vinculado_por_id),'') is null or nullif(btrim(new.vinculado_por_nome),'') is null then
            raise exception 'Identifique o responsável pelo vínculo.';
        end if;
    end if;
    if new.evento_id is not null and not exists(select 1 from public.musica_eventos e
        where e.id=new.evento_id and e.tipo=new.tipo and e.data_evento=new.data_evento and e.familia=new.familia) then
        raise exception 'Evento incompatível com a justificativa.';
    end if;
    if new.ministerio_evento_id is not null and not exists(select 1 from public.musica_ministerio_eventos e
        where e.id=new.ministerio_evento_id and e.tipo=new.tipo and e.data_evento=new.data_evento and e.familia=new.familia) then
        raise exception 'Reunião incompatível com a justificativa.';
    end if;
    return new;
end $$;
drop trigger if exists musica_justificativa_publica_validacao on public.musica_justificativas_publicas;
create trigger musica_justificativa_publica_validacao before insert or update on public.musica_justificativas_publicas
    for each row execute function public.musica_justificativa_publica_validar();
create or replace function public.musica_justificativa_publica_auditar()
returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
    insert into public.musica_justificativas_vinculos_auditoria(justificativa_id,anterior,posterior,usuario_id,usuario_nome)
        values(new.id,to_jsonb(old),to_jsonb(new),new.vinculado_por_id,new.vinculado_por_nome);
    return new;
end $$;
drop trigger if exists musica_justificativa_publica_auditoria on public.musica_justificativas_publicas;
create trigger musica_justificativa_publica_auditoria after update on public.musica_justificativas_publicas
    for each row execute function public.musica_justificativa_publica_auditar();
notify pgrst,'reload schema';
commit;
