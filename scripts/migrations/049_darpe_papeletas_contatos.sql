-- Contatos opcionais da instituição atendida; nunca inferir números do campo local.
begin;
alter table public.darpe_papeletas
 add column if not exists whatsapp text not null default '',
 add column if not exists telefone text not null default '';
notify pgrst, 'reload schema';
commit;
