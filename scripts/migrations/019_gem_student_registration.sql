alter table public.musica_acompanhamento_aluno
  add column if not exists possui_instrumento boolean,
  add column if not exists instrumento_proprio boolean,
  add column if not exists tonalidade text,
  add column if not exists data_inicio_gem date,
  add column if not exists data_nascimento date,
  add column if not exists estado_civil text,
  add column if not exists telefone text,
  add column if not exists nome_responsavel text,
  add column if not exists grau_parentesco text,
  add column if not exists consentimento_lgpd boolean not null default false;
