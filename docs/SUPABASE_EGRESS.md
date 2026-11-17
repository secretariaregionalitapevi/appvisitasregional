# Controle do egress Supabase

## Diagnóstico e limites da investigação

A captura fornecida registra 5,746 GB consumidos de 5 GB. Ela não discrimina
Database, Auth, Storage e demais origens. A inspeção do código identificou
desperdícios, mas não determina quantos GB cada fluxo consumiu em produção.
Não foram executadas varreduras nas tabelas de produção para este diagnóstico.

Referência: https://supabase.com/docs/guides/platform/manage-your-usage/egress

## Correções

- Catálogo SAM: intervalo padrão de 120 para 3600 segundos (até 720 para 24
  verificações diárias em ociosidade; redução de frequência de 99,86%).
- Aulas e auditoria SAM: padrão de 300 para 86400 segundos (288 para 1; 99,65%).
- A sincronização incremental de aulas não baixa mais a tabela inteira de
  presenças para calcular uma lista usada apenas na retomada da carga completa.
- Catálogo SAM consulta somente os campos de estado necessários à conciliação;
  não transfere source_payload e outros campos não usados. Paginação ordenada.
- Lotes cheios de históricos continuam sem reler o catálogo entre cada lote.
- Painel de cartas: atualização automática de cinco minutos para uma hora;
  ações e filtros continuam atualizando os dados normalmente.
- Mapa: consulta automática da agenda de um para cinco minutos; continua
  suspensa em aba oculta. A animação dos marcadores não consulta o Supabase.
- Sino: atualização de cinco para quinze minutos, com intervalo mínimo também
  ao recuperar visibilidade; alterações de cartas forçam atualização imediata.
- Cache local em memoria do Django, sem Redis ou servico externo. Os prazos e invalidacoes existentes continuam valendo. Cada instancia da Vercel tem seu proprio cache; ele pode ser perdido em reinicios ou novas instancias.
- Leituras via supabase_get registram caminho, status, Content-Length e tentativa
  com SUPABASE_EGRESS_LOG=1. Esse diagnóstico não cobre requests.get direto,
  SDKs ou outro aplicativo ligado ao mesmo projeto. Content-Length pode faltar
  e não equivale necessariamente ao valor faturado; consultar o painel também.

## Aplicação em produção

1. Publicar o código e instalar requirements.txt atualizado.
2. Reiniciar o worker SAM para adotar os novos padrões. Variáveis
   SAM_SYNC_INTERVAL_SECONDS e SAM_CLASSES_SYNC_INTERVAL_SECONDS ou argumentos
   --interval e --classes-interval existentes sobrescrevem os padrões: ajustar
   também para 3600 se configurados. As aulas e novos cadastros podem aparecer
   até uma hora depois. Histórico pendente continua sendo processado por lote.
3. Nenhuma configuracao de Redis e necessaria. O cache utiliza a memoria do processo.
   A economia depende principalmente da reducao das consultas e dos ciclos diarios.
4. Habilitar SUPABASE_EGRESS_LOG=1 temporariamente e comparar os caminhos mais
   frequentes/volumosos. Não habilitar log de corpos ou cabeçalhos de autorização.
5. No Usage do Supabase, separar egress por projeto e serviço. Comparar o
   crescimento diário após a publicação com período de atividade semelhante.
   O consumo acumulado não diminui após a correção. A organização pode ter
   outros projetos e o APP_CARTAS pode continuar gerando tráfego independentemente.

## Preservação de acesso e validação

A confirmação de aprovação do perfil no middleware continua em toda requisição
protegida. Não foi introduzido cache de páginas autenticadas ou relaxamento de
escopo municipal/local. Os caches existentes mantêm seus prazos e invalidações.
Não foi feita alteração de esquema ou exclusão de dados.

Testes de regressão cobrem ausência de leitura integral de presenças no delta,
retomada da carga completa e ausência de tokens nos logs. Executar também as
suítes SAM, acesso por módulo, cartas e busca GEM antes da publicação.

Não é possível prometer consumo abaixo da franquia sem medir o tráfego real
após implantação e incluir todos os aplicativos/projetos da organização.

Uma sincronizacao diaria envolve varias requisicoes tecnicas para catalogo, aulas, auditoria e historicos; nao significa uma unica requisicao HTTP. O registro diario deve permanecer em disco persistente no host do worker.
