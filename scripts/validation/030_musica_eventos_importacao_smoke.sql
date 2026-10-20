-- Banco de homologação após 029 e 030. Todas as alterações são desfeitas.
-- psql -v ON_ERROR_STOP=1 -f scripts/validation/030_musica_eventos_importacao_smoke.sql
begin;
do $$
declare
    v_resultado jsonb; v_repetido jsonb; v_evento uuid;
    v_registros jsonb; v_antes bigint; v_falhou boolean := false;
begin
    v_registros := jsonb_build_array(
        jsonb_build_object('origem_registro_id',gen_random_uuid()::text,'nome','Músico sintético',
            'local','ITAPEVI','comum_informada','Comum de teste','municipio_informado','ITAPEVI',
            'categoria','MUSICO','familia','CORDAS','instrumento','VIOLINO','cargo','INSTRUTOR',
            'data_hora_original','2026-09-20T08:00:00'),
        jsonb_build_object('origem_registro_id',gen_random_uuid()::text,'nome','Organista sintética',
            'local','PIRAPORA','comum_informada','Comum visitante','municipio_informado','OUTRO MUNICÍPIO',
            'categoria','ORGANISTA','familia','TECLADO','instrumento','ÓRGÃO','cargo','ORGANISTA',
            'data_hora_original','2026-09-19T20:00:00'));
    v_resultado := public.musica_evento_importar_appcont(repeat('b',64),'Importação sintética',
        '2026-09-20','ENSAIO_REGIONAL','GERAL','teste','Operador sintético','{}',v_registros);
    v_evento := (v_resultado->>'evento_id')::uuid;
    if v_resultado->>'quantidade' <> '2' or (v_resultado->>'ja_importado')::boolean then
        raise exception 'Contagem ou indicador de nova importação incorreto';
    end if;
    if (select count(*) from public.musica_evento_locais where evento_id=v_evento) <> 2
        or (select sum(total_geral) from public.musica_evento_resumo_local where evento_id=v_evento) <> 2 then
        raise exception 'Locais ou resumo administrativo incorretos';
    end if;
    if exists(select 1 from public.musica_evento_frequencia where evento_id=v_evento)
        or exists(select 1 from public.musica_eventos where id=v_evento and base_id is not null) then
        raise exception 'A importação não pode presumir uma população SAM';
    end if;
    v_repetido := public.musica_evento_importar_appcont(repeat('b',64),'Título diferente',
        '2026-09-20','ENSAIO_REGIONAL','GERAL','teste','Operador sintético','{}',v_registros);
    if v_repetido->>'evento_id' <> v_resultado->>'evento_id'
        or not (v_repetido->>'ja_importado')::boolean
        or (select count(*) from public.musica_evento_presencas where evento_id=v_evento) <> 2 then
        raise exception 'Reimportação duplicou o lote';
    end if;
    if not exists(select 1 from public.musica_evento_auditoria
        where tabela='musica_evento_presencas' and usuario_id='teste'
        and posterior->>'evento_id'=v_evento::text) then
        raise exception 'Autoria do importador não foi auditada';
    end if;
    -- Um erro na segunda presença deve desfazer também evento/local/primeira presença.
    select count(*) into v_antes from public.musica_eventos;
    begin
        perform public.musica_evento_importar_appcont(repeat('c',64),'Importação inválida',
            '2026-09-20','ENSAIO_REGIONAL','GERAL','teste','Operador sintético','{}',
            jsonb_set(v_registros,'{1,categoria}','"INVALIDA"'));
    exception when check_violation then v_falhou := true;
    end;
    if not v_falhou or (select count(*) from public.musica_eventos) <> v_antes then
        raise exception 'Lote inválido deixou dados parciais';
    end if;
    raise notice 'OK: contagem sem SAM, locais, reimportação, autoria e atomicidade.';
end $$;
rollback;
