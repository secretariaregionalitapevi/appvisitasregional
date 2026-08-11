-- Permite que o mesmo integrante participe simultaneamente de uma equipe
-- da comum e de um grupo regional.

alter table public.visitas_irmandade
    add column if not exists grupo_regional_id uuid null
        references public.visitas_equipes(id) on delete set null;

alter table public.visitas_irmandade
    add column if not exists grupo_regional_nome text null;

create index if not exists visitas_irmandade_grupo_regional_id_idx
    on public.visitas_irmandade (grupo_regional_id);

-- Move para o vínculo regional as atribuições regionais que estavam ocupando
-- o campo da equipe local. Cadastros de pessoas são preservados.
update public.visitas_irmandade i
set grupo_regional_id = e.id,
    grupo_regional_nome = e.nome,
    equipe_id = null,
    equipe_visita = null
from public.visitas_equipes e
where i.equipe_id = e.id
  and e.tipo = 'REGIONAL'
  and i.grupo_regional_id is null;

comment on column public.visitas_irmandade.grupo_regional_id is
    'Grupo regional do integrante, independente da equipe local da comum.';

comment on column public.visitas_irmandade.grupo_regional_nome is
    'Nome desnormalizado do grupo regional para compatibilidade e relatórios.';
