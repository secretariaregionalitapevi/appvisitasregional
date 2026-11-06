-- Relação manual e protocolo de recebimento. Emissão e aprovação continuam independentes.
begin;
create table if not exists public.cartas_relacao_candidatos (
 candidate_key text primary key check(length(candidate_key)=64),
 event_id text not null, comum text not null, municipio text not null,
 data jsonb not null, version integer not null default 1,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 updated_by uuid not null, updated_name text not null
);
create index if not exists cartas_relacao_event on public.cartas_relacao_candidatos(event_id);
create table if not exists public.cartas_entrega_prazos (
 event_id text primary key, event_snapshot jsonb not null, pre_date date not null,
 deadline date not null, version integer not null default 1,
 updated_at timestamptz not null default now(), updated_by uuid not null, updated_name text not null,
 check(deadline<pre_date)
);
create table if not exists public.cartas_entrega_auditoria (
 id bigint generated always as identity primary key, candidate_key text, event_id text not null,
 action text not null, before_data jsonb, after_data jsonb not null,
 actor_id uuid not null, actor_name text not null, created_at timestamptz not null default now()
);
alter table public.cartas_relacao_candidatos enable row level security;
alter table public.cartas_entrega_prazos enable row level security;
alter table public.cartas_entrega_auditoria enable row level security;
revoke all on public.cartas_relacao_candidatos,public.cartas_entrega_prazos,public.cartas_entrega_auditoria from public,anon,authenticated;
grant all on public.cartas_relacao_candidatos,public.cartas_entrega_prazos,public.cartas_entrega_auditoria to service_role;
grant usage,select on sequence public.cartas_entrega_auditoria_id_seq to service_role;

create or replace function public.cartas_registrar_entrega(p_key text,p_data jsonb,p_version integer,p_actor uuid,p_name text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare old public.cartas_relacao_candidatos; result public.cartas_relacao_candidatos;
begin
 if p_actor is null or nullif(trim(p_name),'') is null then raise exception 'Responsável inválido'; end if;
 perform pg_advisory_xact_lock(hashtextextended(p_key,0));
 select * into old from public.cartas_relacao_candidatos where candidate_key=p_key for update;
 if (found and old.version<>p_version) or (not found and p_version<>0) then
  raise exception 'Recebimento alterado por outro usuário. Atualize a relação.' using errcode='40001';
 end if;
 if found then
  p_data=old.data || jsonb_build_object('delivery',p_data->'delivery');
 end if;
 insert into public.cartas_relacao_candidatos(candidate_key,event_id,comum,municipio,data,version,updated_by,updated_name)
 values(p_key,p_data->>'event_id',p_data->>'comum',p_data->>'municipio',p_data,1,p_actor,p_name)
 on conflict(candidate_key) do update set data=excluded.data,version=cartas_relacao_candidatos.version+1,
 updated_at=now(),updated_by=p_actor,updated_name=p_name returning * into result;
 insert into public.cartas_entrega_auditoria(candidate_key,event_id,action,before_data,after_data,actor_id,actor_name)
 values(p_key,result.event_id,'ENTREGA',to_jsonb(old),to_jsonb(result),p_actor,p_name);
 return to_jsonb(result);
end $$;

create or replace function public.cartas_salvar_prazo(p_event text,p_snapshot jsonb,p_pre date,p_deadline date,p_version integer,p_actor uuid,p_name text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare old public.cartas_entrega_prazos; result public.cartas_entrega_prazos;
begin
 if p_actor is null or nullif(trim(p_name),'') is null or p_deadline>=p_pre then raise exception 'Prazo ou responsável inválido'; end if;
 perform pg_advisory_xact_lock(hashtextextended(p_event,0));
 select * into old from public.cartas_entrega_prazos where event_id=p_event for update;
 if (found and old.version<>p_version) or (not found and p_version<>0) then
  raise exception 'Prazo alterado por outro usuário. Atualize a relação.' using errcode='40001';
 end if;
 insert into public.cartas_entrega_prazos(event_id,event_snapshot,pre_date,deadline,updated_by,updated_name)
 values(p_event,p_snapshot,p_pre,p_deadline,p_actor,p_name)
 on conflict(event_id) do update set event_snapshot=p_snapshot,pre_date=p_pre,deadline=p_deadline,
 version=cartas_entrega_prazos.version+1,updated_at=now(),updated_by=p_actor,updated_name=p_name returning * into result;
 insert into public.cartas_entrega_auditoria(event_id,action,before_data,after_data,actor_id,actor_name)
 values(p_event,'PRAZO',to_jsonb(old),to_jsonb(result),p_actor,p_name);
 return to_jsonb(result);
end $$;

create or replace function public.cartas_importar_relacao(p_rows jsonb,p_actor uuid,p_name text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare item jsonb; inserted integer=0; skipped integer=0; result public.cartas_relacao_candidatos;
begin
 if p_actor is null or nullif(trim(p_name),'') is null or jsonb_array_length(p_rows)>1000 then raise exception 'Importação inválida'; end if;
 for item in select value from jsonb_array_elements(p_rows) loop
  insert into public.cartas_relacao_candidatos(candidate_key,event_id,comum,municipio,data,updated_by,updated_name)
  values(item->>'key',item->>'event_id',item->>'comum',item->>'municipio',item,p_actor,p_name)
  on conflict(candidate_key) do nothing returning * into result;
  if found then
   inserted=inserted+1;
   insert into public.cartas_entrega_auditoria(candidate_key,event_id,action,after_data,actor_id,actor_name)
   values(result.candidate_key,result.event_id,'IMPORTAR',to_jsonb(result),p_actor,p_name);
  else skipped=skipped+1; end if;
 end loop;
 return jsonb_build_object('inserted',inserted,'skipped',skipped);
end $$;
revoke all on function public.cartas_registrar_entrega(text,jsonb,integer,uuid,text) from public,anon,authenticated;
revoke all on function public.cartas_salvar_prazo(text,jsonb,date,date,integer,uuid,text) from public,anon,authenticated;
revoke all on function public.cartas_importar_relacao(jsonb,uuid,text) from public,anon,authenticated;
grant execute on function public.cartas_registrar_entrega(text,jsonb,integer,uuid,text) to service_role;
grant execute on function public.cartas_salvar_prazo(text,jsonb,date,date,integer,uuid,text) to service_role;
grant execute on function public.cartas_importar_relacao(jsonb,uuid,text) to service_role;
notify pgrst,'reload schema';
commit;
