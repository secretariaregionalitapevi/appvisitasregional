-- PostgREST on_conflict precisa de índice único sem predicado.
-- Valores NULL dos eventos manuais continuam permitidos e não conflitam.
begin;
drop index if exists public.visitas_agenda_import_key_uidx;
create unique index visitas_agenda_import_key_uidx on public.visitas_agenda(import_key);
commit;
