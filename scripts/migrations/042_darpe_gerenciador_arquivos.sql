begin;
create table if not exists public.darpe_pastas (
 id uuid primary key default gen_random_uuid(),
 nome text not null check(length(trim(nome)) between 1 and 100),
 parent_id uuid references public.darpe_pastas(id),
 categoria text not null check(categoria in ('documentos','instrumentos','setores')),
 sistema boolean not null default false,
 created_by text not null,
 created_at timestamptz not null default now(),
 check((sistema and parent_id is null) or (not sistema and parent_id is not null))
);
create unique index if not exists darpe_pasta_nome on public.darpe_pastas(parent_id,lower(nome));
insert into public.darpe_pastas(id,nome,categoria,sistema,created_by) values
 ('00000000-0000-4000-8000-000000000001','Documentos','documentos',true,'sistema'),
 ('00000000-0000-4000-8000-000000000002','Instrumentos','instrumentos',true,'sistema'),
 ('00000000-0000-4000-8000-000000000003','Setores','setores',true,'sistema') on conflict(id) do nothing;
create or replace function public.darpe_pasta_validar() returns trigger language plpgsql set search_path=public as $$
declare cursor_id uuid; parent_category text; steps integer:=0;
begin
 perform pg_advisory_xact_lock(hashtext('darpe-pastas'));
 if tg_op='UPDATE' and (old.sistema or new.sistema<>old.sistema or new.categoria<>old.categoria) then
  raise exception 'Pastas principais e categoria da pasta não podem ser alteradas.';
 end if;
 if new.parent_id is not null then
  select categoria into parent_category from public.darpe_pastas where id=new.parent_id;
  if parent_category is distinct from new.categoria then raise exception 'A pasta deve permanecer na mesma área.'; end if;
  cursor_id:=new.parent_id;
  while cursor_id is not null loop
   steps:=steps+1;
   if cursor_id=new.id or steps>16 then raise exception 'Hierarquia de pastas inválida.'; end if;
   select parent_id into cursor_id from public.darpe_pastas where id=cursor_id;
  end loop;
 end if;
 return new;
end $$;
drop trigger if exists darpe_pasta_validacao on public.darpe_pastas;
create trigger darpe_pasta_validacao before insert or update on public.darpe_pastas for each row execute function public.darpe_pasta_validar();
alter table public.darpe_pastas enable row level security;
revoke all on public.darpe_pastas from anon,authenticated;
grant select,insert,update on public.darpe_pastas to service_role;

alter table public.darpe_documentos add column if not exists pasta_id uuid references public.darpe_pastas(id);
alter table public.darpe_documentos add column if not exists version integer not null default 1;
alter table public.darpe_documentos add column if not exists updated_at timestamptz not null default now();
alter table public.darpe_documentos add column if not exists updated_by text not null default '';
alter table public.darpe_documentos add column if not exists deleted_at timestamptz;
update public.darpe_documentos set pasta_id=case categoria when 'instrumentos' then '00000000-0000-4000-8000-000000000002'::uuid when 'setores' then '00000000-0000-4000-8000-000000000003'::uuid else '00000000-0000-4000-8000-000000000001'::uuid end where pasta_id is null;
alter table public.darpe_documentos alter column pasta_id set not null;
create table if not exists public.darpe_documento_versoes (
 id uuid primary key default gen_random_uuid(),
 documento_id uuid not null references public.darpe_documentos(id),
 version integer not null,
 snapshot jsonb not null,
 created_at timestamptz not null default clock_timestamp(),
 unique(documento_id,version)
);
alter table public.darpe_documento_versoes enable row level security;
revoke all on public.darpe_documento_versoes from anon,authenticated;
grant select on public.darpe_documento_versoes to service_role;
insert into public.darpe_documento_versoes(documento_id,version,snapshot)
select id,version,to_jsonb(d) from public.darpe_documentos d on conflict(documento_id,version) do nothing;
create or replace function public.darpe_documento_versionar() returns trigger language plpgsql set search_path=public as $$
begin
 if tg_op='UPDATE' then
  new.version:=old.version+1;
  new.created_at:=old.created_at;
  new.created_by:=old.created_by;
 else new.version:=1;
 end if;
 select categoria into new.categoria from public.darpe_pastas where id=new.pasta_id;
 if new.categoria is null then raise exception 'Pasta não encontrada.'; end if;
 new.updated_at:=clock_timestamp();
 return new;
end $$;
create or replace function public.darpe_documento_auditar() returns trigger language plpgsql security definer set search_path=public as $$
begin
 insert into public.darpe_documento_versoes(documento_id,version,snapshot) values(new.id,new.version,to_jsonb(new));
 return new;
end $$;
revoke all on function public.darpe_documento_auditar() from public;
drop trigger if exists darpe_documento_versionar on public.darpe_documentos;
create trigger darpe_documento_versionar before insert or update on public.darpe_documentos for each row execute function public.darpe_documento_versionar();
drop trigger if exists darpe_documento_auditar on public.darpe_documentos;
create trigger darpe_documento_auditar after insert or update on public.darpe_documentos for each row execute function public.darpe_documento_auditar();
revoke delete on public.darpe_documentos from service_role;
notify pgrst,'reload schema';
commit;
