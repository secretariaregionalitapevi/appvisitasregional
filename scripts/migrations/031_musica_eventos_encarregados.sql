-- Conferência dos encarregados por evento/comum, independente da base SAM.
begin;
create table if not exists public.musica_evento_encarregados (
    id uuid primary key default gen_random_uuid(),
    evento_id uuid not null references public.musica_eventos(id),
    comum_chave text not null check(btrim(comum_chave)<>''),
    comum_nome text not null check(btrim(comum_nome)<>''),
    municipio text not null check(btrim(municipio)<>''),
    situacao text not null check(situacao in ('PRESENTE','JUSTIFICOU','NAO_JUSTIFICOU','NAO_INFORMADO','SEM_ENCARREGADO','ENFERMO')),
    local_id uuid,
    observacoes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by_user_id text not null check(btrim(created_by_user_id)<>''),
    created_by_name text not null check(btrim(created_by_name)<>''),
    updated_by_user_id text not null check(btrim(updated_by_user_id)<>''),
    updated_by_name text not null check(btrim(updated_by_name)<>''),
    unique(evento_id,comum_chave),
    foreign key(evento_id,local_id) references public.musica_evento_locais(evento_id,id),
    check((situacao='PRESENTE' and local_id is not null) or (situacao<>'PRESENTE' and local_id is null)),
    check(situacao<>'JUSTIFICOU' or nullif(btrim(observacoes),'') is not null)
);
alter table public.musica_evento_encarregados enable row level security;
revoke all on public.musica_evento_encarregados from anon,authenticated;
grant select,insert,update on public.musica_evento_encarregados to service_role;
revoke delete on public.musica_evento_encarregados from service_role;
create or replace function public.musica_evento_validar_encarregado()
returns trigger language plpgsql set search_path=public,pg_temp as $$
declare v_status text;
begin
    select status into strict v_status from public.musica_eventos where id=new.evento_id for share;
    if v_status='ENCERRADO' then raise exception 'Evento encerrado não permite alterar a conferência.'; end if;
    if tg_op='UPDATE' and (new.evento_id<>old.evento_id or new.comum_chave<>old.comum_chave
        or new.created_by_user_id<>old.created_by_user_id or new.created_by_name<>old.created_by_name
        or new.created_at<>old.created_at) then raise exception 'Identidade e autoria original são imutáveis.'; end if;
    new.updated_at=now();return new;
end $$;
drop trigger if exists musica_encarregado_validar on public.musica_evento_encarregados;
create trigger musica_encarregado_validar before insert or update on public.musica_evento_encarregados
for each row execute function public.musica_evento_validar_encarregado();
drop trigger if exists musica_encarregado_auditar on public.musica_evento_encarregados;
create trigger musica_encarregado_auditar after insert or update on public.musica_evento_encarregados
for each row execute function public.musica_evento_auditar();
revoke all on function public.musica_evento_validar_encarregado() from public,anon,authenticated;
notify pgrst,'reload schema';
commit;
