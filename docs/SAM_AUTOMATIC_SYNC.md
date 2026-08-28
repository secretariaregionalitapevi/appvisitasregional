# Sincronização automática do SAM

O painel web não executa scraping. Um worker Windows consulta o SAM, compara o catálogo pelo ID permanente do aluno e grava somente diferenças no Supabase.

O worker usa um único Chromium em modo headless. Ele autentica uma vez, reutiliza a mesma sessão para catálogo e históricos e somente refaz o login se a sessão expirar. A cada aluno concluído, grava `last_history_sync_at`; depois de queda de energia ou reinício, a fila recomeça no primeiro estado ainda pendente. Reprocessamentos são idempotentes.

## Preparação

1. Execute `scripts/migrations/012_sam_automatic_sync.sql` no SQL Editor do Supabase.
2. Configure no ambiente do computador do worker:
   - `SAM_SCRAPER_DIR`: pasta que contém `web_scraper.py`.
   - `SAM_SYNC_INTERVAL_SECONDS`: intervalo entre ciclos; padrão 1800 segundos.
   - `SAM_SYNC_HISTORY_LIMIT`: históricos completos processados por ciclo; padrão 5.
3. Faça um ciclo controlado:

   `python manage.py run_sam_sync_worker --once --history-limit 1`

4. Depois de revisar `sam_sync_runs`, instale a tarefa:

   `powershell -ExecutionPolicy Bypass -File scripts/install_sam_sync_task.ps1`

   Se a política do Windows não permitir tarefas agendadas sem administrador, use a inicialização do usuário:

   `powershell -ExecutionPolicy Bypass -File scripts/install_sam_sync_startup.ps1`

## Regras de segurança

- O ID interno do SAM é a identidade primária da sincronização.
- No primeiro vínculo, nome só é aceito quando produz exatamente um aluno.
- Um aluno novo só é criado quando nome e comum podem ser associados sem ambiguidade.
- Registros que desaparecerem do SAM não são excluídos automaticamente.
- Mudança sem data no SAM usa o instante da detecção e `date_basis=detected_at_sync`.
- Históricos usam assinaturas idempotentes, portanto reprocessamento não duplica eventos.
- Falhas ficam registradas e são tentadas novamente em ciclos posteriores.

## Limitação de hospedagem

A Vercel continua responsável apenas pelo painel Django. O worker precisa permanecer em um Windows com acesso ao SAM e navegador Playwright disponível, pois a Vercel não mantém processos contínuos nem navegador automatizado em segundo plano.
