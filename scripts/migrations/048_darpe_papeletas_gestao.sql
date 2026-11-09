-- Gestão das papeletas pelo servidor principal, após autenticação e escopo.
begin;
grant update, delete on public.darpe_papeletas to service_role;
notify pgrst, 'reload schema';
commit;
