-- A 037 conserva a detecção; esta migração conserva a vigência comprovada.
begin;
create table if not exists public.sam_cadastro_transicoes (
    id uuid primary key default gen_random_uuid(),
    aluno_id uuid not null,
    campo text not null check (campo in ('cargo_ministerio','comum_congregacao','municipio','nivel','data_inicio_gem','status','instrumento')),
    anterior jsonb,
    posterior jsonb,
    effective_at timestamptz not null,
    detected_at timestamptz not null default now(),
    date_basis text not null check (date_basis in ('sam','manual','detected_at_sync')),
    source_ref text not null,
    evidence jsonb not null default '{}'::jsonb,
    unique (aluno_id, campo, source_ref)
);
create index if not exists sam_transicoes_aluno_data_idx on public.sam_cadastro_transicoes(aluno_id,effective_at);
alter table public.sam_cadastro_transicoes enable row level security;
revoke all on public.sam_cadastro_transicoes from anon,authenticated,service_role;
grant select,insert on public.sam_cadastro_transicoes to service_role;

create or replace function public.sam_auditoria_transicoes()
returns trigger language plpgsql security definer set search_path = public,pg_temp as $$
declare campo text;
begin
    foreach campo in array array['cargo_ministerio','comum_congregacao','municipio','nivel','data_inicio_gem','status','instrumento'] loop
        if new.anterior->campo is distinct from new.posterior->campo then
            insert into public.sam_cadastro_transicoes(aluno_id,campo,anterior,posterior,effective_at,date_basis,source_ref,evidence)
            values(new.aluno_id,campo,new.anterior->campo,new.posterior->campo,new.detected_at,
                'detected_at_sync','cadastro:'||new.id::text,jsonb_build_object('audit_id',new.id))
            on conflict do nothing;
        end if;
    end loop;
    return new;
end;
$$;
revoke all on function public.sam_auditoria_transicoes() from public;
drop trigger if exists sam_auditoria_transicoes on public.sam_cadastro_historico;
create trigger sam_auditoria_transicoes after insert on public.sam_cadastro_historico
    for each row execute function public.sam_auditoria_transicoes();
-- Also preserve changes detected before installation, without inventing SAM dates.
insert into public.sam_cadastro_transicoes(aluno_id,campo,anterior,posterior,effective_at,date_basis,source_ref,evidence)
select h.aluno_id,f.campo,h.anterior->f.campo,h.posterior->f.campo,h.detected_at,
    'detected_at_sync','cadastro:'||h.id::text,jsonb_build_object('audit_id',h.id)
from public.sam_cadastro_historico h cross join unnest(array['cargo_ministerio','comum_congregacao','municipio','nivel','data_inicio_gem','status','instrumento']) as f(campo)
where h.anterior->f.campo is distinct from h.posterior->f.campo on conflict do nothing;
insert into public.sam_cadastro_transicoes(aluno_id,campo,anterior,posterior,effective_at,detected_at,date_basis,source_ref,evidence)
select aluno_id,'nivel',to_jsonb(previous_level),to_jsonb(new_level),coalesce(source_date,effective_at),detected_at,
    case when source_date is not null then 'sam' else date_basis end,
    'level:'||id::text,evidence from public.sam_level_history on conflict do nothing;

-- Keep existing level integrations alive while recording them in the same ledger.
create or replace function public.sam_nivel_transicao()
returns trigger language plpgsql security definer set search_path = public,pg_temp as $$
begin
    insert into public.sam_cadastro_transicoes(aluno_id,campo,anterior,posterior,effective_at,detected_at,date_basis,source_ref,evidence)
    values(new.aluno_id,'nivel',to_jsonb(new.previous_level),to_jsonb(new.new_level),coalesce(new.source_date,new.effective_at),
           new.detected_at,case when new.source_date is not null then 'sam' else new.date_basis end,
           'level:'||new.id::text,new.evidence) on conflict do nothing;
    return new;
end;
$$;
revoke all on function public.sam_nivel_transicao() from public;
drop trigger if exists sam_nivel_transicao on public.sam_level_history;
create trigger sam_nivel_transicao after insert on public.sam_level_history
    for each row execute function public.sam_nivel_transicao();

-- An explicit date + old/new values is required. A generic "saved student" log
-- is insufficient evidence of a change of role, common or academic level.
create or replace function public.sam_registrar_transicao(
    p_source_key text,p_campo text,p_anterior jsonb,p_posterior jsonb,
    p_effective_at timestamptz,p_source_ref text,p_evidence jsonb)
returns void language plpgsql security definer set search_path = public,pg_temp as $$
declare target uuid; matches integer;
begin
    if p_effective_at is null or p_effective_at > now() or coalesce(p_source_ref,'') = ''
       or coalesce(p_evidence,'{}'::jsonb) = '{}'::jsonb or p_anterior is not distinct from p_posterior then
        raise exception 'Transição sem data, evidência ou mudança válida';
    end if;
    select count(*),min(id::text)::uuid into matches,target
    from public.musica_acompanhamento_aluno where registro_msa = p_source_key;
    if matches <> 1 then raise exception 'Identidade SAM ausente ou ambígua: %',p_source_key; end if;
    if exists(select 1 from public.sam_cadastro_transicoes
        where aluno_id=target and campo=p_campo and source_ref=p_source_ref
          and (anterior is distinct from p_anterior or posterior is distinct from p_posterior or effective_at<>p_effective_at)) then
        raise exception 'Evidência já registrada com valores diferentes';
    end if;
    insert into public.sam_cadastro_transicoes(aluno_id,campo,anterior,posterior,effective_at,date_basis,source_ref,evidence)
    values(target,p_campo,p_anterior,p_posterior,p_effective_at,'sam',p_source_ref,p_evidence)
    on conflict do nothing;
end;
$$;
revoke all on function public.sam_registrar_transicao(text,text,jsonb,jsonb,timestamptz,text,jsonb) from public,anon,authenticated;
grant execute on function public.sam_registrar_transicao(text,text,jsonb,jsonb,timestamptz,text,jsonb) to service_role;
create or replace function public.auditar_sam_cadastro()
returns trigger language plpgsql security definer set search_path = public, pg_temp as $$
begin
    if (old.nome_aluno, old.cargo_ministerio, old.comum_congregacao, old.municipio,
        old.status, old.nivel, old.instrumento, old.registro_msa) is distinct from
       (new.nome_aluno, new.cargo_ministerio, new.comum_congregacao, new.municipio,
        new.status, new.nivel, new.instrumento, new.registro_msa)
       or to_jsonb(old)->'data_inicio_gem' is distinct from to_jsonb(new)->'data_inicio_gem' then
        insert into public.sam_cadastro_historico
            (aluno_id, registro_msa, usuario_id, anterior, posterior)
        values (new.id, new.registro_msa, auth.uid()::text, to_jsonb(old), to_jsonb(new));
    end if;
    return new;
end;
$$;

commit;
