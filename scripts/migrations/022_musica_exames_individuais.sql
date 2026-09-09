-- Gestão individual e idempotente de exames e testes da Música.
create table if not exists public.musica_exames_individuais (
 id uuid primary key default gen_random_uuid(), aluno_id uuid not null,
 nome_aluno text not null, registro_msa text, municipio text not null, comum text,
 instrumento text, categoria text, data_exame date not null, tipo_exame text not null,
 resultado text not null default 'AGENDADO' check (resultado in ('AGENDADO','APROVADO','RETORNOU AO CICLO','AUSENTE')),
 encarregado_local text, observacoes text, prova_url text, prova_nome text,
 lancado_por text not null, origem text not null default 'PAINEL' check (origem in ('PAINEL','IMPORTACAO','APP_EXAMES')),
 chave_idempotencia text not null unique, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.musica_exames_individuais drop constraint if exists musica_exames_individuais_resultado_check;
update public.musica_exames_individuais set resultado='RETORNOU AO CICLO' where resultado='REPROVADO';
alter table public.musica_exames_individuais add constraint musica_exames_individuais_resultado_check check (resultado in ('AGENDADO','APROVADO','RETORNOU AO CICLO','AUSENTE'));
create index if not exists musica_exames_data_idx on public.musica_exames_individuais(data_exame desc);
create index if not exists musica_exames_aluno_idx on public.musica_exames_individuais(aluno_id);
create index if not exists musica_exames_municipio_idx on public.musica_exames_individuais(municipio);
alter table public.musica_exames_individuais enable row level security;
revoke all on public.musica_exames_individuais from anon, authenticated;
insert into storage.buckets (id,name,public,file_size_limit,allowed_mime_types)
values ('gem_exam_documents','gem_exam_documents',false,12582912,array['application/pdf','image/jpeg','image/png','image/webp'])
on conflict (id) do update set public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
drop policy if exists "Service role manages exam documents" on storage.objects;
create policy "Service role manages exam documents" on storage.objects for all to service_role
using (bucket_id='gem_exam_documents') with check (bucket_id='gem_exam_documents');

-- Vínculo estável com a agenda e identificação do autor para auditoria.
alter table public.musica_exames_individuais add column if not exists lancado_por_id uuid;
alter table public.musica_exames_individuais add column if not exists agenda_evento_id text;
alter table public.musica_exames_individuais add column if not exists agenda_evento_titulo text;
alter table public.musica_exames_individuais add column if not exists agenda_evento_data date;
alter table public.musica_exames_individuais add column if not exists agenda_evento_hora time;
alter table public.musica_exames_individuais add column if not exists agenda_evento_url text;
create index if not exists musica_exames_created_idx on public.musica_exames_individuais(created_at desc);
create index if not exists musica_exames_agenda_idx on public.musica_exames_individuais(agenda_evento_id);

create table if not exists public.musica_exames_auditoria (
 id bigint generated always as identity primary key,
 exame_id uuid not null,
 acao text not null check (acao in ('INSERT','UPDATE','DELETE')),
 lancado_por text,
 lancado_por_id uuid,
 agenda_evento_id text,
 dados jsonb not null,
 created_at timestamptz not null default now()
);
alter table public.musica_exames_auditoria enable row level security;
revoke all on public.musica_exames_auditoria from anon, authenticated;

create or replace function public.auditar_musica_exame() returns trigger
language plpgsql security definer set search_path = public as $$
begin
 insert into public.musica_exames_auditoria(exame_id,acao,lancado_por,lancado_por_id,agenda_evento_id,dados)
 values (coalesce(new.id,old.id),tg_op,coalesce(new.lancado_por,old.lancado_por),coalesce(new.lancado_por_id,old.lancado_por_id),coalesce(new.agenda_evento_id,old.agenda_evento_id),to_jsonb(coalesce(new,old)));
 return coalesce(new,old);
end; $$;
drop trigger if exists musica_exames_auditoria_trigger on public.musica_exames_individuais;
create trigger musica_exames_auditoria_trigger after insert or update or delete on public.musica_exames_individuais for each row execute function public.auditar_musica_exame();