-- Corrige somente as chaves das tabelas D.A.R.P.E legadas para UUID.
-- O cadastro canônico é abastecido exclusivamente pela planilha oficial;
-- a tabela darpe_musicos contém repetições e não pode ser consolidada nela.
begin;

-- As tabelas antigas não possuem FKs declaradas; os vínculos de atendimentos
-- eram guardados como bigint e JSON. Os mapas preservam esses vínculos.
create temporary table darpe_musicos_id_map (old_id bigint primary key, new_id uuid not null);
insert into darpe_musicos_id_map select id, gen_random_uuid() from public.darpe_musicos;
create temporary table darpe_clinicas_id_map (old_id bigint primary key, new_id uuid not null);
insert into darpe_clinicas_id_map select id, gen_random_uuid() from public.darpe_clinicas;

alter table public.darpe_musicos add column id_uuid uuid;
update public.darpe_musicos m set id_uuid=map.new_id from darpe_musicos_id_map map where map.old_id=m.id;
alter table public.darpe_musicos alter column id_uuid set default gen_random_uuid();
alter table public.darpe_musicos alter column id_uuid set not null;
alter table public.darpe_musicos drop constraint darpe_musicos_pkey;
alter table public.darpe_musicos drop column id;
alter table public.darpe_musicos rename column id_uuid to id;
alter table public.darpe_musicos add primary key (id);

alter table public.darpe_clinicas add column id_uuid uuid;
update public.darpe_clinicas c set id_uuid=map.new_id from darpe_clinicas_id_map map where map.old_id=c.id;
alter table public.darpe_clinicas alter column id_uuid set default gen_random_uuid();
alter table public.darpe_clinicas alter column id_uuid set not null;
alter table public.darpe_clinicas drop constraint darpe_clinicas_pkey;
alter table public.darpe_clinicas drop column id;
alter table public.darpe_clinicas rename column id_uuid to id;
alter table public.darpe_clinicas add primary key (id);

-- Preserva o vínculo do local antes de substituir o bigint.
alter table public.darpe_atendimentos add column local_uuid uuid;
update public.darpe_atendimentos a set local_uuid=map.new_id
from darpe_clinicas_id_map map where map.old_id=a.local_id;
alter table public.darpe_atendimentos drop column local_id;
alter table public.darpe_atendimentos rename column local_uuid to local_id;
alter table public.darpe_atendimentos
    add constraint darpe_atendimentos_local_fk foreign key (local_id) references public.darpe_clinicas(id);

-- Converte a lista JSON de IDs numéricos para os UUIDs correspondentes.
update public.darpe_atendimentos a
set musicos_ids=coalesce((
    select jsonb_agg(to_jsonb(map.new_id::text))
    from jsonb_array_elements_text(coalesce(a.musicos_ids,'[]'::jsonb)) item
    join darpe_musicos_id_map map on map.old_id=item.value::bigint
),'[]'::jsonb);

alter table public.darpe_atendimentos add column id_uuid uuid not null default gen_random_uuid();
alter table public.darpe_atendimentos drop constraint darpe_atendimentos_pkey;
alter table public.darpe_atendimentos drop column id;
alter table public.darpe_atendimentos rename column id_uuid to id;
alter table public.darpe_atendimentos add primary key (id);

alter table public.darpe_batismos add column id_uuid uuid not null default gen_random_uuid();
alter table public.darpe_batismos drop constraint darpe_batismos_pkey;
alter table public.darpe_batismos drop column id;
alter table public.darpe_batismos rename column id_uuid to id;
alter table public.darpe_batismos add primary key (id);

notify pgrst, 'reload schema';
commit;
