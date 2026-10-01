# Histórico operacional do SAM

Esta trilha é independente da Auditoria de acesso do aplicativo. Ela arquiva os acontecimentos produzidos pelo SAM original e mantém uma cópia da identidade e da localidade exibidas na origem.

## Ativação

1. Execute `scripts/migrations/028_sam_audit_history.sql` no SQL Editor do Supabase.
2. Faça a primeira carga histórica no computador que executa o worker:

   `python manage.py sync_sam_audit --full --limit 100000`

3. Reinicie o worker SAM. A partir daí, a janela recente será capturada junto da sincronização incremental de aulas.

Variáveis opcionais:

- `SAM_AUDIT_SYNC_LIMIT`: máximo de linhas consideradas em cada execução; padrão 2000.
- `SAM_AUDIT_LOOKBACK_DAYS`: janela sobreposta da captura incremental; padrão 7 dias. A sobreposição é segura porque a assinatura de cada evento impede duplicações.

## Garantias

- `actor_name_snapshot`, `congregation_snapshot` e `action_raw` são cópias históricas, não referências ao cadastro atual.
- Não há relacionamento com exclusão em cascata para usuário, aluno, turma ou aula.
- IDs citados no texto precário do SAM são extraídos para `parsed_refs`, mas o texto original permanece intacto.
- Reprocessamentos usam `source_fingerprint` único e não duplicam eventos.
- A tabela usa RLS e somente o `service_role` acessa os dados; a página exige perfil regional ou global.

## Página

Abra `/gem/sam/historico/` ou use **GEM > Histórico SAM**. A pesquisa combina texto livre, tipo de ação, operador, localidade e período; cada evento expõe os IDs identificados e os dados técnicos preservados.
