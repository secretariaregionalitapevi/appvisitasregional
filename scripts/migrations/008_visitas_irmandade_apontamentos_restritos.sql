alter table public.visitas_irmandade
    add column if not exists apontamentos_restritos text null;

comment on column public.visitas_irmandade.apontamentos_restritos is
    'Informações sensíveis de visita, retornadas pelo sistema somente a Coordenadores, Admin e Master.';
