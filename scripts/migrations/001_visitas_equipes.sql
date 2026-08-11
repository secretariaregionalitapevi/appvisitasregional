-- A equipe pertence ao membro já existente em visitas_irmandade.
-- Execute uma vez no SQL Editor do Supabase.

alter table public.visitas_irmandade
    add column if not exists equipe_visita text null;

create index if not exists visitas_irmandade_comum_equipe_idx
    on public.visitas_irmandade (comum, equipe_visita);

comment on column public.visitas_irmandade.equipe_visita is
'Equipe na qual o membro atua como integrante do grupo de visitas.';

-- Atribuições informadas para a Vila Doutor Cardoso.
update public.visitas_irmandade
set equipe_visita = 'Equipe 1'
where comum = 'BR-22-0673 - VILA DOUTOR CARDOSO'
  and upper(trim(nome)) in ('RICARDO', 'LUCIANO', 'RODRIGO', 'GERSON');

update public.visitas_irmandade
set equipe_visita = 'Equipe 2'
where comum = 'BR-22-0673 - VILA DOUTOR CARDOSO'
  and upper(trim(nome)) in ('ROGER', 'JAIR');

update public.visitas_irmandade
set cargo_outros = concat_ws(',', nullif(trim(cargo_outros), ''), 'Grupo de Visitas')
where equipe_visita is not null
  and trim(equipe_visita) <> ''
  and lower(coalesce(cargo_outros, '')) not like '%grupo de visitas%';
