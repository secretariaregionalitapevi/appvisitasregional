-- Espelho somente de leitura do Google. Não cria reservas nem aprovações retroativas.
begin;
create table public.agenda_google_leituras (
 id uuid primary key default gen_random_uuid(),
 agenda_id text not null references public.agenda_calendarios(id),
 calendar_id text not null,
 inicio timestamptz not null,
 fim timestamptz not null check(fim>inicio),
 status text not null default 'PENDENTE' check(status in ('PENDENTE','EXECUTANDO','OK','ERRO')),
 lease_token uuid,
 lease_ate timestamptz,
 iniciado_em timestamptz,
 concluido_em timestamptz,
 solicitado_em timestamptz not null default now(),
 mensagem text not null default '',
 unique(agenda_id,inicio,fim)
);
create table public.agenda_google_eventos (
 id uuid primary key,
 agenda_id text not null references public.agenda_calendarios(id),
 calendar_id text not null,
 google_event_id text not null,
 administracao_id text not null references public.agenda_administracoes(id),
 municipio text not null,
 titulo text not null,
 local text not null default '',
 inicio timestamptz not null,
 fim timestamptz not null check(fim>inicio),
 dia_inteiro boolean not null default false,
 disponivel boolean not null default false,
 obtido_em timestamptz not null,
 unique(calendar_id,google_event_id)
);
create index agenda_google_intervalo on public.agenda_google_eventos(inicio,fim);
create view public.agenda_google_visiveis as
 select g.* from public.agenda_google_eventos g
 join public.agenda_calendarios c on c.id=g.agenda_id and c.calendar_id=g.calendar_id
 where not exists(select 1 from public.agenda_eventos e where e.google_calendar_id=g.calendar_id
   and coalesce(e.google_event_id,replace(e.id::text,'-',''))=g.google_event_id);

create function public.agenda_google_operar(p_acao text,p_dados jsonb default '{}') returns jsonb
language plpgsql security definer set search_path=public as $$
declare l public.agenda_google_leituras; c public.agenda_calendarios;
 v_inicio timestamptz; v_fim timestamptz; v_ids text[]; v jsonb;
begin
 perform pg_advisory_xact_lock(64112026);
 if p_acao='solicitar' then
   v_inicio:=(p_dados->>'inicio')::timestamptz;v_fim:=(p_dados->>'fim')::timestamptz;
   if v_inicio is null or v_fim is null or v_fim<=v_inicio or v_fim>v_inicio+interval '93 days' then
     raise exception 'Período de leitura inválido';
   end if;
   for c in select * from public.agenda_calendarios where calendar_id<>'' loop
     insert into public.agenda_google_leituras(agenda_id,calendar_id,inicio,fim)
       values(c.id,c.calendar_id,v_inicio,v_fim)
       on conflict(agenda_id,inicio,fim) do update set
       calendar_id=excluded.calendar_id,status='PENDENTE',lease_token=null,lease_ate=null,
       concluido_em=case when agenda_google_leituras.calendar_id<>excluded.calendar_id then null else agenda_google_leituras.concluido_em end,
       mensagem='',solicitado_em=now()
       where agenda_google_leituras.calendar_id<>excluded.calendar_id or
        (agenda_google_leituras.status in ('OK','ERRO') and agenda_google_leituras.solicitado_em<now()-interval '1 minute'
          and (coalesce((p_dados->>'force')::boolean,false) or agenda_google_leituras.solicitado_em<now()-interval '5 minutes'));
   end loop;
   return jsonb_build_object('ok',true);
 elsif p_acao='buscar' then
   select r.* into l from public.agenda_google_leituras r
    join public.agenda_calendarios cal on cal.id=r.agenda_id and cal.calendar_id=r.calendar_id
    where r.status='PENDENTE' or r.status='EXECUTANDO' and r.lease_ate<now()
    order by r.solicitado_em,r.agenda_id limit 1 for update of r;
   if not found then return jsonb_build_object('job',null); end if;
   update public.agenda_google_leituras set status='EXECUTANDO',lease_token=gen_random_uuid(),
     lease_ate=now()+interval '10 minutes',iniciado_em=now() where id=l.id returning * into l;
   return jsonb_build_object('job',to_jsonb(l));
 elsif p_acao='resultado' then
   select * into l from public.agenda_google_leituras where id=(p_dados->>'id')::uuid for update;
   if not found or l.lease_token is distinct from (p_dados->>'lease_token')::uuid then
     raise exception 'Leitura substituída. Descarte o retorno antigo.';
   end if;
   if l.status<>'EXECUTANDO' then return jsonb_build_object('ok',true); end if;
   select * into c from public.agenda_calendarios where id=l.agenda_id;
   if c.calendar_id<>l.calendar_id then raise exception 'A agenda mudou. Solicite outra leitura.'; end if;
   if p_dados->>'resultado'='erro' then
     update public.agenda_google_leituras set status='ERRO',lease_ate=null,
       mensagem=left(coalesce(p_dados->>'mensagem','Falha ao consultar o Google'),500) where id=l.id;
     return jsonb_build_object('ok',false);
   end if;
   if coalesce(p_dados->>'resultado','')<>'ok' or coalesce(jsonb_typeof(p_dados->'eventos'),'')<>'array'
       or jsonb_array_length(p_dados->'eventos')>3000 then raise exception 'Leitura incompleta ou inválida'; end if;
   select coalesce(array_agg(x->>'google_event_id'),'{}'::text[]) into v_ids from jsonb_array_elements(p_dados->'eventos') x;
   if cardinality(v_ids)<>(select count(distinct x) from unnest(v_ids) x) then raise exception 'Eventos duplicados na leitura'; end if;
   for v in select value from jsonb_array_elements(p_dados->'eventos') loop
     if (v->>'inicio')::timestamptz>=l.fim or (v->>'fim')::timestamptz<=l.inicio then
       raise exception 'Evento fora do período consultado';
     end if;
     insert into public.agenda_google_eventos(id,agenda_id,calendar_id,google_event_id,administracao_id,municipio,
       titulo,local,inicio,fim,dia_inteiro,disponivel,obtido_em)
       values((v->>'id')::uuid,c.id,c.calendar_id,v->>'google_event_id',c.administracao_id,c.municipio,
         v->>'titulo',coalesce(v->>'local',''),(v->>'inicio')::timestamptz,(v->>'fim')::timestamptz,
         (v->>'dia_inteiro')::boolean,(v->>'disponivel')::boolean,l.iniciado_em)
       on conflict(calendar_id,google_event_id) do update set titulo=excluded.titulo,local=excluded.local,
         inicio=excluded.inicio,fim=excluded.fim,dia_inteiro=excluded.dia_inteiro,disponivel=excluded.disponivel,
         obtido_em=excluded.obtido_em where excluded.obtido_em>=agenda_google_eventos.obtido_em;
   end loop;
   -- Somente uma leitura completa pode remover registros ausentes; erro conserva o espelho anterior.
   delete from public.agenda_google_eventos where calendar_id=l.calendar_id and inicio<l.fim and fim>l.inicio
     and obtido_em<=l.iniciado_em and not(google_event_id=any(v_ids));
   update public.agenda_google_leituras set status='OK',concluido_em=now(),mensagem='',lease_ate=null where id=l.id;
   return jsonb_build_object('ok',true,'quantidade',cardinality(v_ids));
 end if;
 raise exception 'Operação de leitura inválida';
end;
$$;
alter table public.agenda_google_eventos enable row level security;
alter table public.agenda_google_leituras enable row level security;
revoke all on public.agenda_google_eventos,public.agenda_google_leituras,public.agenda_google_visiveis from anon,authenticated;
revoke insert,update,delete,truncate,references,trigger on public.agenda_google_eventos,public.agenda_google_leituras from service_role;
grant select on public.agenda_google_eventos,public.agenda_google_leituras,public.agenda_google_visiveis to service_role;
create policy agenda_google_eventos_service on public.agenda_google_eventos for select to service_role using(true);
create policy agenda_google_leituras_service on public.agenda_google_leituras for select to service_role using(true);
revoke all on function public.agenda_google_operar(text,jsonb) from public,anon,authenticated;
grant execute on function public.agenda_google_operar(text,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
