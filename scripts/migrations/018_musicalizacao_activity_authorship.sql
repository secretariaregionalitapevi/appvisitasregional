-- Auditoria nominal dos lançamentos da Musicalização.
-- A identidade é preenchida pelo backend a partir da sessão autenticada.
alter table public.musicalizacao_aulas
    add column if not exists created_by_user_id text,
    add column if not exists created_by_name text,
    add column if not exists created_by_email text,
    add column if not exists updated_by_user_id text,
    add column if not exists updated_by_name text,
    add column if not exists updated_by_email text;

comment on column public.musicalizacao_aulas.created_by_user_id is
'ID imutável do usuário autenticado que criou o lançamento.';
comment on column public.musicalizacao_aulas.created_by_name is
'Nome do usuário no momento da criação, preservado para auditoria.';
comment on column public.musicalizacao_aulas.updated_by_user_id is
'ID do usuário autenticado que realizou a alteração mais recente.';
comment on column public.musicalizacao_aulas.updated_by_name is
'Nome do usuário que realizou a alteração mais recente.';
