-- Ensaios regionais e reuniões técnicas: modelo nominal com base SAM histórica.
-- Preparação do módulo. Executar em homologação antes de produção.
-- O navegador NÃO recebe service_role. Somente o backend autorizado escreve.
begin;

create table if not exists public.musica_evento_comuns (
    codigo text primary key check (codigo ~ '^BR-[0-9]+-[0-9]+$'),
    nome text not null check (btrim(nome) <> ''),
    municipio text not null check (btrim(municipio) <> ''),
    regional text not null default 'ITAPEVI'
);

-- Uma captura só pode ser homologada após conferir paginação e cobertura.
-- Não usar a lista de alunos GEM como se fosse o cadastro individual completo.
create table if not exists public.musica_evento_bases (
    id uuid primary key default gen_random_uuid(),
    referencia date not null,
    origem text not null check (btrim(origem) <> ''),
    arquivo_sha256 text check (arquivo_sha256 ~ '^[a-f0-9]{64}$'),
    capturada_em timestamptz not null default now(),
    homologada_em timestamptz,
    homologada_por_id text,
    homologada_por_nome text,
    created_by_user_id text not null check (btrim(created_by_user_id) <> ''),
    created_by_name text not null check (btrim(created_by_name) <> ''),
    observacoes text,
    check ((homologada_em is null and homologada_por_id is null and homologada_por_nome is null)
        or (homologada_em is not null and homologada_por_id is not null
            and homologada_por_nome is not null and btrim(homologada_por_id) <> ''
            and btrim(homologada_por_nome) <> ''))
);

-- Uma comum coberta pode ter zero pessoas. Ausência de cobertura não é zero.
create table if not exists public.musica_evento_base_cobertura (
    base_id uuid not null references public.musica_evento_bases(id),
    comum_codigo text not null references public.musica_evento_comuns(codigo),
    comum_nome text not null check (btrim(comum_nome) <> ''),
    municipio text not null check (btrim(municipio) <> ''),
    completa boolean not null default false,
    quantidade_fonte integer not null check (quantidade_fonte >= 0),
    primary key (base_id, comum_codigo)
);

create table if not exists public.musica_evento_base_pessoas (
    base_id uuid not null references public.musica_evento_bases(id),
    sam_pessoa_id text not null check (btrim(sam_pessoa_id) <> ''),
    comum_codigo text not null,
    nome text not null check (btrim(nome) <> ''),
    categoria text not null check (categoria in ('MUSICO','ORGANISTA')),
    familia text not null check (familia in ('CORDAS','MADEIRAS','METAIS','TECLADO','OUTROS')),
    instrumento text,
    nivel text,
    cargo text,
    ativo boolean not null,
    primary key (base_id, sam_pessoa_id),
    foreign key (base_id, comum_codigo)
        references public.musica_evento_base_cobertura(base_id, comum_codigo),
    check (categoria <> 'ORGANISTA' or familia = 'TECLADO')
);

-- Um evento administrativo agrupa os encontros simultâneos (locais).
create table if not exists public.musica_eventos (
    id uuid primary key default gen_random_uuid(),
    titulo text not null check (btrim(titulo) <> ''),
    data_evento date not null,
    tipo text not null check (tipo in ('ENSAIO_REGIONAL','REUNIAO_TECNICA')),
    familia text not null default 'GERAL'
        check (familia in ('GERAL','CORDAS','MADEIRAS','METAIS','ORGANISTAS')),
    base_id uuid not null references public.musica_evento_bases(id),
    criterio_publico text not null default 'ATIVOS_TODOS_NIVEIS'
        check (criterio_publico = 'ATIVOS_TODOS_NIVEIS'),
    status text not null default 'RASCUNHO' check (status in ('RASCUNHO','ABERTO','ENCERRADO')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by_user_id text not null check (btrim(created_by_user_id) <> ''),
    created_by_name text not null check (btrim(created_by_name) <> ''),
    updated_by_user_id text not null check (btrim(updated_by_user_id) <> ''),
    updated_by_name text not null check (btrim(updated_by_name) <> ''),
    observacoes text,
    check (tipo <> 'ENSAIO_REGIONAL' or familia = 'GERAL')
);

create table if not exists public.musica_evento_locais (
    id uuid primary key default gen_random_uuid(),
    evento_id uuid not null references public.musica_eventos(id),
    nome text not null check (btrim(nome) <> ''),
    municipio text not null check (btrim(municipio) <> ''),
    comum_sede_codigo text references public.musica_evento_comuns(codigo),
    horario time,
    presidencia text,
    atendimento text,
    atendimento_adicional text,
    hino_cantado integer check (hino_cantado between 1 and 480),
    palavra text,
    hinos_ensaiados integer[] not null default '{}',
    -- Contagem complementar só para pessoas NÃO cadastradas nominalmente.
    irmandade_nao_nominal integer not null default 0 check (irmandade_nao_nominal >= 0),
    apoio_nao_nominal integer not null default 0 check (apoio_nao_nominal >= 0),
    check (1 <= all(hinos_ensaiados) and 480 >= all(hinos_ensaiados)
        and array_position(hinos_ensaiados,null) is null),
    unique (evento_id, nome),
    unique (evento_id, id)
);

-- Cada comum é convocada uma única vez no evento consolidado.
-- O local de referência não impede alguém de comparecer em outro local.
create table if not exists public.musica_evento_convocacoes (
    evento_id uuid not null references public.musica_eventos(id),
    comum_codigo text not null references public.musica_evento_comuns(codigo),
    local_referencia_id uuid not null,
    encarregado_situacao text not null default 'NAO_INFORMADO'
        check (encarregado_situacao in ('NAO_INFORMADO','PRESENTE','JUSTIFICOU',
            'NAO_JUSTIFICOU','SEM_ENCARREGADO','ENFERMO')),
    encarregado_observacoes text,
    primary key (evento_id, comum_codigo),
    foreign key (evento_id, local_referencia_id) references public.musica_evento_locais(evento_id,id)
);

create table if not exists public.musica_evento_presencas (
    id uuid primary key default gen_random_uuid(),
    evento_id uuid not null references public.musica_eventos(id),
    local_id uuid not null,
    -- Com vínculo: SAM:<id>. Sem vínculo: EXTERNO:<uuid estável>, nunca nome sozinho.
    pessoa_chave text not null check (btrim(pessoa_chave) <> ''),
    sam_pessoa_id text,
    nome text not null check (btrim(nome) <> ''),
    comum_codigo text references public.musica_evento_comuns(codigo),
    comum_informada text,
    municipio_informado text,
    categoria text not null check (categoria in ('MUSICO','ORGANISTA','MINISTERIO','APOIO','IRMANDADE')),
    instrumento text,
    familia text check (familia in ('CORDAS','MADEIRAS','METAIS','TECLADO','OUTROS')),
    nivel text,
    cargo text,
    situacao text not null default 'PRESENTE' check (situacao in ('PRESENTE','JUSTIFICADO','CANCELADO')),
    origem text not null check (origem in ('MANUAL','XLSX','SAM')),
    origem_registro_id text,
    origem_arquivo_sha256 text check (origem_arquivo_sha256 ~ '^[a-f0-9]{64}$'),
    registrado_por_legado text,
    registrado_em_legado timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by_user_id text not null check (btrim(created_by_user_id) <> ''),
    created_by_name text not null check (btrim(created_by_name) <> ''),
    updated_by_user_id text not null check (btrim(updated_by_user_id) <> ''),
    updated_by_name text not null check (btrim(updated_by_name) <> ''),
    observacoes text,
    unique (evento_id,pessoa_chave),
    foreign key (evento_id,local_id) references public.musica_evento_locais(evento_id,id),
    check ((sam_pessoa_id is not null and pessoa_chave = 'SAM:' || sam_pessoa_id)
        or (sam_pessoa_id is null and pessoa_chave ~ '^EXTERNO:[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')),
    check (categoria not in ('MUSICO','ORGANISTA') or familia is not null)
);
create unique index if not exists musica_evento_presenca_origem_uidx
    on public.musica_evento_presencas(evento_id,origem,origem_registro_id)
    where origem_registro_id is not null;
create index if not exists musica_eventos_data_idx on public.musica_eventos(data_evento desc);
create index if not exists musica_evento_presenca_local_idx on public.musica_evento_presencas(evento_id,local_id);
create index if not exists musica_evento_base_comum_idx on public.musica_evento_base_pessoas(base_id,comum_codigo);

create table if not exists public.musica_evento_auditoria (
    id bigint generated always as identity primary key,
    tabela text not null,
    registro_id text not null,
    operacao text not null,
    executado_em timestamptz not null default now(),
    usuario_id text not null,
    usuario_nome text not null,
    anterior jsonb,
    posterior jsonb
);

-- Captura homologada fica imutável, mesmo antes de ser vinculada a eventos.
create or replace function public.musica_evento_proteger_base()
returns trigger language plpgsql set search_path = public, pg_temp as $$
declare v_base uuid;
begin
    if tg_table_name = 'musica_evento_bases' then
        if tg_op = 'INSERT' and new.homologada_em is not null then
            raise exception 'Importe a base como rascunho antes de homologar.';
        end if;
        if tg_op <> 'INSERT' and old.homologada_em is not null then
            raise exception 'Base SAM homologada é imutável; crie uma nova captura.';
        end if;
        if tg_op = 'UPDATE' and new.homologada_em is not null then
            if not exists (select 1 from public.musica_evento_base_cobertura where base_id = new.id)
                or exists (select 1 from public.musica_evento_base_cobertura c
                    where c.base_id = new.id and (not c.completa or c.quantidade_fonte <>
                        (select count(*) from public.musica_evento_base_pessoas p
                            where p.base_id = c.base_id and p.comum_codigo = c.comum_codigo))) then
                raise exception 'Cobertura incompleta ou contagem SAM divergente.';
            end if;
        end if;
    else
        v_base := case when tg_op = 'DELETE' then old.base_id else new.base_id end;
        perform 1 from public.musica_evento_bases where id = v_base for update;
        if exists (select 1 from public.musica_evento_bases where id = v_base and homologada_em is not null)
            or (tg_op = 'UPDATE' and exists (select 1 from public.musica_evento_bases
                where id = old.base_id and homologada_em is not null)) then
            raise exception 'Conteúdo da base SAM homologada é imutável.';
        end if;
    end if;
    if tg_op = 'DELETE' then return old; end if;
    return new;
end $$;

drop trigger if exists musica_evento_base_imutavel on public.musica_evento_bases;
create trigger musica_evento_base_imutavel before insert or update or delete on public.musica_evento_bases
    for each row execute function public.musica_evento_proteger_base();
drop trigger if exists musica_evento_pessoas_imutaveis on public.musica_evento_base_pessoas;
create trigger musica_evento_pessoas_imutaveis before insert or update or delete on public.musica_evento_base_pessoas
    for each row execute function public.musica_evento_proteger_base();
drop trigger if exists musica_evento_cobertura_imutavel on public.musica_evento_base_cobertura;
create trigger musica_evento_cobertura_imutavel before insert or update or delete on public.musica_evento_base_cobertura
    for each row execute function public.musica_evento_proteger_base();

create or replace function public.musica_evento_validar_presenca()
returns trigger language plpgsql set search_path = public, pg_temp as $$
declare v_evento public.musica_eventos; v_pessoa public.musica_evento_base_pessoas;
begin
    select * into strict v_evento from public.musica_eventos where id = new.evento_id for share;
    if v_evento.status <> 'ABERTO' then raise exception 'Evento não está aberto para lançamentos.'; end if;
    if tg_op = 'UPDATE' then
        if new.evento_id <> old.evento_id or new.pessoa_chave <> old.pessoa_chave
            or new.created_by_user_id <> old.created_by_user_id or new.created_by_name <> old.created_by_name
            or new.created_at <> old.created_at then
            raise exception 'Identidade do lançamento e autoria original são imutáveis.';
        end if;
    end if;
    if new.sam_pessoa_id is not null then
        select * into v_pessoa from public.musica_evento_base_pessoas
            where base_id = v_evento.base_id and sam_pessoa_id = new.sam_pessoa_id;
        if not found then raise exception 'Pessoa não consta da captura SAM deste evento.'; end if;
        if new.comum_codigo is distinct from v_pessoa.comum_codigo
            or (new.categoria in ('MUSICO','ORGANISTA') and
                (new.categoria <> v_pessoa.categoria or new.familia is distinct from v_pessoa.familia)) then
            raise exception 'Comum/categoria/família divergente da base SAM; revisar o vínculo.';
        end if;
    end if;
    new.updated_at := now();
    return new;
end $$;
drop trigger if exists musica_evento_presenca_validar on public.musica_evento_presencas;
create trigger musica_evento_presenca_validar before insert or update on public.musica_evento_presencas
    for each row execute function public.musica_evento_validar_presenca();

create or replace function public.musica_evento_validar_evento()
returns trigger language plpgsql set search_path = public, pg_temp as $$
begin
    if tg_op = 'UPDATE' then
        if new.base_id <> old.base_id or new.tipo <> old.tipo or new.familia <> old.familia
            or new.data_evento <> old.data_evento or new.created_by_user_id <> old.created_by_user_id
            or new.created_by_name <> old.created_by_name or new.created_at <> old.created_at then
            raise exception 'Base, data, público e autoria são imutáveis; crie outro evento.';
        end if;
    end if;
    if new.status <> 'RASCUNHO' then
        if not exists (select 1 from public.musica_evento_bases where id = new.base_id and homologada_em is not null)
            or not exists (select 1 from public.musica_evento_convocacoes where evento_id = new.id) then
            raise exception 'Homologue a base e defina as comuns convocadas antes de abrir o evento.';
        end if;
        if exists (select 1 from public.musica_evento_convocacoes c
            left join public.musica_evento_base_cobertura b on b.base_id = new.base_id and b.comum_codigo = c.comum_codigo
            where c.evento_id = new.id and (b.completa is distinct from true)) then
            raise exception 'Base SAM incompleta para as comuns convocadas.';
        end if;
    end if;
    new.updated_at := now();
    return new;
end $$;
drop trigger if exists musica_evento_validar on public.musica_eventos;
create trigger musica_evento_validar before insert or update on public.musica_eventos
    for each row execute function public.musica_evento_validar_evento();

create or replace function public.musica_evento_auditar()
returns trigger language plpgsql security definer set search_path = public, pg_temp as $$
declare v_novo jsonb := to_jsonb(new);
begin
    insert into public.musica_evento_auditoria(tabela,registro_id,operacao,usuario_id,usuario_nome,anterior,posterior)
        values (tg_table_name,new.id::text,tg_op,new.updated_by_user_id,new.updated_by_name,
            case when tg_op = 'UPDATE' then to_jsonb(old) else null end,v_novo);
    return new;
end $$;
drop trigger if exists musica_eventos_auditoria on public.musica_eventos;
create trigger musica_eventos_auditoria after insert or update on public.musica_eventos
    for each row execute function public.musica_evento_auditar();
drop trigger if exists musica_evento_presencas_auditoria on public.musica_evento_presencas;
create trigger musica_evento_presencas_auditoria after insert or update on public.musica_evento_presencas
    for each row execute function public.musica_evento_auditar();

-- População elegível: ativos, todos os níveis; RT usa apenas a família convocada.
create or replace view public.musica_evento_elegiveis with (security_invoker = true) as
select e.id evento_id,p.*
from public.musica_eventos e
join public.musica_evento_base_pessoas p on p.base_id = e.base_id
join public.musica_evento_convocacoes c on c.evento_id = e.id and c.comum_codigo = p.comum_codigo
where p.ativo and (e.familia = 'GERAL'
    or (e.familia = 'ORGANISTAS' and p.categoria = 'ORGANISTA')
    or (e.familia = p.familia and p.categoria = 'MUSICO'));

-- Uma linha por comum, inclusive quando nenhuma presença foi registrada.
-- Presenças em qualquer local contam para a comum de origem do participante.
create or replace view public.musica_evento_frequencia with (security_invoker = true) as
with base as (
    select evento_id,comum_codigo,
        count(*) filter(where categoria = 'MUSICO')::integer musicos_base,
        count(*) filter(where categoria = 'ORGANISTA')::integer organistas_base
    from public.musica_evento_elegiveis group by evento_id,comum_codigo
), presentes as (
    select p.evento_id,b.comum_codigo,
        count(*) filter(where b.categoria = 'MUSICO')::integer musicos_presentes,
        count(*) filter(where b.categoria = 'ORGANISTA')::integer organistas_presentes
    from public.musica_evento_presencas p join public.musica_evento_elegiveis b
        on b.evento_id = p.evento_id and b.sam_pessoa_id = p.sam_pessoa_id
    where p.situacao = 'PRESENTE' and p.categoria = b.categoria
    group by p.evento_id,b.comum_codigo
)
select e.id evento_id,c.comum_codigo,coalesce(cobertura.comum_nome,k.nome) comum,
    coalesce(cobertura.municipio,k.municipio) municipio,c.local_referencia_id,
    c.encarregado_situacao,
    (s.homologada_em is not null and cobertura.completa is true) base_validada,
    coalesce(b.musicos_base,0) musicos_base,coalesce(b.organistas_base,0) organistas_base,
    coalesce(p.musicos_presentes,0) musicos_presentes,coalesce(p.organistas_presentes,0) organistas_presentes,
    case when s.homologada_em is not null and cobertura.completa is true
        then round(100.0 * coalesce(p.musicos_presentes,0) / nullif(b.musicos_base,0),2) end percentual_musicos,
    case when s.homologada_em is not null and cobertura.completa is true
        then round(100.0 * coalesce(p.organistas_presentes,0) / nullif(b.organistas_base,0),2) end percentual_organistas
from public.musica_eventos e
join public.musica_evento_bases s on s.id = e.base_id
join public.musica_evento_convocacoes c on c.evento_id = e.id
join public.musica_evento_comuns k on k.codigo = c.comum_codigo
left join public.musica_evento_base_cobertura cobertura on cobertura.base_id = e.base_id and cobertura.comum_codigo = c.comum_codigo
left join base b on b.evento_id = e.id and b.comum_codigo = c.comum_codigo
left join presentes p on p.evento_id = e.id and p.comum_codigo = c.comum_codigo;

-- Percentual consolidado é razão das somas, nunca média de percentuais.
create or replace view public.musica_evento_frequencia_totais with (security_invoker = true) as
select evento_id,sum(musicos_base) musicos_base,sum(organistas_base) organistas_base,
    sum(musicos_presentes) musicos_presentes,sum(organistas_presentes) organistas_presentes,
    case when bool_and(base_validada) then round(100.0 * sum(musicos_presentes) / nullif(sum(musicos_base),0),2) end percentual_musicos,
    case when bool_and(base_validada) then round(100.0 * sum(organistas_presentes) / nullif(sum(organistas_base),0),2) end percentual_organistas
from public.musica_evento_frequencia group by evento_id;

create or replace view public.musica_evento_resumo_local with (security_invoker = true) as
select l.evento_id,l.id local_id,l.nome,l.municipio,
    count(p.id) filter(where p.categoria = 'MUSICO') musicos,
    count(p.id) filter(where p.categoria = 'ORGANISTA') organistas,
    count(p.id) filter(where p.categoria = 'MINISTERIO') ministerio,
    count(p.id) filter(where p.categoria = 'APOIO') + l.apoio_nao_nominal apoio,
    count(p.id) filter(where p.categoria = 'IRMANDADE') + l.irmandade_nao_nominal irmandade,
    count(p.id) + l.apoio_nao_nominal + l.irmandade_nao_nominal total_geral
from public.musica_evento_locais l left join public.musica_evento_presencas p
    on p.evento_id = l.evento_id and p.local_id = l.id and p.situacao = 'PRESENTE'
group by l.evento_id,l.id,l.nome,l.municipio,l.apoio_nao_nominal,l.irmandade_nao_nominal;

-- Não há políticas públicas: o Django aplica pasta e escopo territorial.
-- service_role não deve ser entregue ao cliente; não habilitar acesso anon.
do $$
declare tabela text;
begin
    foreach tabela in array array['musica_evento_comuns','musica_evento_bases',
        'musica_evento_base_cobertura','musica_evento_base_pessoas','musica_eventos',
        'musica_evento_locais','musica_evento_convocacoes','musica_evento_presencas','musica_evento_auditoria'] loop
        execute format('alter table public.%I enable row level security',tabela);
        execute format('revoke all on public.%I from anon, authenticated',tabela);
        execute format('grant select,insert,update on public.%I to service_role',tabela);
        execute format('revoke delete on public.%I from service_role',tabela);
    end loop;
end $$;
revoke insert,update on public.musica_evento_auditoria from service_role;
grant usage,select on sequence public.musica_evento_auditoria_id_seq to service_role;
revoke all on public.musica_evento_elegiveis,public.musica_evento_frequencia,
    public.musica_evento_frequencia_totais,public.musica_evento_resumo_local from anon,authenticated;
grant select on public.musica_evento_elegiveis,public.musica_evento_frequencia,
    public.musica_evento_frequencia_totais,public.musica_evento_resumo_local to service_role;
revoke all on function public.musica_evento_proteger_base(),public.musica_evento_validar_presenca(),
    public.musica_evento_validar_evento(),public.musica_evento_auditar() from public,anon,authenticated;

comment on table public.musica_eventos is
'Evento administrativo com vários locais; base SAM histórica, ativos de todos os níveis.';
comment on view public.musica_evento_frequencia is
'Somente presentes elegíveis vinculados ao SAM no numerador. Visitantes aparecem no resumo administrativo.';
notify pgrst, 'reload schema';
commit;
