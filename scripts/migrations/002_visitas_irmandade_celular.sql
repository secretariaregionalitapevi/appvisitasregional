-- Adiciona o celular de contato ao cadastro da irmandade.
-- Execute uma vez no SQL Editor do Supabase.

alter table public.visitas_irmandade
    add column if not exists celular text null;

comment on column public.visitas_irmandade.celular is
'Celular de contato do membro, preferencialmente no formato (DD) 99999-9999.';
