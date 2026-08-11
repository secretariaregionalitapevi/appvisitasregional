-- Estrutura escalavel das equipes de visita.
-- LOCAL: numerada e vinculada a uma comum.
-- REGIONAL: identificada por letra e vinculada a um municipio.

create extension if not exists pgcrypto;

create table if not exists public.visitas_equipes (
    id uuid primary key default gen_random_uuid(),
    nome text not null,
    tipo text not null check (tipo in ('LOCAL', 'REGIONAL')),
    municipio text not null,
    comum text null,
    ativo boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint visitas_equipes_localizacao_check check (
        (tipo = 'LOCAL' and comum is not null and trim(comum) <> '')
        or (tipo = 'REGIONAL' and comum is null)
    )
);

create unique index if not exists visitas_equipes_local_unique
    on public.visitas_equipes (lower(municipio), lower(comum), lower(nome))
    where tipo = 'LOCAL';

create unique index if not exists visitas_equipes_regional_unique
    on public.visitas_equipes (lower(municipio), lower(nome))
    where tipo = 'REGIONAL';

alter table public.visitas_irmandade
    add column if not exists equipe_id uuid null references public.visitas_equipes(id) on delete set null;

alter table public.visitas_agenda
    add column if not exists equipe_id uuid null references public.visitas_equipes(id) on delete set null;

alter table public.visitas_agenda
    add column if not exists equipe_tipo text null check (equipe_tipo in ('LOCAL', 'REGIONAL'));

create index if not exists visitas_equipes_municipio_tipo_idx
    on public.visitas_equipes (municipio, tipo, ativo);

create index if not exists visitas_irmandade_equipe_id_idx
    on public.visitas_irmandade (equipe_id);

create index if not exists visitas_agenda_equipe_id_idx
    on public.visitas_agenda (equipe_id);

-- Converte automaticamente as equipes numericas que ja estavam mapeadas.
insert into public.visitas_equipes (nome, tipo, municipio, comum)
select distinct
    'Equipe ' || (regexp_replace(trim(i.equipe_visita), '[^0-9]', '', 'g')::integer)::text,
    'LOCAL', c.cidade, i.comum
from public.visitas_irmandade i
join public.visitas_comuns c on lower(trim(c.comum)) = lower(trim(i.comum))
where trim(coalesce(i.equipe_visita, '')) ~* '^equipe( de visitas?)? [0-9]+$'
on conflict do nothing;

update public.visitas_irmandade i
set equipe_id = e.id,
    equipe_visita = e.nome
from public.visitas_equipes e
where e.tipo = 'LOCAL'
  and lower(trim(e.comum)) = lower(trim(i.comum))
  and trim(coalesce(i.equipe_visita, '')) ~* '^equipe( de visitas?)? [0-9]+$'
  and e.nome = 'Equipe ' || (regexp_replace(trim(i.equipe_visita), '[^0-9]', '', 'g')::integer)::text;

update public.visitas_agenda a
set equipe_id = e.id,
    equipe_tipo = 'LOCAL',
    equipe_responsavel = e.nome
from public.visitas_irmandade i
join public.visitas_equipes e on e.id = i.equipe_id
where a.irmandade_id = i.id
  and trim(coalesce(a.equipe_responsavel, '')) ~* '^equipe( de visitas?)? [0-9]+$'
  and e.nome = 'Equipe ' || (regexp_replace(trim(a.equipe_responsavel), '[^0-9]', '', 'g')::integer)::text;

comment on table public.visitas_equipes is
    'Cadastro de equipes locais por comum e grupos regionais por municipio.';
