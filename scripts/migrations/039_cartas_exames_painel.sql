-- Estrutura compartilhada e painel de cartas de exames. Migração autocontida.
begin;
-- Executar no SQL Editor do projeto Supabase usado para as cartas.

create table if not exists public.cartas_emissoes (
 id uuid primary key default gen_random_uuid(),
 duplicate_key text not null unique check(length(duplicate_key)=64),
 nome text not null, comum text not null, municipio text not null,
 tipo text not null check(tipo in ('musico','organista')),
 modalidade text not null, event_id text not null,
 event_snapshot jsonb not null, ministry_snapshot jsonb not null,
 payload jsonb not null,
 status text not null default 'processing' check(status in ('processing','ready','failed')),
 pdf_path text, pdf_sha256 text,
 created_by uuid references auth.users(id),
 owner_session uuid not null,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
alter table public.cartas_emissoes alter column created_by drop not null;
alter table public.cartas_emissoes add column if not exists owner_session uuid;
update public.cartas_emissoes set owner_session=created_by where owner_session is null;
alter table public.cartas_emissoes alter column owner_session set not null;
create index if not exists cartas_owner_date on public.cartas_emissoes(owner_session,created_at desc);
alter table public.cartas_emissoes enable row level security;
revoke all on public.cartas_emissoes from anon,authenticated;
grant all on public.cartas_emissoes to service_role;
-- Todo acesso passa pelo servidor, com sessão validada e restrição de proprietário.
create table if not exists public.cartas_auditoria (
 id bigint generated always as identity primary key,
 carta_id uuid not null, created_by uuid, owner_session uuid,
 action text not null, before_data jsonb, after_data jsonb,
 created_at timestamptz not null default now()
);
alter table public.cartas_auditoria alter column created_by drop not null;
alter table public.cartas_auditoria add column if not exists owner_session uuid;
alter table public.cartas_auditoria enable row level security;
revoke all on public.cartas_auditoria from anon,authenticated;
create or replace function public.cartas_audit_change() returns trigger
language plpgsql security definer set search_path=public as $$
begin
 if TG_OP='UPDATE' then NEW.updated_at=now(); end if;
 insert into public.cartas_auditoria(carta_id,created_by,owner_session,action,before_data,after_data)
 values(NEW.id,NEW.created_by,NEW.owner_session,TG_OP,case when TG_OP='UPDATE' then to_jsonb(OLD) else null end,to_jsonb(NEW));
 return NEW;
end $$;
revoke all on function public.cartas_audit_change() from public;
drop trigger if exists cartas_audit on public.cartas_emissoes;
create trigger cartas_audit before insert or update on public.cartas_emissoes for each row execute function public.cartas_audit_change();
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('cartas-musicais','cartas-musicais',false,5242880,array['application/pdf'])
on conflict(id) do nothing;


create table if not exists public.cartas_ministerio_comuns (
 common_code text primary key, comum text not null, municipio text not null,
 anciao text not null default '', cooperador text not null default '',
 regional text not null default '', encarregado text not null default '', secretario text not null default '',
 source_file text, source_row integer, source_sha256 text,
 updated_at timestamptz not null default now()
);
alter table public.cartas_ministerio_comuns enable row level security;
revoke all on public.cartas_ministerio_comuns from anon,authenticated;
grant all on public.cartas_ministerio_comuns to service_role;
create table if not exists public.cartas_ministerio_auditoria (
 id bigint generated always as identity primary key, common_code text not null,
 before_data jsonb, after_data jsonb not null, created_at timestamptz not null default now()
);
alter table public.cartas_ministerio_auditoria enable row level security;
revoke all on public.cartas_ministerio_auditoria from anon,authenticated;
create or replace function public.cartas_audit_ministry() returns trigger
language plpgsql security definer set search_path=public as $$
begin
 NEW.updated_at=now();
 insert into public.cartas_ministerio_auditoria(common_code,before_data,after_data)
 values(NEW.common_code,case when TG_OP='UPDATE' then to_jsonb(OLD) else null end,to_jsonb(NEW));
 return NEW;
end $$;
revoke all on function public.cartas_audit_ministry() from public;
drop trigger if exists cartas_ministerio_audit on public.cartas_ministerio_comuns;
create trigger cartas_ministerio_audit before insert or update on public.cartas_ministerio_comuns
for each row execute function public.cartas_audit_ministry();
alter table public.cartas_emissoes add column if not exists review_result text not null default 'PENDENTE';
alter table public.cartas_emissoes add column if not exists review_version integer not null default 1;
alter table public.cartas_emissoes add column if not exists reviewed_by uuid;
alter table public.cartas_emissoes add column if not exists reviewed_name text;
alter table public.cartas_emissoes add column if not exists reviewed_at timestamptz;
alter table public.cartas_emissoes add column if not exists review_notes text;
alter table public.cartas_emissoes add column if not exists exam_id uuid references public.musica_exames_individuais(id);
alter table public.cartas_emissoes drop constraint if exists cartas_review_result_check;
alter table public.cartas_emissoes add constraint cartas_review_result_check check(review_result in ('PENDENTE','APROVADO','RETORNOU AO CICLO','AUSENTE'));
create index if not exists cartas_exam_date on public.cartas_emissoes(event_id,review_result);

alter table public.musica_exames_individuais add column if not exists lancado_por_id uuid;

-- A confirmação e a contabilização são uma transação: sem contagens parciais ou duplicadas.
create or replace function public.cartas_confirmar_resultado(
 p_carta uuid,p_resultado text,p_actor uuid,p_nome text,p_version integer,p_notes text,
 p_exame jsonb,p_totais jsonb
) returns jsonb language plpgsql security definer set search_path=public as $$
declare c public.cartas_emissoes; e uuid;
begin
 select * into c from public.cartas_emissoes where id=p_carta for update;
 if not found then raise exception 'Carta não encontrada'; end if;
 if c.status<>'ready' then raise exception 'A carta precisa ter PDF emitido antes da confirmação'; end if;
 if c.review_version<>p_version then raise exception 'A carta foi atualizada por outro usuário. Atualize o painel.' using errcode='40001'; end if;
 if p_resultado not in ('PENDENTE','APROVADO','RETORNOU AO CICLO','AUSENTE') or p_actor is null or length(trim(p_nome))=0 then raise exception 'Confirmação inválida'; end if;
 if p_exame->>'aluno_id' is distinct from c.payload->>'pessoa_id' then raise exception 'O candidato não corresponde à carta'; end if;
 insert into public.musica_exames_individuais(id,aluno_id,nome_aluno,municipio,comum,instrumento,categoria,
 data_exame,tipo_exame,resultado,encarregado_local,observacoes,lancado_por,lancado_por_id,origem,chave_idempotencia)
 values(coalesce(c.exam_id,c.id),(p_exame->>'aluno_id')::uuid,c.nome,c.municipio,c.comum,
 p_exame->>'instrumento',p_exame->>'categoria',(c.event_snapshot->>'data')::date,p_exame->>'tipo_exame',
 case when p_resultado='PENDENTE' then 'AGENDADO' else p_resultado end,
 p_exame->>'encarregado_local',p_exame->>'observacoes',p_nome,p_actor,'PAINEL',p_exame->>'chave_idempotencia')
 on conflict(chave_idempotencia) do update set resultado=excluded.resultado,lancado_por=excluded.lancado_por,
 lancado_por_id=excluded.lancado_por_id,updated_at=now()
 returning id into e;
 insert into public.musica_exames_lancamentos(id,data_exame,municipio,lancado_por,total_exames,
 musicos_culto_oficial,musicos_oficializacao,musicos_troca_instrumento,organistas_rjm,
 organistas_culto_oficial,organistas_oficializacao,organistas_testes_especiais)
 values(e,(c.event_snapshot->>'data')::date,c.municipio,p_nome,coalesce((p_totais->>'total')::integer,0),
 coalesce((p_totais->>'musicos_culto_oficial')::integer,0),coalesce((p_totais->>'musicos_oficializacao')::integer,0),
 coalesce((p_totais->>'musicos_troca_instrumento')::integer,0),coalesce((p_totais->>'organistas_rjm')::integer,0),
 coalesce((p_totais->>'organistas_culto_oficial')::integer,0),coalesce((p_totais->>'organistas_oficializacao')::integer,0),
 coalesce((p_totais->>'organistas_testes_especiais')::integer,0))
 on conflict(id) do update set total_exames=excluded.total_exames,musicos_culto_oficial=excluded.musicos_culto_oficial,
 musicos_oficializacao=excluded.musicos_oficializacao,musicos_troca_instrumento=excluded.musicos_troca_instrumento,
 organistas_rjm=excluded.organistas_rjm,organistas_culto_oficial=excluded.organistas_culto_oficial,
 organistas_oficializacao=excluded.organistas_oficializacao,organistas_testes_especiais=excluded.organistas_testes_especiais;
 update public.cartas_emissoes set review_result=p_resultado,review_version=review_version+1,
 reviewed_by=p_actor,reviewed_name=p_nome,reviewed_at=now(),review_notes=p_notes,exam_id=e where id=c.id
 returning * into c;
 return to_jsonb(c);
end $$;
revoke all on function public.cartas_confirmar_resultado(uuid,text,uuid,text,integer,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.cartas_confirmar_resultado(uuid,text,uuid,text,integer,text,jsonb,jsonb) to service_role;
notify pgrst,'reload schema';

commit;
