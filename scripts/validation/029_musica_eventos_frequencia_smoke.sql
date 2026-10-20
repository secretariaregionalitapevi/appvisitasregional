-- Executar APÓS a migração 029, em homologação PostgreSQL 15+.
-- psql -v ON_ERROR_STOP=1 -f scripts/validation/029_musica_eventos_frequencia_smoke.sql
-- Usa dados sintéticos e sempre desfaz a transação se não houver erro.
begin;
do $$
declare
    v_base uuid := gen_random_uuid();
    v_evento uuid := gen_random_uuid();
    v_rt uuid := gen_random_uuid();
    v_local_a uuid := gen_random_uuid();
    v_local_b uuid := gen_random_uuid();
    v_local_rt uuid := gen_random_uuid();
    v_ok boolean;
    v_linha record;
begin
    insert into public.musica_evento_comuns(codigo,nome,municipio) values
        ('BR-99999-90001','Comum sintética A','COTIA'),
        ('BR-99999-90002','Comum sintética B','CAUCAIA DO ALTO'),
        ('BR-99999-90003','Comum visitante','OUTRO MUNICÍPIO');
    insert into public.musica_evento_bases(id,referencia,origem,created_by_user_id,created_by_name)
        values(v_base,'2026-10-19','TESTE SINTÉTICO','teste','Operador de teste');
    insert into public.musica_evento_base_cobertura
        (base_id,comum_codigo,comum_nome,municipio,completa,quantidade_fonte) values
        (v_base,'BR-99999-90001','Comum sintética A','COTIA',true,4),
        (v_base,'BR-99999-90002','Comum sintética B','CAUCAIA DO ALTO',true,1),
        (v_base,'BR-99999-90003','Comum visitante','OUTRO MUNICÍPIO',true,1);
    insert into public.musica_evento_base_pessoas
        (base_id,sam_pessoa_id,comum_codigo,nome,categoria,familia,nivel,ativo) values
        (v_base,'a1','BR-99999-90001','Músico A1','MUSICO','CORDAS','ENSAIO',true),
        (v_base,'a2','BR-99999-90001','Músico A2','MUSICO','METAIS','OFICIALIZADO',true),
        (v_base,'a3','BR-99999-90001','Organista A3','ORGANISTA','TECLADO','RJM',true),
        (v_base,'a4','BR-99999-90001','Músico inativo','MUSICO','CORDAS','OFICIALIZADO',false),
        (v_base,'b1','BR-99999-90002','Músico B1','MUSICO','METAIS','CULTO OFICIAL',true),
        (v_base,'c1','BR-99999-90003','Músico visitante','MUSICO','CORDAS','OFICIALIZADO',true);
    update public.musica_evento_bases set homologada_em=now(),homologada_por_id='teste',
        homologada_por_nome='Operador de teste' where id=v_base;

    -- A captura não pode mais ser alterada.
    v_ok := false;
    begin
        update public.musica_evento_base_pessoas set ativo=true where base_id=v_base and sam_pessoa_id='a4';
    exception when raise_exception then v_ok := true;
    end;
    if not v_ok then raise exception 'FALHA: base homologada foi alterada'; end if;

    insert into public.musica_eventos(id,titulo,data_evento,tipo,base_id,
        created_by_user_id,created_by_name,updated_by_user_id,updated_by_name)
        values(v_evento,'Ensaio sintético','2026-10-19','ENSAIO_REGIONAL',v_base,
            'teste','Operador de teste','teste','Operador de teste');
    insert into public.musica_evento_locais(id,evento_id,nome,municipio) values
        (v_local_a,v_evento,'COTIA','COTIA'),(v_local_b,v_evento,'CAUCAIA','CAUCAIA DO ALTO');
    insert into public.musica_evento_convocacoes(evento_id,comum_codigo,local_referencia_id) values
        (v_evento,'BR-99999-90001',v_local_a),(v_evento,'BR-99999-90002',v_local_b);
    update public.musica_eventos set status='ABERTO' where id=v_evento;

    select * into v_linha from public.musica_evento_frequencia_totais where evento_id=v_evento;
    if v_linha.musicos_base <> 3 or v_linha.organistas_base <> 1
        or v_linha.percentual_musicos <> 0 then
        raise exception 'FALHA: base, inatividade, todos os níveis ou zero presentes';
    end if;

    -- A1, da comum A, comparece no OUTRO local. Deve contar normalmente na origem.
    insert into public.musica_evento_presencas(evento_id,local_id,pessoa_chave,sam_pessoa_id,
        nome,comum_codigo,categoria,familia,origem,
        created_by_user_id,created_by_name,updated_by_user_id,updated_by_name) values
        (v_evento,v_local_b,'SAM:a1','a1','Músico A1','BR-99999-90001','MUSICO','CORDAS','MANUAL','teste','Operador de teste','teste','Operador de teste'),
        (v_evento,v_local_a,'SAM:a3','a3','Organista A3','BR-99999-90001','ORGANISTA','TECLADO','MANUAL','teste','Operador de teste','teste','Operador de teste'),
        (v_evento,v_local_b,'SAM:b1','b1','Músico B1','BR-99999-90002','MUSICO','METAIS','MANUAL','teste','Operador de teste','teste','Operador de teste'),
        (v_evento,v_local_a,'SAM:c1','c1','Músico visitante','BR-99999-90003','MUSICO','CORDAS','MANUAL','teste','Operador de teste','teste','Operador de teste');
    insert into public.musica_evento_presencas(evento_id,local_id,pessoa_chave,nome,
        categoria,familia,origem,created_by_user_id,created_by_name,updated_by_user_id,updated_by_name)
        values(v_evento,v_local_a,'EXTERNO:'||gen_random_uuid(),'Visitante sem vínculo',
            'MUSICO','CORDAS','MANUAL','teste','Operador de teste','teste','Operador de teste');

    select * into v_linha from public.musica_evento_frequencia_totais where evento_id=v_evento;
    if v_linha.musicos_presentes <> 2 or v_linha.musicos_base <> 3
        or v_linha.percentual_musicos <> 66.67 or v_linha.percentual_organistas <> 100 then
        raise exception 'FALHA: razão das somas, vínculo SAM ou visitantes';
    end if;
    if (select sum(total_geral) from public.musica_evento_resumo_local where evento_id=v_evento) <> 5 then
        raise exception 'FALHA: total administrativo deve incluir visitantes';
    end if;

    v_ok := false;
    begin
        insert into public.musica_evento_presencas(evento_id,local_id,pessoa_chave,sam_pessoa_id,
            nome,comum_codigo,categoria,familia,origem,
            created_by_user_id,created_by_name,updated_by_user_id,updated_by_name)
        values(v_evento,v_local_a,'SAM:a1','a1','Músico A1','BR-99999-90001','MUSICO','CORDAS',
            'MANUAL','teste','Operador de teste','teste','Operador de teste');
    exception when unique_violation then v_ok := true;
    end;
    if not v_ok then raise exception 'FALHA: presença duplicada entre locais foi aceita'; end if;

    -- Edição legítima guarda autor original e registra novo editor.
    update public.musica_evento_presencas set observacoes='Conferido',updated_by_user_id='editor',
        updated_by_name='Editor de teste' where evento_id=v_evento and sam_pessoa_id='a1';
    if not exists (select 1 from public.musica_evento_auditoria
        where tabela='musica_evento_presencas' and operacao='UPDATE' and usuario_id='editor'
        and posterior->>'observacoes'='Conferido') then
        raise exception 'FALHA: edição sem auditoria';
    end if;
    v_ok := false;
    begin
        update public.musica_evento_presencas set created_by_name='Autor forjado'
            where evento_id=v_evento and sam_pessoa_id='a1';
    exception when raise_exception then v_ok := true;
    end;
    if not v_ok then raise exception 'FALHA: autoria original foi alterada'; end if;

    -- RT de Cordas usa A1, mas não o inativo A4, os metais ou a organista.
    insert into public.musica_eventos(id,titulo,data_evento,tipo,familia,base_id,
        created_by_user_id,created_by_name,updated_by_user_id,updated_by_name)
        values(v_rt,'RT sintética','2026-10-19','REUNIAO_TECNICA','CORDAS',v_base,
            'teste','Operador de teste','teste','Operador de teste');
    insert into public.musica_evento_locais(id,evento_id,nome,municipio)
        values(v_local_rt,v_rt,'COTIA','COTIA');
    insert into public.musica_evento_convocacoes(evento_id,comum_codigo,local_referencia_id) values
        (v_rt,'BR-99999-90001',v_local_rt),(v_rt,'BR-99999-90002',v_local_rt);
    update public.musica_eventos set status='ABERTO' where id=v_rt;
    select * into v_linha from public.musica_evento_frequencia_totais where evento_id=v_rt;
    if v_linha.musicos_base <> 1 or v_linha.organistas_base <> 0
        or v_linha.percentual_organistas is not null then
        raise exception 'FALHA: filtro RT ou divisão por zero';
    end if;
    update public.musica_eventos set status='ENCERRADO' where id=v_evento;
    v_ok := false;
    begin
        update public.musica_evento_presencas set observacoes='Alteração indevida'
            where evento_id=v_evento and sam_pessoa_id='a1';
    exception when raise_exception then v_ok := true;
    end;
    if not v_ok then raise exception 'FALHA: evento encerrado aceitou alteração de presença'; end if;
    raise notice 'OK: base histórica, frequência, RT, visitantes, duplicidade, autoria e fechamento.';
end $$;
rollback;
