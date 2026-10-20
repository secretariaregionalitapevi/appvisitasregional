-- Complemento da 029: importar contagens AppCont antes da conciliação SAM.
-- Aplicar após 029. A base ausente não é tratada como população zero.
begin;
alter table public.musica_eventos alter column base_id drop not null;

create table if not exists public.musica_evento_importacoes (
    id uuid primary key default gen_random_uuid(),
    arquivo_sha256 text not null unique check (arquivo_sha256 ~ '^[a-f0-9]{64}$'),
    evento_id uuid not null references public.musica_eventos(id),
    quantidade integer not null check (quantidade > 0),
    resumo jsonb not null,
    conteudo jsonb not null,
    created_at timestamptz not null default now(),
    created_by_user_id text not null,
    created_by_name text not null
);
alter table public.musica_evento_importacoes enable row level security;
revoke all on public.musica_evento_importacoes from anon, authenticated, service_role;
grant select on public.musica_evento_importacoes to service_role;

create or replace function public.musica_evento_validar_evento()
returns trigger language plpgsql set search_path = public, pg_temp as $$
begin
    if tg_op = 'UPDATE' then
        if (old.base_id is not null and new.base_id is distinct from old.base_id)
            or new.tipo <> old.tipo or new.familia <> old.familia
            or new.data_evento <> old.data_evento or new.created_by_user_id <> old.created_by_user_id
            or new.created_by_name <> old.created_by_name or new.created_at <> old.created_at then
            raise exception 'Base existente, data, público e autoria são imutáveis.';
        end if;
    end if;
    if new.base_id is not null and not exists (
        select 1 from public.musica_evento_bases where id = new.base_id and homologada_em is not null
    ) then raise exception 'Selecione uma base SAM homologada.'; end if;
    if new.status <> 'RASCUNHO' then
        if not exists (select 1 from public.musica_evento_locais where evento_id = new.id) then
            raise exception 'Configure ao menos um local antes de abrir o evento.';
        end if;
        if new.base_id is not null then
            if not exists (select 1 from public.musica_evento_convocacoes where evento_id = new.id)
                or exists (select 1 from public.musica_evento_convocacoes c
                    left join public.musica_evento_base_cobertura b on b.base_id = new.base_id and b.comum_codigo = c.comum_codigo
                    where c.evento_id = new.id and b.completa is distinct from true) then
                raise exception 'Configure as comuns convocadas e a cobertura SAM.';
            end if;
        end if;
    end if;
    new.updated_at := now();
    return new;
end $$;

-- Uma chamada RPC grava evento, locais, presenças e recibo em UMA transação.
-- A função não é exposta ao browser; o backend valida sessão e papel regional.
create or replace function public.musica_evento_importar_appcont(
    p_hash text, p_titulo text, p_data date, p_tipo text, p_familia text,
    p_usuario_id text, p_usuario_nome text, p_resumo jsonb, p_registros jsonb
) returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare
    v_evento uuid; v_local uuid; v_registro jsonb; v_nome_local text; v_importacao public.musica_evento_importacoes;
begin
    if p_hash !~ '^[a-f0-9]{64}$' or nullif(btrim(p_usuario_id),'') is null
        or nullif(btrim(p_usuario_nome),'') is null or nullif(btrim(p_titulo),'') is null
        or p_data is null or jsonb_typeof(p_registros) <> 'array'
        or jsonb_array_length(p_registros) not between 1 and 20000 then
        raise exception 'Importação inválida.';
    end if;
    perform pg_advisory_xact_lock(hashtext('musica_appcont:' || p_hash));
    select * into v_importacao from public.musica_evento_importacoes where arquivo_sha256 = p_hash;
    if found then return jsonb_build_object('evento_id',v_importacao.evento_id,
        'quantidade',v_importacao.quantidade,'ja_importado',true); end if;
    insert into public.musica_eventos(titulo,data_evento,tipo,familia,base_id,
        created_by_user_id,created_by_name,updated_by_user_id,updated_by_name,observacoes)
    values(p_titulo,p_data,p_tipo,p_familia,null,p_usuario_id,p_usuario_nome,p_usuario_id,p_usuario_nome,
        'Contagem AppCont importada. Conciliação com cadastro SAM pendente.') returning id into v_evento;
    for v_nome_local in select distinct value->>'local' from jsonb_array_elements(p_registros) loop
        insert into public.musica_evento_locais(evento_id,nome,municipio)
        values(v_evento,v_nome_local,case when upper(v_nome_local) = 'PIRAPORA' then 'PIRAPORA DO BOM JESUS' else v_nome_local end);
    end loop;
    update public.musica_eventos set status='ABERTO' where id=v_evento;
    for v_registro in select value from jsonb_array_elements(p_registros) loop
        select id into strict v_local from public.musica_evento_locais
            where evento_id=v_evento and nome=v_registro->>'local';
        insert into public.musica_evento_presencas(evento_id,local_id,pessoa_chave,nome,
            comum_informada,municipio_informado,categoria,instrumento,familia,nivel,cargo,
            origem,origem_registro_id,origem_arquivo_sha256,registrado_por_legado,
            created_by_user_id,created_by_name,updated_by_user_id,updated_by_name,observacoes)
        values(v_evento,v_local,'EXTERNO:'||(v_registro->>'origem_registro_id'),v_registro->>'nome',
            v_registro->>'comum_informada',v_registro->>'municipio_informado',v_registro->>'categoria',
            v_registro->>'instrumento',v_registro->>'familia',v_registro->>'nivel',v_registro->>'cargo',
            'XLSX',v_registro->>'origem_registro_id',p_hash,v_registro->>'registrado_por_legado',
            p_usuario_id,p_usuario_nome,p_usuario_id,p_usuario_nome,
            concat_ws(E'\n',nullif(v_registro->>'observacoes',''),
                'Data/hora original no arquivo: '||(v_registro->>'data_hora_original')));
    end loop;
    insert into public.musica_evento_importacoes(arquivo_sha256,evento_id,quantidade,resumo,conteudo,
        created_by_user_id,created_by_name)
    values(p_hash,v_evento,jsonb_array_length(p_registros),p_resumo,p_registros,p_usuario_id,p_usuario_nome);
    return jsonb_build_object('evento_id',v_evento,'quantidade',jsonb_array_length(p_registros),'ja_importado',false);
end $$;
revoke all on function public.musica_evento_importar_appcont(text,text,date,text,text,text,text,jsonb,jsonb)
    from public,anon,authenticated;
grant execute on function public.musica_evento_importar_appcont(text,text,date,text,text,text,text,jsonb,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
