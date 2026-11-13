-- RJM and Culto Oficial are separate levels. Only officialization may retain
-- the RJM prefix, which identifies the unmarried musician/organist category.
begin;

update public.musica_acompanhamento_aluno
set nivel = 'CULTO OFICIAL', updated_at = now()
where upper(btrim(nivel)) = 'RJM / CULTO OFICIAL';

update public.sam_level_history
set new_level = 'CULTO OFICIAL',
    evidence = evidence || jsonb_build_object('normalized_from', 'RJM / CULTO OFICIAL')
where new_level = 'RJM / CULTO OFICIAL'
  and evidence->>'exam_id' = 'c2825408-132e-48c5-894c-7382c02ae765';

update public.sam_level_history
set previous_level = 'CULTO OFICIAL'
where previous_level = 'RJM / CULTO OFICIAL'
  and evidence->>'exam_id' = 'c2825408-132e-48c5-894c-7382c02ae765';

update public.sam_cadastro_transicoes
set anterior = case
        when anterior = to_jsonb('RJM / CULTO OFICIAL'::text) then to_jsonb('CULTO OFICIAL'::text)
        else anterior
    end,
    posterior = case
        when posterior = to_jsonb('RJM / CULTO OFICIAL'::text) then to_jsonb('CULTO OFICIAL'::text)
        else posterior
    end
where campo = 'nivel'
  and (
      anterior = to_jsonb('RJM / CULTO OFICIAL'::text)
      or posterior = to_jsonb('RJM / CULTO OFICIAL'::text)
  );

alter table public.musica_acompanhamento_aluno
    drop constraint if exists musica_acompanhamento_nivel_sem_rjm_culto;
alter table public.musica_acompanhamento_aluno
    add constraint musica_acompanhamento_nivel_sem_rjm_culto
    check (upper(btrim(coalesce(nivel, ''))) <> 'RJM / CULTO OFICIAL');

commit;
