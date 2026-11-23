-- Evolução da 064: quatro administrações e sete agendas municipais independentes.
-- Executar uma vez, após a 064. Preserva responsáveis, pareceres, eventos e destinos já vinculados.
begin;
select pg_advisory_xact_lock(64112026);
create table public.agenda_calendarios (
 id text primary key,
 administracao_id text not null references public.agenda_administracoes(id),
 nome text not null,
 municipio text not null unique,
 calendar_id text not null default ''
);
create unique index agenda_calendario_municipal_unico on public.agenda_calendarios(calendar_id) where calendar_id<>'';
insert into public.agenda_calendarios(id,administracao_id,nome,municipio) values
 ('cotia','cotia','Cotia','Cotia'),
 ('caucaia','cotia','Caucaia do Alto','Caucaia do Alto'),
 ('vargem_grande','cotia','Vargem Grande Paulista','Vargem Grande Paulista'),
 ('itapevi','itapevi','Itapevi','Itapevi'),
 ('jandira','jandira','Jandira','Jandira'),
 ('santana','santana','Santana de Parnaíba','Santana de Parnaíba'),
 ('pirapora','santana','Pirapora do Bom Jesus','Pirapora do Bom Jesus');
-- Somente os dois destinos inequivocamente municipais podem ser reaproveitados.
-- IDs antes compartilhados ficam preservados em agenda_administracoes, sem assumir o município.
update public.agenda_calendarios c set calendar_id=a.calendar_id from public.agenda_administracoes a
 where c.id in ('itapevi','jandira') and a.id=c.administracao_id;
alter table public.agenda_eventos add column agenda_id text references public.agenda_calendarios(id);
update public.agenda_eventos e set agenda_id=c.id from public.agenda_calendarios c
 where c.administracao_id=e.administracao_id and c.municipio=e.municipio;
alter table public.agenda_eventos alter column agenda_id set not null;
create index agenda_evento_calendario on public.agenda_eventos(agenda_id,inicio);
-- Aprovações externas antigas são vinculadas ao Calendar ID original, não a um município presumido.
update public.agenda_eventos e set conflitos_externos=(
 select jsonb_agg(x || jsonb_build_object('calendar_id',a.calendar_id))
 from jsonb_array_elements(e.conflitos_externos) x
 left join public.agenda_administracoes a on a.id=x->>'administracao_id'
) where jsonb_array_length(e.conflitos_externos)>0;
alter table public.agenda_calendarios enable row level security;
revoke all on public.agenda_calendarios from anon,authenticated;
revoke insert,update,delete,truncate,references,trigger on public.agenda_calendarios from service_role;
grant select on public.agenda_calendarios to service_role;
create policy agenda_calendarios_service on public.agenda_calendarios for all to service_role using (true) with check (true);

create or replace function public.agenda_operar(p_acao text,p_dados jsonb,p_actor uuid,p_nome text,
 p_nivel text,p_municipio text,p_master boolean default false) returns jsonb
language plpgsql set search_path=public as $$
declare
 e public.agenda_eventos; a public.agenda_administracoes; r public.agenda_responsaveis;
 c public.agenda_calendarios;
 v_id uuid; v_conf uuid[]; v_adms text[]; v_dec text; v_nota text; v_reg boolean;
 v_adm text; v_status text; v_current jsonb;
begin
 perform pg_advisory_xact_lock(64112026);
 if p_actor is null then raise exception 'Identidade ausente' using errcode='42501'; end if;
 v_reg := exists(select 1 from public.agenda_responsaveis where user_id=p_actor and papel='REGIONAL');
 if p_acao='configurar' then
   if not p_master then raise exception 'Somente o administrador global configura os responsáveis' using errcode='42501'; end if;
   if p_dados->>'tipo'='agenda' then
     select * into c from public.agenda_calendarios where id=p_dados->>'agenda_id' for update;
     if not found then raise exception 'Selecione uma agenda municipal válida. Atualize a página.'; end if;
     if exists(select 1 from public.agenda_eventos where agenda_id=c.id
          and status not in ('CANCELADO','RECUSADO')) and c.calendar_id<>btrim(p_dados->>'calendar_id') and c.calendar_id<>'' then
       raise exception 'Não troque uma agenda municipal com reservas ativas. Concilie os eventos antes.';
     end if;
     update public.agenda_calendarios set calendar_id=btrim(p_dados->>'calendar_id') where id=c.id;
   elsif p_dados->>'tipo'='prazo' then
     update public.agenda_administracoes set prazo_horas=(p_dados->>'prazo_horas')::integer
       where id=p_dados->>'administracao_id';
     if not found then raise exception 'Administração inválida'; end if;
   elsif p_dados->>'tipo'='remover_responsavel' then
     delete from public.agenda_responsaveis where id=(p_dados->>'id')::uuid returning * into r;
     if not found then raise exception 'Responsável não encontrado'; end if;
   elsif p_dados->>'tipo'='responsavel' then
     if not exists(select 1 from public.profiles where user_id=(p_dados->>'user_id')::uuid and status='approved') then
       raise exception 'Selecione um usuário aprovado';
     end if;
     insert into public.agenda_responsaveis(user_id,nome,papel,administracao_id)
       select user_id,coalesce(full_name,'Responsável'),p_dados->>'papel',nullif(p_dados->>'administracao_id','')
       from public.profiles where user_id=(p_dados->>'user_id')::uuid;
   else raise exception 'Configuração inválida'; end if;
   insert into public.agenda_historico(acao,user_id,nome,dados) values('CONFIGURACAO',p_actor,p_nome,p_dados);
   return jsonb_build_object('ok',true);
 end if;
 if p_acao='criar' then
   v_id := (p_dados->>'id')::uuid;
   select * into e from public.agenda_eventos where id=v_id;
   if found then
     if e.criado_por<>p_actor then raise exception 'Identificador já utilizado' using errcode='42501'; end if;
     if e.administracao_id<>p_dados->>'administracao_id' or e.municipio<>p_dados->>'municipio'
       or e.titulo<>p_dados->>'titulo' or e.categoria<>p_dados->>'categoria' or e.local<>p_dados->>'local'
       or e.inicio<>(p_dados->>'inicio')::timestamptz or e.fim<>(p_dados->>'fim')::timestamptz then
       raise exception 'O protocolo já contém outros dados. Atualize a página.';
     end if;
     return to_jsonb(e);
   end if;
   select * into a from public.agenda_administracoes where id=p_dados->>'administracao_id';
   if not found or not (p_dados->>'municipio'=any(a.municipios)) then raise exception 'Município incompatível com a administração'; end if;
   if p_nivel not in ('regional','global') and not v_reg and not exists(
       select 1 from public.agenda_responsaveis where user_id=p_actor and administracao_id=a.id) then
     if p_nivel<>'municipal' or lower(p_municipio)<>lower(p_dados->>'municipio') then
       raise exception 'Município fora do seu escopo' using errcode='42501';
     end if;
   end if;
   select * into c from public.agenda_calendarios where administracao_id=a.id and municipio=p_dados->>'municipio';
   if not found then raise exception 'Agenda municipal não encontrada'; end if;
   if exists(select 1 from public.agenda_calendarios where calendar_id='') then
     raise exception 'Configure as sete agendas municipais Google antes de solicitar eventos';
   end if;
   insert into public.agenda_eventos(id,administracao_id,agenda_id,municipio,titulo,categoria,local,inicio,fim,
       criado_por,criado_por_nome,status,prazo_em)
     values(v_id,a.id,c.id,p_dados->>'municipio',p_dados->>'titulo',p_dados->>'categoria',p_dados->>'local',
       (p_dados->>'inicio')::timestamptz,(p_dados->>'fim')::timestamptz,p_actor,p_nome,'PRONTO',now()+make_interval(hours=>a.prazo_horas)) returning * into e;
   if e.inicio<=now() or e.fim>e.inicio+interval '7 days' then raise exception 'Informe um período futuro de até sete dias'; end if;
   v_conf:=public.agenda_conflitos(e);
   if exists(select 1 from public.agenda_eventos where id=any(v_conf) and administracao_id=e.administracao_id) then
     raise exception 'Esse horário está ocupado na mesma administração. Escolha outro período.' using errcode='23P01';
   end if;
   update public.agenda_eventos set conflitos=v_conf,status=case when cardinality(v_conf)>0 then 'PENDENTE_ADM' else 'PRONTO' end
     where id=e.id returning * into e;
   insert into public.agenda_historico(evento_id,acao,user_id,nome,dados)
     values(e.id,'SOLICITADO',p_actor,p_nome,jsonb_build_object('conflitos',v_conf));
   perform public.agenda_notificar(e.id,e.status);
   return to_jsonb(e);
 end if;
 select * into e from public.agenda_eventos where id=(p_dados->>'id')::uuid for update;
 if not found then raise exception 'Evento não encontrado' using errcode='P0002'; end if;
 if p_acao='cancelar' then
   if e.criado_por<>p_actor and not v_reg and not exists(select 1 from public.agenda_responsaveis
       where user_id=p_actor and administracao_id=e.administracao_id) then
     raise exception 'Você não pode cancelar este evento' using errcode='42501';
   end if;
   if e.status in ('INTEGRANDO','ERRO_INTEGRACAO') then raise exception 'Conclua a verificação da integração antes de cancelar'; end if;
   if e.status in ('CANCELADO','RECUSADO','CANCELANDO') then return to_jsonb(e); end if;
   v_nota:=btrim(p_dados->>'justificativa');
   if coalesce(length(v_nota),0)<3 then raise exception 'Informe o motivo do cancelamento'; end if;
   update public.agenda_eventos set status=case when google_event_id is null then 'CANCELADO' else 'CANCELANDO' end,
     atualizado_em=now(),proxima_tentativa=now(),lease_ate=null where id=e.id returning * into e;
 elsif p_acao='parecer' then
   if e.status not in ('PENDENTE_ADM','PENDENTE_REGIONAL') then raise exception 'Este evento não aguarda parecer'; end if;
   if e.versao<>(p_dados->>'versao')::integer then raise exception 'A solicitação mudou. Atualize a análise.'; end if;
   v_adm:=nullif(p_dados->>'administracao_id','');
   if e.status='PENDENTE_REGIONAL' then
     if not v_reg then raise exception 'Somente a equipe Regional designada decide esta etapa' using errcode='42501'; end if;
     v_adm:=null;
   elsif not exists(select 1 from public.agenda_responsaveis where user_id=p_actor and administracao_id=v_adm
            and papel in ('ENCARREGADO','SUPLENTE')) then
     raise exception 'Somente o encarregado designado pode emitir este parecer' using errcode='42501';
   end if;
   v_conf:=public.agenda_conflitos(e);
   -- Conflitos cancelados não invalidam autorização; novos conflitos exigem nova rodada.
   if not v_conf <@ e.conflitos then
     update public.agenda_eventos set conflitos=v_conf,versao=versao+1,status='PENDENTE_ADM',atualizado_em=now()
       where id=e.id returning * into e;
     perform public.agenda_notificar(e.id,'NOVA_ANALISE');
     return to_jsonb(e)||jsonb_build_object('reanalise',true);
   end if;
   select array_agg(distinct administracao_id) into v_adms from public.agenda_eventos where id=any(v_conf) or id=e.id;
   if e.status='PENDENTE_ADM' and not (v_adm=any(v_adms)) then raise exception 'Administração não envolvida' using errcode='42501'; end if;
   v_dec:=p_dados->>'decisao'; v_nota:=btrim(p_dados->>'justificativa');
   if coalesce(length(v_nota),0)<3 or length(v_nota)>2000 then raise exception 'Informe uma justificativa de 3 a 2000 caracteres'; end if;
   if e.status='PENDENTE_ADM' and v_dec not in ('APROVAR','IMPEDIMENTO') or
      e.status='PENDENTE_REGIONAL' and v_dec not in ('APROVAR','RECUSAR') then raise exception 'Decisão inválida'; end if;
   insert into public.agenda_pareceres(evento_id,versao,etapa,administracao_id,decisao,justificativa,user_id,nome)
     values(e.id,e.versao,case when e.status='PENDENTE_ADM' then 'ADM' else 'REGIONAL' end,v_adm,v_dec,v_nota,p_actor,p_nome);
   v_status:=e.status;
   if e.status='PENDENTE_REGIONAL' then v_status:=case when v_dec='APROVAR' then 'PRONTO' else 'RECUSADO' end;
   elsif v_dec='IMPEDIMENTO' then v_status:='PENDENTE_REGIONAL';
   elsif not exists(select 1 from unnest(v_adms) adm where not exists(
      select 1 from public.agenda_pareceres p where p.evento_id=e.id and p.versao=e.versao
        and p.administracao_id=adm and p.decisao='APROVAR' and p.etapa='ADM')) then v_status:='PRONTO'; end if;
   update public.agenda_eventos set status=v_status,atualizado_em=now(),proxima_tentativa=now()
     where id=e.id returning * into e;
 elsif p_acao='reenviar' then
   if not v_reg and not p_master then raise exception 'Somente a Regional pode reprocessar a integração' using errcode='42501'; end if;
   if e.status<>'ERRO_INTEGRACAO' then raise exception 'Este evento não possui integração pendente de verificação'; end if;
   update public.agenda_eventos set status='PRONTO',proxima_tentativa=now(),atualizado_em=now() where id=e.id returning * into e;
 else raise exception 'Operação inválida'; end if;
 insert into public.agenda_historico(evento_id,acao,user_id,nome,dados) values(e.id,upper(p_acao),p_actor,p_nome,p_dados);
 perform public.agenda_notificar(e.id,e.status);
 return to_jsonb(e);
end;
$$;

create or replace function public.agenda_trabalho(p_acao text,p_dados jsonb default '{}') returns jsonb
language plpgsql set search_path=public as $$
declare e public.agenda_eventos; n public.agenda_notificacoes; v_token uuid; v_status text; v_conf uuid[]; v_external jsonb;
begin
 perform pg_advisory_xact_lock(64112026);
 if p_acao in ('buscar','resultado') and coalesce(p_dados->>'protocol_version','')<>'2' then
   raise exception 'Atualize o workflow n8n para sete agendas municipais (protocolo 2)';
 end if;
 -- Um lembrete na metade do prazo, registrado na mesma transação da caixa de saída.
 for e in update public.agenda_eventos set lembrete_em=now()
   where status='PENDENTE_ADM' and lembrete_em is null and prazo_em>now()
     and now()>=criado_em+(prazo_em-criado_em)/2 returning * loop
   perform public.agenda_notificar(e.id,'LEMBRETE_PARECER');
 end loop;
 -- Falta de resposta encaminha à Regional, nunca aprova automaticamente.
 for e in update public.agenda_eventos set status='PENDENTE_REGIONAL',atualizado_em=now()
   where status='PENDENTE_ADM' and prazo_em<=now() returning * loop
   insert into public.agenda_historico(evento_id,acao,nome) values(e.id,'PRAZO_ENCERRADO','Sistema');
   perform public.agenda_notificar(e.id,'PRAZO_ENCERRADO');
 end loop;
 if p_acao='buscar' then
   select * into e from public.agenda_eventos where
     (status in ('PRONTO','CANCELANDO') or status='INTEGRANDO' and lease_ate<now())
     and (lease_ate is null or lease_ate<now()) and proxima_tentativa<=now()
     and (status='CANCELANDO' or not exists(select 1 from public.agenda_calendarios where calendar_id=''))
     order by ordem limit 1 for update;
   if not found then return jsonb_build_object('job',null); end if;
   if e.status='PRONTO' then
     v_conf:=public.agenda_conflitos(e);
     if not v_conf <@ e.conflitos then
       update public.agenda_eventos set conflitos=v_conf,versao=versao+1,status='PENDENTE_ADM',atualizado_em=now()
         where id=e.id;
       perform public.agenda_notificar(e.id,'NOVA_ANALISE');
       return jsonb_build_object('job',null);
     end if;
   end if;
   v_token:=gen_random_uuid();
   update public.agenda_eventos set lease_token=v_token,lease_ate=now()+interval '10 minutes',
     status=case when status='CANCELANDO' then status else 'INTEGRANDO' end,tentativas=tentativas+1,
     google_calendar_id=coalesce(google_calendar_id,(select calendar_id from public.agenda_calendarios where id=e.agenda_id)),
     atualizado_em=now() where id=e.id returning * into e;
   return jsonb_build_object('job',to_jsonb(e)||jsonb_build_object(
     'google_id',replace(e.id::text,'-',''),'calendar_schema','municipal-v1',
     'allowed_google_events',coalesce((select jsonb_agg(jsonb_build_object('id',v.id,'administracao_id',v.administracao_id,
       'agenda_id',v.agenda_id,'google_calendar_id',coalesce(v.google_calendar_id,cal.calendar_id),
       'titulo',v.titulo,'local',v.local,'inicio',v.inicio,'fim',v.fim)) from public.agenda_eventos v
       join public.agenda_calendarios cal on cal.id=v.agenda_id where v.id=any(e.conflitos)),'[]'::jsonb),
     'calendars',(select jsonb_agg(jsonb_build_object('id',id,'administracao_id',administracao_id,'municipio',municipio,'calendar_id',calendar_id) order by id) from public.agenda_calendarios)));
 elsif p_acao='resultado' then
   select * into e from public.agenda_eventos where id=(p_dados->>'id')::uuid for update;
   if not found then raise exception 'Trabalho não encontrado'; end if;
   if e.lease_token is distinct from (p_dados->>'lease_token')::uuid then raise exception 'Execução substituída. Descarte este retorno.'; end if;
   if e.status not in ('INTEGRANDO','CANCELANDO') then
     return to_jsonb(e); -- Callback repetido da mesma execução, sem repetir histórico/notificações.
   end if;
   v_status:=p_dados->>'resultado';
   if v_status='confirmado' and e.status='INTEGRANDO' then
     if coalesce(p_dados->>'google_event_id','')<>replace(e.id::text,'-','') then raise exception 'Identificador Google incompatível'; end if;
     update public.agenda_eventos set status='CONFIRMADO',google_event_id=p_dados->>'google_event_id',mensagem_integracao='' where id=e.id;
   elsif v_status='cancelado' and e.status='CANCELANDO' then
     update public.agenda_eventos set status='CANCELADO',mensagem_integracao='' where id=e.id;
   elsif v_status='conflito_externo' and e.status='INTEGRANDO' then
     v_external:=p_dados->'conflitos';
     if jsonb_typeof(v_external)<>'array' or jsonb_array_length(v_external)=0 then raise exception 'Conflitos externos ausentes'; end if;
     select jsonb_agg(x) into v_external from (
       select distinct on (coalesce(x->>'calendar_id',x->>'administracao_id'),x->>'google_event_id') x
       from jsonb_array_elements(e.conflitos_externos||v_external) with ordinality as items(x,pos)
       order by coalesce(x->>'calendar_id',x->>'administracao_id'),x->>'google_event_id',pos desc
     ) merged;
     if exists(select 1 from jsonb_array_elements(v_external) x where x->>'administracao_id'=e.administracao_id) then
       update public.agenda_eventos set status='RECUSADO',conflitos_externos=v_external where id=e.id;
     else
       update public.agenda_eventos set status='PENDENTE_REGIONAL',conflitos_externos=v_external,
          versao=versao+1 where id=e.id;
     end if;
   elsif v_status='erro' then
     -- Conserva a reserva; não sabemos se o Google concluiu a operação.
     update public.agenda_eventos set status=case when e.status='CANCELANDO' then 'CANCELANDO' else 'ERRO_INTEGRACAO' end,
       mensagem_integracao=left(coalesce(p_dados->>'mensagem','Falha na integração'),500),
       proxima_tentativa=now()+interval '10 minutes' where id=e.id;
   else raise exception 'Resultado incompatível com a operação'; end if;
   update public.agenda_eventos set atualizado_em=now(),lease_ate=null where id=e.id returning * into e;
   insert into public.agenda_historico(evento_id,acao,nome,dados) values(e.id,'INTEGRACAO','n8n',p_dados-'lease_token');
   perform public.agenda_notificar(e.id,e.status);
   return to_jsonb(e);
 elsif p_acao='notificacao' then
   select * into n from public.agenda_notificacoes where entregue_em is null and (lease_ate is null or lease_ate<now())
     and exists(select 1 from public.profiles where user_id=destinatario and status='approved')
     order by criado_em limit 1 for update;
   if not found then return jsonb_build_object('notification',null); end if;
   update public.agenda_notificacoes set lease_token=gen_random_uuid(),lease_ate=now()+interval '10 minutes'
     where id=n.id returning * into n;
   return jsonb_build_object('notification',to_jsonb(n)||jsonb_build_object('evento',
     (select jsonb_build_object('id',id,'titulo',titulo,'inicio',inicio,'fim',fim,'status',status,'administracao_id',administracao_id,'agenda_id',agenda_id,'municipio',municipio)
       from public.agenda_eventos where id=n.evento_id),
     'destinatario',(select jsonb_build_object('user_id',user_id,'nome',full_name,'whatsapp',whatsapp,'celular',celular,'telefone',telefone)
       from public.profiles where user_id=n.destinatario and status='approved')));
 elsif p_acao='notificado' then
   update public.agenda_notificacoes set entregue_em=now() where id=(p_dados->>'id')::uuid
      and lease_token=(p_dados->>'lease_token')::uuid and entregue_em is null;
   return jsonb_build_object('ok',found);
 end if;
 raise exception 'Operação de integração inválida';
end;
$$;

-- CREATE OR REPLACE conserva os privilégios; explicita as restrições da fronteira de serviço.
revoke all on function public.agenda_operar(text,jsonb,uuid,text,text,text,boolean) from public,anon,authenticated;
revoke all on function public.agenda_trabalho(text,jsonb) from public,anon,authenticated;
alter function public.agenda_operar(text,jsonb,uuid,text,text,text,boolean) security definer;
alter function public.agenda_trabalho(text,jsonb) security definer;
grant execute on function public.agenda_operar(text,jsonb,uuid,text,text,text,boolean) to service_role;
grant execute on function public.agenda_trabalho(text,jsonb) to service_role;
notify pgrst, 'reload schema';
commit;
