-- Adiciona o complemento do endereço ao cadastro da irmandade.
-- Execute uma vez no SQL Editor do Supabase.

alter table public.visitas_irmandade
    add column if not exists complemento text null;

comment on column public.visitas_irmandade.complemento is
'Complemento do endereço residencial, como apartamento, bloco, casa ou travessa.';
