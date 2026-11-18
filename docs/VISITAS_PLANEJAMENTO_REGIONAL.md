# Planejamento regional de visitas

## Habilitacao

1. Aplicar `scripts/migrations/057_visitas_planejamento_regional.sql` no SQL Editor
   do Supabase, depois das migrations de equipes existentes (002 e 007).
2. Publicar o codigo e os arquivos estaticos. Reiniciar o Django local quando necessario.
3. Abrir **Visitas > Roteiro Inteligente > Planejamento regional**. Tambem existe
   um acesso em **Equipes de Visita > Confirmar grupos por data**.

A migration cria participacoes por data, snapshots dos roteiros emitidos e
operacoes atomicas. Nao remove cadastros, equipes ou visitas existentes.
Nenhum banco de producao foi alterado pelos testes deste desenvolvimento.

Aplicar tambem `scripts/migrations/058_visitas_coordenador_cadastrado.sql` para
atualizar o cadastro da equipe ao editar o coordenador no roteiro. A migration
resgata os nomes ja salvos, preserva os roteiros emitidos e controla concorrencia.

## Uso

1. Escolher municipio e data e carregar os grupos.
2. O sistema preenche os coordenadores identificados no cadastro das equipes.
   Conferir a disponibilidade, desmarcar grupos ausentes ou substituir nomes e salvar.
   Ao calcular a distribuicao, a disponibilidade e os coordenadores carregados
   sao salvos automaticamente para a data, sem confirmacoes individuais. Apenas
   abrir a pagina nao grava alteracoes. Tambem e possivel salvar as alteracoes
   sem gerar um roteiro, pelo botao especifico.
   Trocar Joao por Manoel atualiza o coordenador cadastrado da equipe e a data
   selecionada. O responsavel dos roteiros ja emitidos em agosto e preservado.
3. Pesquisar pelo codigo ou nome e selecionar as comuns cujas familias serao atendidas.
4. Calcular a previa. Sete casas com sete grupos resultam em uma casa por grupo.
   Todas as familias elegiveis sao distribuidas, sem teto por grupo. Cem familias
   distintas de tres comuns e quatro grupos resultam em 25 visitas por grupo.
   Quando a divisao nao e exata, a diferenca e de no maximo uma visita.
   Para reduzir a quantidade por grupo, confirmar mais grupos ou selecionar menos comuns.
5. Conferir familias, enderecos e comuns e, se necessario, trocar o grupo de uma
   casa na propria previa. A quantidade e calculada pelo sistema, sem campo de maximo.
6. Confirmar para gravar na agenda. Abrir a impressao de todos os grupos.
   Roteiros emitidos podem ser reabertos ao carregar novamente a mesma data.

Em **Equipes de Visita**, selecionar municipio e data para ver o coordenador
vigente, grupos desabilitados e substituicoes. O botao **Ajustar nesta data**
abre o mesmo planejamento com municipio e data preenchidos. O coordenador
cadastrado e utilizado automaticamente quando nao existe uma excecao salva.
O botao de retirar remove o coordenador do cadastro e desabilita o grupo na data.
Para uma ausencia temporaria, apenas desmarcar o grupo, sem apagar o nome.
Marcar novamente um grupo sem nome recupera automaticamente o coordenador
do cadastro; o nome continua editavel para substituicoes.

## Painel administrativo

Roteiro Inteligente abre diretamente o planejamento regional para os perfis
global, regional e municipal. O municipio e a data carregam os grupos
automaticamente, com botao de atualizacao e mensagem visivel em caso de falha.
O formulario legado local continua disponivel em `roteiro-inteligente/?modo=local`
e permanece como entrada para perfis locais. Falhas na leitura do historico nao
impedem carregar os coordenadores.

O painel acompanha municipio e data selecionados e apresenta grupos disponiveis,
familias na previa, visitas por grupo e familias ja agendadas naquela data.
Moradores no mesmo endereco contam como uma familia/parada. A previa e a agenda
gravada possuem indicadores separados; antes do calculo, a previa nao exibe um
zero ficticio. Ajustes manuais atualizam imediatamente os totais por grupo.

A previa e o painel de exportacao mostram a cobertura por comum, inclusive
comuns selecionadas que nao tiveram nenhuma familia incluida. O roteiro salvo
em 17/11/2026 continha Vila Belmira e Jardim Alabama, sem Chacara Regina. A auditoria
de leitura identificou 39 cadastros elegiveis da Regina; eles entram quando a comum
e selecionada, sem descartar familias por morar em outro bairro.

Depois de salvar os coordenadores, a secao recolhe e pode ser reaberta em
**Gerenciar**. A pesquisa das comuns limpa o texto digitado e fecha a lista apos
cada selecao, preservando as comuns escolhidas.

Na previa, o resumo por grupo e a confirmacao ficam visiveis; comuns e lista de
familias recolhem automaticamente. Clicar num grupo abre somente suas familias.
A lista possui pesquisa e paginas de dez casas. Alteracoes de grupo permanecem
em memoria ao trocar pagina ou filtro; confirmar envia sempre o lote completo.
A cobertura por comum fica recolhida, abrindo quando houver comuns sem familias.
Ao confirmar, a pagina mostra os arquivos salvos, sem repetir a previa inteira.

Os indicadores da agenda usam uma consulta restrita a data e aos grupos do
municipio, ao carregar o planejamento ou confirmar a gravacao. Nao ha polling.
Se o indicador estiver indisponivel, uma gravacao concluida continua sendo
informada como concluida.

## Exportacao por grupo

Depois de confirmar, os arquivos aparecem na mesma pagina no Painel de exportacao.
Um PDF vetorial e gerado por grupo, com cartoes compactos, periodo, horario,
categorias, preferencias, comum do cadastro e QR local. Os nomes usam
`ROTEIRO_VISITAS_COMUM_GRUPO_X.pdf`; quando ha familias de mais de uma comum,
as comuns efetivamente atendidas pelo grupo compoem o nome. O pacote ZIP reune
esses PDFs individuais, sem juntar todos os grupos em um unico PDF.

Excel consolida as familias por grupo, com data real e cabecalho institucional.
O painel permite reabrir distribuicoes ja salvas ao carregar a mesma data.
Exportar nao redistribui nem grava visitas. Apontamentos restritos so sao
incluidos para os niveis autorizados, inclusive nos snapshots antigos.

A visualizacao individual reutiliza o template original de visitas. O PDF
inclui distancia desde a congregacao e da casa anterior, preferencias e notas
autorizadas. Distancias dos badges sao aproximadas em linha reta, como no roteiro
original. O PDF e o ZIP incluem o mapa real de ruas Google, com percurso rodoviario
e pins numerados, usando a chave existente. A opcao **Somente cartoes** omite o
mapa. A imagem preserva o logo e a atribuicao Google; a chave nao entra no PDF.
Mapas e percursos sao reaproveitados por 15 minutos, sem Redis e sem Supabase.

Preferencias existentes aparecem em badges. Quando o cadastro nao tem preferencia,
o cartao informa **Sem preferencia informada**. Exportacoes ativas recuperam
preferencias ausentes do snapshot em uma consulta curta e restrita aos IDs.
Documentos historicos preservam os valores originalmente emitidos.

O agrupamento troca casas entre grupos para reduzir dispersao, sem alterar as
cotas. A troca e descartada quando aumenta o deslocamento estimado do recorte.
A sequencia reaproveita o otimizador do roteiro original, sem novas consultas de
geocodificacao durante a otimizacao. Trechos acima de 1 km aparecem na previa
para conferencia dos enderecos; nenhuma distancia e encurtada artificialmente.

O acabamento do PDF baixado tambem preserva os elementos do template original
conferido no GitHub: icones Font Awesome locais incorporados, pin no endereco,
badges arredondados de hora/setor/categoria/preferencia/distancia, botoes de grupo
e data arredondados, cartoes com borda azul e separador tracejado do QR.

Roteiros ativos antigos salvos sem GPS exigem **Recalcular sequencia com GPS** e
confirmar antes de liberar os PDFs atualizados. Isso atualiza ordem e horarios
na agenda pela mesma transacao do planejamento. Reimprimir um arquivo nao altera
agendamentos nem finge que a sequencia antiga ja foi corrigida. Historicos
substituidos continuam disponiveis como documentos de auditoria.

A primeira parada do planejamento novo e a casa atribuida mais proxima da comum
de partida. A referencia avanca depois de cada casa; nao retorna a igreja na
mudanca de manha para tarde. Se faltar a coordenada de um ponto, o trecho fica
indisponivel, sem reutilizar a igreja como substituta da casa anterior.

## Regras de atendimento

- As casas sao agrupadas pelo endereco dentro do municipio, incluindo moradores
  de comuns diferentes. Complementos diferentes continuam sendo casas distintas.
  Novas visitas preservam o vinculo de cada pessoa com seu cadastro na agenda,
  com o mesmo grupo e horario para todos os moradores elegiveis da casa.
- Cada familia aparece com a **comum do cadastro**; o endereco determina onde
  sera atendida. Congregar no Jardim Ruth e morar na Vila das Chacaras nao exclui
  a familia do roteiro conjunto.
- Visitas regionais ainda **Marcadas** nas comuns selecionadas sao redistribuidas.
  Os registros existentes sao atualizados; nao sao recriados nem excluidos.
- Visitas concluidas, locais e outros agendamentos fixos sao preservados. Casas
  com atendimento recente (15 dias) ou agendamento futuro nao sao agendadas de novo.
- O planejamento considera primeiro as casas ja marcadas e depois as nunca
  visitadas ou com visita mais antiga, pelo campo de ultima visita do cadastro.
- Integrantes de equipes e grupos, inativos e cadastros sem endereco nao entram
  como destinos automaticos. Uma familia elegivel na mesma casa continua visivel.
- Todas as familias elegiveis do recorte entram na previa. Nao existe saldo
  aguardando capacidade, limite fixo de 8/10 visitas ou preenchimento dessa meta.
  Visitas fixas fora do recorte sao preservadas separadamente, sem alterar a
  divisao igualitaria das familias selecionadas.
- Coordenadas faltantes sao localizadas no Google Maps/ArcGIS (autorizado pelo
  usuario), com cache em disco por 90 dias e falhas por uma hora, sem Redis e sem
  usar Supabase como cache. Localizacoes devem corresponder ao municipio. Sem
  localizacao confirmada, a familia continua no roteiro e a distancia aparece
  como indisponivel, sem coordenadas inventadas. O calculo nao e rodoviario.
- Preferencias de manha/tarde sao consideradas. Preferencias conflitantes no
  mesmo endereco sao sinalizadas para confirmar o horario com a familia.
- O QR para GPS e gerado localmente. Enderecos nao sao enviados a servicos de QR.
- O roteiro antigo por equipe atende a geracao local e os grupos especificos
  RF/RE, que preservam seu calendario independente. Consultar um grupo por
  letra pelo endereco antigo nao completa novas casas nem reorganiza horarios,
  preservando o equilibrio do planejamento regional.

## Controle e consistencia

### Excluir comuns do roteiro e limpar a agenda opcionalmente

Aplicar `scripts/migrations/060_visitas_exclusao_seletiva_comuns.sql` apos as
migrations do planejamento regional. A 059 permanece para compatibilidade.
Na lixeira do painel, escolher por comum: remover do roteiro e, opcionalmente,
excluir tambem da agenda. A limpeza da agenda vem desmarcada e so pode ser
selecionada para uma comum que sera removida do roteiro. Antes de gravar,
a confirmacao lista as comuns afetadas e a quantidade de agendamentos.

A limpeza exclui somente visitas Marcadas vinculadas ao ID do roteiro escolhido,
na data dele e pertencentes aos moradores daquela comum no snapshot. Visitas
realizadas, outras datas, agendas avulsas e outras distribuicoes sao preservadas.
O codigo da comum permite reconhecer nomes legados com maiusculas/minusculas.
Casas compartilhadas preservam os moradores e agendamentos das comuns restantes.

A remocao parcial mantem as outras comuns no roteiro. Retirar todas as comuns
remove a distribuicao da lista; manter a agenda conserva os eventos no calendario.
O snapshot recebe registro de data, operador, comuns e contagem removida para
auditoria. A transacao verifica a versao do snapshot e de suas agendas; mudancas
concorrentes exigem recarregar antes de excluir. Nenhum dado real foi excluido
durante os testes de desenvolvimento.

Previa assinada, vinculada ao usuario e valida por 30 minutos; nao grava visitas.
A confirmacao reconsulta o recorte e verifica alteracoes em grupos, coordenadores,
cadastros e agenda. Se algo mudou, exige nova previa. A gravacao ocorre em uma
transacao no PostgreSQL e tem identificador idempotente: repetir a mesma
confirmacao apos perder conexao nao duplica visitas.

Confirmacoes por data possuem controle de concorrencia. Uma alteracao salva por
outro operador exige recarregar os grupos antes de sobrescrever os coordenadores.
Gravacoes sao auditadas e possuem identificacao do operador. Os dados sao
restritos no servidor ao municipio e as comuns autorizados; acesso local nao
administra o planejamento regional.

Quando uma nova distribuicao move visitas de um roteiro anterior, o anterior
fica marcado como historico substituido, inclusive na impressao. A lista de
familias e o coordenador originalmente emitidos permanecem preservados.

## Validacao local, sem consultas de producao

Na previa e na confirmacao, a ordem final considera uma matriz direcional de
distancias de carro do Google, por grupo, preservando manha antes de tarde.
A tarde continua a partir da ultima casa da manha. A matriz usa cache por
coordenadas, lotes de ate 100 elementos, no maximo 20 pontos por grupo e tres
consultas concorrentes; a busca tem prazo limitado para nao travar a pagina.
Grupos sem matriz completa conservam o calculo geografico e aparecem em um
aviso na previa, para conferir o Mapa Google antes de confirmar. Roteiros ja
salvos devem ser recalculados e confirmados para atualizar a ordem na agenda.

A migration `061_visitas_composicao_regional.sql` cadastra a composicao permanente
de Itapevi (20 pessoas, 23 funcoes e grupos A a O) a partir da imagem fornecida.
As tabelas de integrantes e funcoes sao separadas por municipio; uma pessoa pode
acumular funcoes sem duplicar seu cadastro. A comum de origem preserva o texto
do documento, sem inferir codigos BR por nome aproximado. As cores da imagem
nao geram presencas. Confirmacoes existentes por data permanecem preservadas.

`visitas_atribuir_integrante_por_data` permite que qualquer integrante ativo do
mesmo municipio assuma um grupo naquela data, sem substituir o titular no cadastro.
A operacao exige a versao anterior da participacao, registra auditoria e impede
confirmar a mesma pessoa em dois grupos na mesma data. Novos integrantes podem
receber a funcao `PARTICIPANTE` ou as demais funcoes
da composicao. As novas tabelas e funcoes sao restritas ao servidor/service_role.

```powershell
python manage.py test ColorAdminApp.tests.tests_regional_routes ColorAdminApp.tests.tests_route_quantity ColorAdminApp.tests.tests_visit_participation ColorAdminApp.tests.tests_route_integrity ColorAdminApp.tests.tests_linear_route --noinput
node scripts/validation/test_regional_routes_sql.mjs
node scripts/validation/test_regional_route_removal_sql.mjs
node scripts/validation/test_regional_composition_sql.mjs
python manage.py test ColorAdminApp.tests.tests_regional_route_roads --noinput
python scripts/validation/test_regional_routes_ui.py
python manage.py check
```

O teste SQL utiliza o PGlite ja disponivel em `tmp/ministry-sql/node_modules`.
O teste de interface utiliza Playwright e um dominio ficticio com todas as
respostas interceptadas: nao abre localhost e nao acessa Supabase, SAM ou dados
reais. As evidencias de interface e impressao ficam em
`relatorios/qa-roteiro-regional/`, fora do versionamento.
