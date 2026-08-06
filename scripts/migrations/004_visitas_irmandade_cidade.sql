-- Adiciona a cidade/município ao cadastro individual da irmandade.
-- Execute uma vez no SQL Editor do Supabase.

alter table public.visitas_irmandade
    add column if not exists cidade text null;

-- Preenche os cadastros atuais a partir do catálogo oficial de comuns.
update public.visitas_irmandade as membro
set cidade = comum.cidade
from public.visitas_comuns as comum
where upper(trim(membro.comum)) = upper(trim(comum.comum))
  and nullif(trim(membro.cidade), '') is null
  and nullif(trim(comum.cidade), '') is not null;

create index if not exists visitas_irmandade_cidade_idx
    on public.visitas_irmandade (cidade);

comment on column public.visitas_irmandade.cidade is
'Cidade ou município de residência do membro, por exemplo Itapevi ou Cotia.';
