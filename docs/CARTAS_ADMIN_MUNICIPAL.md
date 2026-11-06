# Administração municipal de cartas

A página `/admin` usa o cadastro já existente do sistema regional e a autenticação Supabase por e-mail e senha. Não cria usuários nem aprova cadastros automaticamente.

## Liberação

1. O secretário acessa **Solicitar cadastro** e preenche o cadastro regional.
2. Na trilha de auditoria, o administrador confirma o município e seleciona **Municipal**, **Música (gestão de cartas)** e situação **Aprovado**. Desmarque as demais pastas quando o acesso for exclusivo às cartas.
3. O secretário entra em `/admin` com o mesmo e-mail e senha. A liberação Música é independente de Musicalização e não libera o dashboard principal.

Aplicar no Supabase compartilhado as migrações 044 (relação/entregas) e 045 (pasta Música), disponíveis no projeto APP_VISITAS_CCB. Configure `REGIONAL_PORTAL_URL` no APP_CARTAS com o endereço do sistema regional. No sistema regional, `CARTAS_APP_URL` permite redirecionar acessos exclusivos da pasta Música para este aplicativo.

## Funcionamento

- O município aprovado é conferido no servidor em cada solicitação, assim como a aprovação e a pasta autorizada. Não há seletor de município para ampliar o acesso.
- A relação reúne cartas emitidas e candidatos importados, com filtros por exame, músicos/organistas, nome e recebimento.
- A agenda oficial define as pré-avaliações. O prazo padrão é a sexta-feira em ou antes de um mês antes da pré-avaliação correspondente; um prazo válido definido pela regional tem prioridade. Datas antigas salvas sem referência oficial são ignoradas. Se a agenda falhar, nenhum prazo é presumido.
- Marcar ou desmarcar o recebimento usa a mesma função auditada do dashboard, com responsável, data, versão e proteção contra edição simultânea. Desmarcar remove a data efetiva, mantendo o histórico.
- Os PDFs ficam restritos a cartas do município aprovado. A emissão pública e a propriedade das cartas dos visitantes continuam independentes.
- A sessão administrativa usa cookie próprio criptografado HttpOnly, SameSite=Strict, validade máxima de oito horas e Secure em produção. Tokens não são enviados ao JavaScript nem armazenados no navegador. Mutações conferem origem e CSRF.

Os níveis Global e Regional com pasta Música podem entrar, mas também precisam de município válido e recebem o mesmo recorte municipal nesta página. Para administrar outros municípios, use o dashboard principal com a autorização apropriada.
