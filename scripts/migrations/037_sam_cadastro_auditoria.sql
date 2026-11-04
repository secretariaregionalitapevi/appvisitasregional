-- Execute before the next SAM catalog synchronization. Audit and update are atomic.
begin;
create table if not exists public.sam_cadastro_historico (
    id uuid primary key default gen_random_uuid(),
    aluno_id uuid not null,
    registro_msa text,
    detected_at timestamptz not null default now(),
    date_basis text not null default 'detected_at_update',
    usuario_id text,
    anterior jsonb not null,
    posterior jsonb not null
);
create index if not exists sam_cadastro_historico_aluno_idx
    on public.sam_cadastro_historico(aluno_id, detected_at desc);
alter table public.sam_cadastro_historico enable row level security;
revoke all on public.sam_cadastro_historico from anon, authenticated, service_role;
grant select, insert on public.sam_cadastro_historico to service_role;

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
revoke all on function public.auditar_sam_cadastro() from public;
drop trigger if exists sam_cadastro_auditoria on public.musica_acompanhamento_aluno;
create trigger sam_cadastro_auditoria after update on public.musica_acompanhamento_aluno
    for each row execute function public.auditar_sam_cadastro();
comment on table public.sam_cadastro_historico is
    'Antes/depois do cadastro musical, inclusive cargo e comum. Data de detecção não presume a data histórica da mudança no SAM.';
commit;
