-- Remove somente a linha automática de origem das importações anteriores.
-- Preserva observações digitadas e metadados do responsável pelo atendimento.
begin;
update public.visitas_agenda
set observacoes = regexp_replace(
    observacoes,
    E'(^|\n)Importado de [^\r\n]+ \\([0-9a-f]{12}\\)\\.[\r]?(\n|$)',
    E'\\1',
    'g'
)
where import_key is not null
  and observacoes ~ E'(^|\n)Importado de [^\r\n]+ \\([0-9a-f]{12}\\)\\.[\r]?(\n|$)';
commit;
