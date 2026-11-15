begin;

alter table public.musica_evento_encarregados
    add column if not exists encarregado_nome text not null default '';

do $$
declare
    item record;
    value jsonb;
    person_name text;
begin
    for item in
        select id, observacoes
        from public.musica_evento_encarregados
        where encarregado_nome = '' and observacoes like '{%'
    loop
        begin
            value := item.observacoes::jsonb;
        exception when others then
            continue;
        end;
        person_name := nullif(btrim(value ->> 'nome'), '');
        if value ->> '_justificativa' = '1'
           and person_name is not null
           and person_name !~ '[,;/]' then
            update public.musica_evento_encarregados
            set encarregado_nome = person_name
            where id = item.id;
        end if;
    end loop;
end $$;

alter table public.musica_evento_encarregados
    drop constraint if exists musica_evento_encarregados_evento_id_comum_chave_key;
create unique index if not exists musica_evento_encarregados_evento_comum_pessoa_key
    on public.musica_evento_encarregados(evento_id, comum_chave, encarregado_nome);

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

notify pgrst,'reload schema';
commit;
