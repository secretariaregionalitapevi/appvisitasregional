-- Preserve the authenticated actor on lesson and nominal attendance records.
-- Existing rows remain NULL and continue to be shown as legacy/unidentified.
alter table public.musicalizacao_aulas
    add column if not exists created_by_user_id text,
    add column if not exists created_by_name text,
    add column if not exists created_by_email text,
    add column if not exists updated_by_user_id text,
    add column if not exists updated_by_name text,
    add column if not exists updated_by_email text;

alter table public.musicalizacao_presenca
    add column if not exists created_by_user_id text,
    add column if not exists created_by_name text,
    add column if not exists created_by_email text,
    add column if not exists updated_by_user_id text,
    add column if not exists updated_by_name text,
    add column if not exists updated_by_email text;

comment on column public.musicalizacao_presenca.created_by_user_id is
'ID do usuário autenticado que registrou a presença.';
comment on column public.musicalizacao_presenca.created_by_name is
'Nome do usuário no momento do registro da presença.';
comment on column public.musicalizacao_presenca.created_by_email is
'E-mail do usuário no momento do registro da presença.';
comment on column public.musicalizacao_presenca.updated_by_user_id is
'ID do usuário autenticado que realizou a alteração mais recente.';
comment on column public.musicalizacao_presenca.updated_by_name is
'Nome do usuário que realizou a alteração mais recente.';
comment on column public.musicalizacao_presenca.updated_by_email is
'E-mail do usuário que realizou a alteração mais recente.';
