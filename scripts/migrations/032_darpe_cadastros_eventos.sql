-- Estrutura própria do D.A.R.P.E, baseada no cadastro regional consolidado.
begin;

-- Inclui a nova pasta no controle de acesso quando essa tabela opcional existir.
-- Alguns ambientes deste projeto autorizam apenas pelo campo sector de profiles
-- e, portanto, ainda não possuem public.user_module_access.
do $$
begin
    if to_regclass('public.user_module_access') is not null then
        alter table public.user_module_access
            drop constraint if exists user_module_access_module_check;
        alter table public.user_module_access
            add constraint user_module_access_module_check
            check (module in ('visitas','musicalizacao','darpe'));
    end if;
end $$;

create table if not exists public.darpe_cadastro (
    id uuid primary key default gen_random_uuid(),
    cpf text unique,
    nome_completo text not null check (btrim(nome_completo) <> ''),
    instrumento_oficializado text,
    rg text,
    data_nascimento date,
    sexo text,
    estado_civil text,
    comum_congregacao text not null check (btrim(comum_congregacao) <> ''),
    data_batismo date,
    logradouro text,
    numero text,
    complemento text,
    bairro text,
    cidade text,
    uf text check (uf is null or uf ~ '^[A-Z]{2}$'),
    cep text,
    ddd text,
    telefone text,
    darpe_ministerio boolean not null default false,
    darpe_atendente boolean not null default false,
    darpe_colaborador boolean not null default false,
    darpe_encarregado boolean not null default false,
    darpe_musico boolean not null default false,
    darpe_organista boolean not null default false,
    darpe_grupo_canto boolean not null default false,
    declaracao_local text,
    declaracao_data date,
    nome_ministerio text,
    nome_encarregado_orquestra text,
    nome_voluntario text,
    status text not null default 'ATIVO' check (status in ('ATIVO','INATIVO')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by_user_id text not null check (btrim(created_by_user_id) <> ''),
    created_by_name text not null check (btrim(created_by_name) <> ''),
    updated_by_user_id text not null check (btrim(updated_by_user_id) <> ''),
    updated_by_name text not null check (btrim(updated_by_name) <> ''),
    check (cpf is null or regexp_replace(cpf, '\D', '', 'g') ~ '^\d{11}$'),
    check (cep is null or regexp_replace(cep, '\D', '', 'g') ~ '^\d{8}$'),
    check (not (darpe_musico and darpe_organista))
);

create index if not exists darpe_cadastro_nome_idx on public.darpe_cadastro (nome_completo);
create index if not exists darpe_cadastro_comum_idx on public.darpe_cadastro (comum_congregacao);
create index if not exists darpe_cadastro_cidade_idx on public.darpe_cadastro (cidade);

create table if not exists public.darpe_eventos (
    id uuid primary key default gen_random_uuid(),
    titulo text not null check (btrim(titulo) <> ''),
    tipo text not null check (btrim(tipo) <> ''),
    data_evento date not null,
    hora_inicio time,
    hora_fim time,
    comum text,
    municipio text not null check (btrim(municipio) <> ''),
    local_evento text not null check (btrim(local_evento) <> ''),
    endereco text,
    status text not null default 'PLANEJADO'
        check (status in ('PLANEJADO','ABERTO','ENCERRADO','CANCELADO')),
    observacoes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by_user_id text not null check (btrim(created_by_user_id) <> ''),
    created_by_name text not null check (btrim(created_by_name) <> ''),
    updated_by_user_id text not null check (btrim(updated_by_user_id) <> ''),
    updated_by_name text not null check (btrim(updated_by_name) <> ''),
    check (hora_fim is null or hora_inicio is null or hora_fim > hora_inicio)
);

create index if not exists darpe_eventos_data_idx on public.darpe_eventos (data_evento desc);
create index if not exists darpe_eventos_municipio_idx on public.darpe_eventos (municipio);

create table if not exists public.darpe_evento_participantes (
    id uuid primary key default gen_random_uuid(),
    evento_id uuid not null references public.darpe_eventos(id) on delete cascade,
    cadastro_id uuid not null references public.darpe_cadastro(id),
    funcao text not null check (funcao in
        ('MINISTERIO','ATENDENTE','COLABORADOR','ENCARREGADO','MUSICO_ORGANISTA','GRUPO_CANTO')),
    situacao text not null default 'INSCRITO'
        check (situacao in ('INSCRITO','PRESENTE','AUSENTE','JUSTIFICADO')),
    observacoes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by_user_id text not null check (btrim(created_by_user_id) <> ''),
    created_by_name text not null check (btrim(created_by_name) <> ''),
    updated_by_user_id text not null check (btrim(updated_by_user_id) <> ''),
    updated_by_name text not null check (btrim(updated_by_name) <> ''),
    unique (evento_id, cadastro_id, funcao)
);

create index if not exists darpe_participantes_evento_idx on public.darpe_evento_participantes (evento_id);
create index if not exists darpe_participantes_cadastro_idx on public.darpe_evento_participantes (cadastro_id);

create or replace function public.darpe_atualizar_timestamp()
returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
    new.updated_at = now();
    return new;
end $$;

drop trigger if exists darpe_cadastro_timestamp on public.darpe_cadastro;
create trigger darpe_cadastro_timestamp before update on public.darpe_cadastro
for each row execute function public.darpe_atualizar_timestamp();
drop trigger if exists darpe_eventos_timestamp on public.darpe_eventos;
create trigger darpe_eventos_timestamp before update on public.darpe_eventos
for each row execute function public.darpe_atualizar_timestamp();
drop trigger if exists darpe_participantes_timestamp on public.darpe_evento_participantes;
create trigger darpe_participantes_timestamp before update on public.darpe_evento_participantes
for each row execute function public.darpe_atualizar_timestamp();

alter table public.darpe_cadastro enable row level security;
alter table public.darpe_eventos enable row level security;
alter table public.darpe_evento_participantes enable row level security;
revoke all on public.darpe_cadastro, public.darpe_eventos, public.darpe_evento_participantes from anon, authenticated;
grant select, insert, update, delete on public.darpe_cadastro, public.darpe_eventos, public.darpe_evento_participantes to service_role;
revoke all on function public.darpe_atualizar_timestamp() from public, anon, authenticated;

comment on table public.darpe_cadastro is 'Cadastro regional dos voluntários do D.A.R.P.E.';
comment on table public.darpe_eventos is 'Agenda de eventos próprios do D.A.R.P.E.';
comment on table public.darpe_evento_participantes is 'Participação e função dos cadastrados em cada evento do D.A.R.P.E.';
notify pgrst, 'reload schema';
commit;
