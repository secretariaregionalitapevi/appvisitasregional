-- Estrutura permanente do GEM no SAM: turma, matrícula, aula, chamada e evolução do aluno.
create table if not exists public.sam_gem_groups (
    id uuid primary key default gen_random_uuid(),
    source_id bigint not null unique,
    congregacao text,
    curso text,
    turma text,
    matriculados integer,
    data_inicio date,
    data_termino date,
    dia_horario text,
    ativo boolean not null default true,
    source_hash text not null,
    source_payload jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    synced_at timestamptz not null default now()
);

alter table public.sam_gem_classes
    add column if not exists turma_id uuid references public.sam_gem_groups(id) on delete set null;

create table if not exists public.sam_gem_enrollments (
    id uuid primary key default gen_random_uuid(),
    turma_id uuid not null references public.sam_gem_groups(id) on delete cascade,
    source_member_id bigint not null,
    aluno_id uuid references public.musica_acompanhamento_aluno(id) on delete set null,
    nome_aluno text not null,
    congregacao text,
    instrumento text,
    ativo boolean not null default true,
    source_hash text not null,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    synced_at timestamptz not null default now(),
    unique (turma_id, source_member_id)
);

-- Reorganiza imediatamente o acervo já importado, sem aguardar as próximas aulas.
insert into public.sam_gem_groups (
    source_id, congregacao, curso, turma, ativo, source_hash, source_payload,
    first_seen_at, last_seen_at, synced_at
)
select distinct on (c.turma_source_id)
    c.turma_source_id, c.congregacao, c.curso, c.turma, true,
    md5(concat_ws('|', c.turma_source_id::text, c.congregacao, c.curso, c.turma)),
    jsonb_build_object('source_id', c.turma_source_id, 'congregacao', c.congregacao,
                       'curso', c.curso, 'turma', c.turma, 'backfilled', true),
    min(c.first_seen_at) over (partition by c.turma_source_id),
    max(c.last_seen_at) over (partition by c.turma_source_id),
    max(c.synced_at) over (partition by c.turma_source_id)
from public.sam_gem_classes c
where c.turma_source_id is not null
order by c.turma_source_id, c.data_aula desc nulls last
on conflict (source_id) do update set
    congregacao = excluded.congregacao,
    curso = excluded.curso,
    turma = excluded.turma,
    source_hash = excluded.source_hash,
    source_payload = public.sam_gem_groups.source_payload || excluded.source_payload,
    last_seen_at = greatest(public.sam_gem_groups.last_seen_at, excluded.last_seen_at),
    synced_at = greatest(public.sam_gem_groups.synced_at, excluded.synced_at);

update public.sam_gem_classes c
set turma_id = g.id
from public.sam_gem_groups g
where c.turma_id is null and g.source_id = c.turma_source_id;

insert into public.sam_gem_enrollments (
    turma_id, source_member_id, aluno_id, nome_aluno, congregacao, instrumento,
    ativo, source_hash, first_seen_at, last_seen_at, synced_at
)
select distinct on (g.id, f.source_member_id)
    g.id, f.source_member_id, f.aluno_id, f.nome_aluno, c.congregacao, a.instrumento,
    true, md5(concat_ws('|', g.id::text, f.source_member_id::text, f.aluno_id::text,
                        f.nome_aluno, c.congregacao, a.instrumento)),
    f.first_seen_at, f.last_seen_at, f.synced_at
from public.sam_gem_attendance f
join public.sam_gem_classes c on c.id = f.aula_id
join public.sam_gem_groups g on g.id = c.turma_id
left join public.musica_acompanhamento_aluno a on a.id = f.aluno_id
order by g.id, f.source_member_id, c.data_aula desc nulls last
on conflict (turma_id, source_member_id) do update set
    aluno_id = coalesce(excluded.aluno_id, public.sam_gem_enrollments.aluno_id),
    nome_aluno = excluded.nome_aluno,
    congregacao = excluded.congregacao,
    instrumento = coalesce(excluded.instrumento, public.sam_gem_enrollments.instrumento),
    source_hash = excluded.source_hash,
    last_seen_at = greatest(public.sam_gem_enrollments.last_seen_at, excluded.last_seen_at),
    synced_at = greatest(public.sam_gem_enrollments.synced_at, excluded.synced_at);
create index if not exists sam_gem_groups_location_idx
    on public.sam_gem_groups(congregacao, curso, turma);
create index if not exists sam_gem_classes_group_idx
    on public.sam_gem_classes(turma_id, data_aula desc);
create index if not exists sam_gem_enrollments_student_idx
    on public.sam_gem_enrollments(aluno_id, turma_id);
create index if not exists sam_gem_enrollments_member_idx
    on public.sam_gem_enrollments(source_member_id, turma_id);

alter table public.sam_gem_groups enable row level security;
alter table public.sam_gem_enrollments enable row level security;
revoke all on public.sam_gem_groups, public.sam_gem_enrollments from anon, authenticated;
grant all on public.sam_gem_groups, public.sam_gem_enrollments to service_role;

create or replace view public.sam_gem_student_evolution as
select m.aluno_id, m.data_aula::date as event_date, 'MSA'::text as event_type,
       coalesce(m.fase, 'Lição MSA')::text as title,
       jsonb_build_object('fase', m.fase, 'paginas', m.paginas, 'licoes', m.licoes,
                          'clave', m.clave, 'observacoes', m.observacoes,
                          'autorizado_por', m.autorizado_por) as details,
       'musica_acompanhamento_msa'::text as source_table, m.id::text as source_id
from public.musica_acompanhamento_msa m
union all
select x.aluno_id, x.data_inicio::date, 'METODO', coalesce(x.metodo, 'Método'),
       jsonb_build_object('metodo', x.metodo, 'pagina', x.pagina, 'licao', x.licao,
                          'observacoes', x.observacoes, 'autorizado_por', x.autorizado_por),
       'musica_acompanhamento_metodo', x.id::text
from public.musica_acompanhamento_metodo x
union all
select h.aluno_id, h.data::date, 'HINARIO', concat('Hino ', coalesce(h.hino, '')),
       jsonb_build_object('hino', h.hino, 'voz', h.voz, 'observacoes', h.observacoes,
                          'autorizado_por', h.autorizado_por),
       'musica_acompanhamento_hinario', h.id::text
from public.musica_acompanhamento_hinario h
union all
select p.aluno_id, p.data_prova::date, 'PROVA', coalesce(p.modulo, 'Prova'),
       jsonb_build_object('modulo', p.modulo, 'nota', p.nota, 'observacoes', p.observacoes,
                          'autorizado_por', p.autorizado_por),
       'musica_acompanhamento_provas', p.id::text
from public.musica_acompanhamento_provas p
union all
select e.aluno_id, e.data::date, 'ESCALA', coalesce(e.escala, 'Escala'),
       jsonb_build_object('escala', e.escala, 'observacoes', e.observacoes,
                          'autorizado_por', e.autorizado_por),
       'musica_acompanhamento_escala', e.id::text
from public.musica_acompanhamento_escala e
union all
select a.aluno_id, a.data_atividade::date, 'ATIVIDADE', coalesce(a.titulo, a.tipo_atividade, 'Atividade'),
       jsonb_build_object('tipo', a.tipo_atividade, 'descricao', a.descricao,
                          'documento_url', a.documento_url, 'nome_documento', a.nome_documento),
       'musica_acompanhamento_atividades', a.id::text
from public.musica_acompanhamento_atividades a
union all
select f.aluno_id, c.data_aula::date, 'FREQUENCIA',
       concat(case when f.presente then 'Presença' else 'Ausência' end, ' · ', coalesce(c.turma, c.curso, 'Aula GEM')),
       jsonb_build_object('presente', f.presente, 'turma', c.turma, 'curso', c.curso,
                          'congregacao', c.congregacao, 'inicio', c.inicio, 'termino', c.termino,
                          'instrutor', c.instrutor_aula, 'aula_source_id', c.source_id,
                          'turma_source_id', c.turma_source_id),
       'sam_gem_attendance', f.id::text
from public.sam_gem_attendance f
join public.sam_gem_classes c on c.id = f.aula_id
where f.aluno_id is not null
union all
select l.aluno_id, l.effective_at::date, 'NIVEL',
       concat(coalesce(l.previous_level, 'Sem nível'), ' → ', l.new_level),
       jsonb_build_object('nivel_anterior', l.previous_level, 'nivel_novo', l.new_level,
                          'criterio_data', l.date_basis, 'evidencia', l.evidence),
       'sam_level_history', l.id::text
from public.sam_level_history l;

grant select on public.sam_gem_student_evolution to service_role;

comment on table public.sam_gem_groups is
'Turmas permanentes do GEM espelhadas do SAM; uma turma possui várias aulas.';
comment on table public.sam_gem_enrollments is
'Matrículas dos alunos nas turmas do GEM, conciliadas pelo id_membro do SAM.';
comment on view public.sam_gem_student_evolution is
'Linha do tempo consolidada do aluno: estudos, avaliações, nível, aulas e frequência, preservando a origem.';
