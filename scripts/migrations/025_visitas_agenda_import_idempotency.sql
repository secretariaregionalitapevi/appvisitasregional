-- Chave determinística usada somente por documentos importados no Calendário de Visitas.
-- Eventos manuais existentes permanecem inalterados e continuam sendo comparados pela API.
alter table public.visitas_agenda
    add column if not exists import_key text;

create unique index if not exists visitas_agenda_import_key_uidx
    on public.visitas_agenda(import_key)
    where import_key is not null;

comment on column public.visitas_agenda.import_key is
'Chave idempotente: comum + dia + categoria + pessoa/endereço do documento importado.';
