-- Controle auditável e visão operacional da sincronização SAM.
create table if not exists public.sam_sync_control (
    id smallint primary key default 1 check (id = 1),
    desired_state text not null default 'paused' check (desired_state in ('running', 'paused')),
    requested_at timestamptz,
    requested_by text,
    worker_id text,
    heartbeat_at timestamptz,
    current_student text,
    processed_students integer not null default 0,
    total_students integer not null default 0,
    last_message text,
    updated_at timestamptz not null default now()
);

insert into public.sam_sync_control (id) values (1) on conflict (id) do nothing;

create index if not exists musica_msa_aluno_data_idx on public.musica_acompanhamento_msa(aluno_id, data_aula desc);
create index if not exists musica_metodo_aluno_data_idx on public.musica_acompanhamento_metodo(aluno_id, data_inicio desc);
create index if not exists musica_hinario_aluno_data_idx on public.musica_acompanhamento_hinario(aluno_id, data desc);
create index if not exists musica_provas_aluno_data_idx on public.musica_acompanhamento_provas(aluno_id, data_prova desc);
create index if not exists musica_escala_aluno_data_idx on public.musica_acompanhamento_escala(aluno_id, data desc);
create index if not exists musica_atividades_aluno_data_idx on public.musica_acompanhamento_atividades(aluno_id, data_atividade desc);

create or replace view public.sam_mirror_student_status as
select
    s.id as sync_state_id,
    s.aluno_id,
    s.source_name,
    a.municipio,
    a.comum_congregacao,
    a.instrumento,
    a.nivel,
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
    a.cargo_ministerio,
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
    select
      m.data_aula as last_msa_date,
      m.fase as last_msa_phase,
      m.observacoes as last_msa_observations
    from public.musica_acompanhamento_msa m
    where m.aluno_id = s.aluno_id
    order by m.data_aula desc nulls last
    limit 1
) latest_msa on true;

alter table public.sam_sync_control enable row level security;
revoke all on table public.sam_sync_control from anon, authenticated;
grant all on table public.sam_sync_control to service_role;
grant select on table public.sam_mirror_student_status to service_role;

comment on view public.sam_mirror_student_status is
'Relatório informativo baseado na última atividade pedagógica: ativo <=90, alerta <=180, inativo <=365 e excluir >365 dias. A classificação EXCLUIR não remove nem altera alunos.';
