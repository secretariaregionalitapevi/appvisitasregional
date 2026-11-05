begin;
create table if not exists public.darpe_estatisticas (
 id uuid primary key default gen_random_uuid(),
 competencia date not null check(extract(day from competencia)=1),
 unidades integer not null check(unidades>=0),
 batismos integer not null check(batismos>=0),
 pessoas_batizadas integer not null check(pessoas_batizadas>=0),
 colaboradores integer not null check(colaboradores>=0),
 atendimentos integer not null check(atendimentos>=0),
 fonte text not null check(length(fonte) between 1 and 500),
 observacoes text not null default '' check(length(observacoes)<=3000),
 distribuicao text not null default '' check(length(distribuicao)<=3000),
 created_by text not null,
 responsavel text not null,
 created_at timestamptz not null default clock_timestamp()
);
create index if not exists darpe_estatisticas_competencia on public.darpe_estatisticas(competencia,created_at);
alter table public.darpe_estatisticas enable row level security;
revoke all on public.darpe_estatisticas from anon,authenticated;
grant select,insert on public.darpe_estatisticas to service_role;
create or replace function public.darpe_estatisticas_preservar() returns trigger language plpgsql as $$
begin raise exception 'O histórico é imutável. Registre uma nova publicação.'; end $$;
drop trigger if exists darpe_estatisticas_imutavel on public.darpe_estatisticas;
create trigger darpe_estatisticas_imutavel before update or delete on public.darpe_estatisticas
for each row execute function public.darpe_estatisticas_preservar();
insert into public.darpe_estatisticas(id,competencia,unidades,batismos,pessoas_batizadas,colaboradores,atendimentos,fonte,distribuicao,observacoes,created_by,responsavel)
values('06202610-0000-4000-8000-000000000001','2026-10-01',220,3613,18001,17722,3332,
'Estatísticas gerais até outubro de 2026 fornecidas pela administração.',
'215 unidades no Brasil; 1 em Angola; 1 em Mallorca (Espanha); 1 em Genebra (Suíça); 2 no Paraguai (Asunción e San Alberto).',
'Dados gerais do D.A.R.P.E., no Brasil e exterior. Não representam somente a Regional Itapevi.',
'implantacao-darpe','Administração DARPE') on conflict(id) do nothing;
notify pgrst, 'reload schema';
commit;
