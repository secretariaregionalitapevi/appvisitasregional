alter table public.visitas_irmandade
    add column if not exists preferencia_periodo_visita text;

alter table public.visitas_irmandade
    drop constraint if exists visitas_irmandade_preferencia_periodo_check;

alter table public.visitas_irmandade
    add constraint visitas_irmandade_preferencia_periodo_check
    check (preferencia_periodo_visita is null or preferencia_periodo_visita in ('Manhã', 'Tarde'));

comment on column public.visitas_irmandade.preferencia_periodo_visita is
    'Período preferido pelo membro para receber visitas: Manhã ou Tarde.';
