-- Separa a função musical do D.A.R.P.E no mesmo padrão do cadastro de irmandade.
begin;

alter table public.darpe_cadastro
    add column if not exists darpe_musico boolean not null default false,
    add column if not exists darpe_organista boolean not null default false;

-- A planilha legada possuía uma única marcação. Órgão e cadastro feminino
-- identificam organistas; os demais registros marcados ficam como músicos.
update public.darpe_cadastro
set darpe_organista = darpe_musico_organista
        and (
            upper(translate(coalesce(instrumento_oficializado,''),'ÃÁÀÂÄÉÈÊËÍÌÎÏÕÓÒÔÖÚÙÛÜÇ','AAAAAEEEEIIIIOOOOOUUUUC')) like '%ORGAO%'
            or upper(coalesce(sexo,'')) = 'FEMININO'
        ),
    darpe_musico = darpe_musico_organista
        and not (
            upper(translate(coalesce(instrumento_oficializado,''),'ÃÁÀÂÄÉÈÊËÍÌÎÏÕÓÒÔÖÚÙÛÜÇ','AAAAAEEEEIIIIOOOOOUUUUC')) like '%ORGAO%'
            or upper(coalesce(sexo,'')) = 'FEMININO'
        );

alter table public.darpe_cadastro
    drop constraint if exists darpe_cadastro_funcao_musical_check;
alter table public.darpe_cadastro
    add constraint darpe_cadastro_funcao_musical_check
    check (not (darpe_musico and darpe_organista));

comment on column public.darpe_cadastro.darpe_musico is
    'Identifica exclusivamente o músico no atendimento D.A.R.P.E.';
comment on column public.darpe_cadastro.darpe_organista is
    'Identifica exclusivamente a organista no atendimento D.A.R.P.E.';

notify pgrst, 'reload schema';
commit;
