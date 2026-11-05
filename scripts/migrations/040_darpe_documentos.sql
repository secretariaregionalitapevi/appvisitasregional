begin;
create table if not exists public.darpe_documentos (
 id uuid primary key default gen_random_uuid(),
 titulo text not null check(length(titulo) between 1 and 160),
 descricao text not null default '' check(length(descricao)<=2000),
 categoria text not null check(categoria in ('documentos','instrumentos','setores')),
 object_path text not null unique,
 original_name text not null,
 byte_size integer not null check(byte_size between 1 and 20971520),
 created_by text not null,
 created_at timestamptz not null default now()
);
alter table public.darpe_documentos enable row level security;
revoke all on public.darpe_documentos from anon, authenticated;
grant all on public.darpe_documentos to service_role;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('darpe-documentos','darpe-documentos',false,20971520,array['application/pdf'])
on conflict(id) do update set public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
notify pgrst, 'reload schema';
commit;
