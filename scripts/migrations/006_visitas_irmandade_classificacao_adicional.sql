-- Mantém categoria para a classificação regional (GVI/GVM/GVE/RF/RE) e
-- armazena Avivamento, Resgate e classificações locais em campo independente.
alter table public.visitas_irmandade
    add column if not exists classificacao_adicional text null;

comment on column public.visitas_irmandade.classificacao_adicional is
    'Classificação complementar local, como Avivamento ou Resgate; não substitui a categoria regional.';

-- Corrige os registros já importados pelo fluxo anterior, que preservou esse
-- conteúdo temporariamente ao final das observações.
update public.visitas_irmandade
set classificacao_adicional = trim(split_part(split_part(observacoes, 'Categoria de origem: ', 2), ' | ', 1)),
    observacoes = nullif(trim(regexp_replace(observacoes, '(\s*\|\s*)?Categoria de origem: [^|]+$', '')), '')
where classificacao_adicional is null
  and observacoes like '%Categoria de origem: %';
