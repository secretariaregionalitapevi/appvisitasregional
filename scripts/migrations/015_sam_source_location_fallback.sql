-- Preserva município e dados cadastrais do catálogo SAM mesmo antes da
-- conciliação do aluno com musica_acompanhamento_aluno.
create or replace view public.sam_mirror_student_status as
select
    s.id as sync_state_id,
    s.aluno_id,
    s.source_name,
    coalesce(a.municipio, nullif(s.source_payload ->> 'city', '')) as municipio,
    coalesce(a.comum_congregacao, s.source_common, nullif(s.source_payload ->> 'common_name', '')) as comum_congregacao,
    coalesce(a.instrumento, s.source_instrument, nullif(s.source_payload ->> 'instrument', '')) as instrumento,
    coalesce(a.nivel, s.source_level, nullif(s.source_payload ->> 'level', '')) as nivel,
    s.sync_status,
    s.last_seen_at,
    s.last_history_sync_at,
    s.last_error,
    activity.last_activity_at,
    case
      when activity.last_activity_at is null then 'SEM HISTORICO'
      when current_date - activity.last_activity_at::date > 365 then 'EXCLUIR'
      when current_date - activity.last_activity_at::date > 180 then 'INATIVO'
      when current_date - activity.last_activity_at::date > 90 then 'ALERTA'
      else 'ATIVO'
    end as operational_status,
    case when activity.last_activity_at is null then null
         else current_date - activity.last_activity_at::date end as inactive_days,
    coalesce(a.cargo_ministerio, nullif(s.source_payload ->> 'ministry', '')) as cargo_ministerio,
    latest_msa.last_msa_date,
    latest_msa.last_msa_phase,
    latest_msa.last_msa_observations
from public.sam_student_sync_state s
left join public.musica_acompanhamento_aluno a on a.id = s.aluno_id
left join lateral (
    select max(event_date) as last_activity_at from (
      select max(data_aula)::date event_date from public.musica_acompanhamento_msa where aluno_id = s.aluno_id
      union all select max(data_inicio)::date from public.musica_acompanhamento_metodo where aluno_id = s.aluno_id
      union all select max(data)::date from public.musica_acompanhamento_hinario where aluno_id = s.aluno_id
      union all select max(data_prova)::date from public.musica_acompanhamento_provas where aluno_id = s.aluno_id
      union all select max(data)::date from public.musica_acompanhamento_escala where aluno_id = s.aluno_id
      union all select max(data_atividade)::date from public.musica_acompanhamento_atividades where aluno_id = s.aluno_id
    ) dates
) activity on true
left join lateral (
    select m.data_aula as last_msa_date, m.fase as last_msa_phase, m.observacoes as last_msa_observations
    from public.musica_acompanhamento_msa m
    where m.aluno_id = s.aluno_id
    order by m.data_aula desc nulls last
    limit 1
) latest_msa on true;

grant select on table public.sam_mirror_student_status to service_role;

comment on view public.sam_mirror_student_status is
'Relatório operacional SAM. Para alunos ainda não conciliados, município, comum, instrumento, nível e ministério são preservados diretamente do catálogo de origem.';
