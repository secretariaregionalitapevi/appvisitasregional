-- Papeletas compartilhadas entre administração e APP_DARPE.
-- darpe_atendimentos pertence ao legado (agenda); não alterar sua estrutura.
begin;
create table if not exists public.darpe_papeletas (
 id uuid primary key,
 data date not null,
 hora_inicio time not null,
 hora_fim time not null check (hora_fim >= hora_inicio),
 setor smallint not null check (setor between 1 and 4),
 local text not null check (length(btrim(local)) between 1 and 200),
 municipio text not null check (length(btrim(municipio)) between 1 and 100),
 comum text not null check (length(btrim(comum)) between 1 and 200),
 equipe jsonb not null check (jsonb_typeof(equipe)='array' and jsonb_array_length(equipe) between 1 and 200),
 hinos jsonb not null default '[]' check (jsonb_typeof(hinos)='array'),
 palavra text not null default '',
 participacao text not null default '',
 observacoes text not null default '',
 pedidos_oracao jsonb not null default '{}' check (jsonb_typeof(pedidos_oracao)='object'),
 created_by text not null,
 created_by_name text not null,
 created_at timestamptz not null default now()
);
-- Compatibilidade com instalações novas em que a versão inicial da 047
-- chegou a criar papeletas com o nome antigo. Nunca converter a agenda legada.
do $$
begin
 if exists (select 1 from information_schema.columns where table_schema='public'
            and table_name='darpe_atendimentos' and column_name='data')
    and exists (select 1 from information_schema.columns where table_schema='public'
                and table_name='darpe_atendimentos' and column_name='equipe') then
   execute 'insert into public.darpe_papeletas
    (id,data,hora_inicio,hora_fim,setor,local,municipio,comum,equipe,hinos,palavra,
     participacao,observacoes,pedidos_oracao,created_by,created_by_name,created_at)
    select id,data,hora_inicio,hora_fim,setor,local,municipio,comum,equipe,hinos,palavra,
     participacao,observacoes,pedidos_oracao,created_by,created_by_name,created_at
    from public.darpe_atendimentos on conflict (id) do nothing';
 end if;
end $$;
create index if not exists darpe_papeletas_data_idx on public.darpe_papeletas(data desc);
create index if not exists darpe_papeletas_localidade_idx on public.darpe_papeletas(municipio,comum,setor);
alter table public.darpe_papeletas enable row level security;
revoke all on public.darpe_papeletas from anon,authenticated;
revoke all on public.darpe_papeletas from service_role;
grant select,insert on public.darpe_papeletas to service_role;
comment on column public.darpe_papeletas.equipe is 'IDs do darpe_cadastro, função e nome no momento do lançamento. Validação pelo servidor principal.';
notify pgrst, 'reload schema';
commit;
