-- Documentos de progresso são privados e acessados somente pela API autenticada.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('gem_documents', 'gem_documents', false, 10485760, array['application/pdf','image/jpeg','image/png'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
allowed_mime_types = excluded.allowed_mime_types;

create index if not exists musica_atividades_tipo_idx
on public.musica_acompanhamento_atividades(aluno_id, tipo_atividade, data_atividade desc);
