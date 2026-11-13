-- Preserve timestamps for every GEM cadastro edit and expose name/registry
-- changes in the same timeline as level and congregation transitions.
begin;

alter table public.musica_acompanhamento_aluno
    add column if not exists updated_at timestamptz not null default now();

create or replace function public.musica_acompanhamento_atualizar_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

drop trigger if exists musica_acompanhamento_updated_at on public.musica_acompanhamento_aluno;
create trigger musica_acompanhamento_updated_at
    before update on public.musica_acompanhamento_aluno
    for each row execute function public.musica_acompanhamento_atualizar_updated_at();

alter table public.sam_cadastro_transicoes
    drop constraint if exists sam_cadastro_transicoes_campo_check;
alter table public.sam_cadastro_transicoes
    add constraint sam_cadastro_transicoes_campo_check
    check (campo in (
        'cargo_ministerio', 'comum_congregacao', 'municipio', 'nivel',
        'data_inicio_gem', 'status', 'instrumento', 'nome_aluno', 'registro_msa'
    ));

create or replace function public.sam_auditoria_transicoes()
returns trigger language plpgsql security definer set search_path = public,pg_temp as $$
declare campo text;
begin
    foreach campo in array array[
        'cargo_ministerio', 'comum_congregacao', 'municipio', 'nivel',
        'data_inicio_gem', 'status', 'instrumento', 'nome_aluno', 'registro_msa'
    ] loop
        if new.anterior->campo is distinct from new.posterior->campo then
            insert into public.sam_cadastro_transicoes
                (aluno_id,campo,anterior,posterior,effective_at,date_basis,source_ref,evidence)
            values (
                new.aluno_id,campo,new.anterior->campo,new.posterior->campo,new.detected_at,
                'detected_at_sync','cadastro:'||new.id::text,jsonb_build_object('audit_id',new.id)
            )
            on conflict do nothing;
        end if;
    end loop;
    return new;
end;
$$;

drop trigger if exists sam_auditoria_transicoes on public.sam_cadastro_historico;
create trigger sam_auditoria_transicoes
    after insert on public.sam_cadastro_historico
    for each row execute function public.sam_auditoria_transicoes();

insert into public.sam_cadastro_transicoes
    (aluno_id,campo,anterior,posterior,effective_at,date_basis,source_ref,evidence)
select h.aluno_id,f.campo,h.anterior->f.campo,h.posterior->f.campo,h.detected_at,
    'detected_at_sync','cadastro:'||h.id::text,jsonb_build_object('audit_id',h.id)
from public.sam_cadastro_historico h
cross join unnest(array['nome_aluno','registro_msa']) as f(campo)
where h.anterior->f.campo is distinct from h.posterior->f.campo
on conflict do nothing;

commit;
