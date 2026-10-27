m]ap-- Remove a carga incorreta originada em darpe_musicos e recria a base canônica.
-- Depois desta migration, darpe_cadastro fica vazia e deve receber somente a
-- planilha oficial validada pelo import_darpe_workbook.py.
begin;

-- Participações dependem do UUID do cadastro e precisam ser recriadas junto.
drop table if exists public.darpe_evento_participantes;
drop table if exists public.darpe_cadastro;

create table public.darpe_cadastro (
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
    cidade text not null check (btrim(cidade) <> ''),
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

create unique index darpe_cadastro_pessoa_comum_uidx
    on public.darpe_cadastro (upper(btrim(nome_completo)), upper(btrim(comum_congregacao)));
create index darpe_cadastro_nome_idx on public.darpe_cadastro (nome_completo);
create index darpe_cadastro_comum_idx on public.darpe_cadastro (comum_congregacao);
create index darpe_cadastro_cidade_idx on public.darpe_cadastro (cidade);

create table public.darpe_evento_participantes (
    id uuid primary key default gen_random_uuid(),
    evento_id uuid not null references public.darpe_eventos(id) on delete cascade,
    cadastro_id uuid not null references public.darpe_cadastro(id) on delete cascade,
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

create index darpe_participantes_evento_idx
    on public.darpe_evento_participantes (evento_id);
create index darpe_participantes_cadastro_idx
    on public.darpe_evento_participantes (cadastro_id);

create trigger darpe_cadastro_timestamp before update on public.darpe_cadastro
for each row execute function public.darpe_atualizar_timestamp();
create trigger darpe_participantes_timestamp before update on public.darpe_evento_participantes
for each row execute function public.darpe_atualizar_timestamp();

alter table public.darpe_cadastro enable row level security;
alter table public.darpe_evento_participantes enable row level security;
revoke all on public.darpe_cadastro, public.darpe_evento_participantes from anon, authenticated;
grant select, insert, update, delete on public.darpe_cadastro, public.darpe_evento_participantes to service_role;

comment on table public.darpe_cadastro is
    'Cadastro oficial do D.A.R.P.E, abastecido exclusivamente pela planilha regional validada.';
comment on table public.darpe_evento_participantes is
    'Participações dos integrantes do cadastro oficial em eventos do D.A.R.P.E.';

-- Garante que nenhuma linha da carga legada permaneceu após a reconstrução.
do $$
begin
    if (select count(*) from public.darpe_cadastro) <> 0 then
        raise exception 'A reconstrução do cadastro D.A.R.P.E não terminou vazia.';
    end if;
end $$;

notify pgrst, 'reload schema';
commit;
