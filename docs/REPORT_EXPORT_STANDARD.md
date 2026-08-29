# Padrão obrigatório para relatórios PDF e Excel

Este arquivo deve ser lido integralmente **antes** de montar ou alterar qualquer PDF, Excel, CSV imprimível ou relatório exportável deste projeto.

## Referências canônicas

- PDF: função `generateStandardPdf` em `ColorAdminApp/templates/pages/musicalizacao.html`.
- Excel: função `export_report` em `ColorAdminApp/gem_sync_admin.py`.
- Identidade institucional: `CONGREGAÇÃO CRISTÃ NO BRASIL` e `Regional Itapevi - São Paulo`.

Não criar uma identidade alternativa. Se um relatório antigo divergir deste documento, adequá-lo ao padrão canônico quando ele for alterado.

## Cabeçalho obrigatório do PDF

Usar cabeçalho em três colunas:

1. Coluna esquerda vazia, com a mesma largura da coluna de metadados.
2. Coluna central, centralizada, nesta ordem:
   - `CONGREGAÇÃO CRISTÃ NO BRASIL` — 15 pt, negrito;
   - `Regional Itapevi - São Paulo` — 9 pt;
   - nome do módulo — 11–12 pt, negrito, azul institucional;
   - nome do relatório — 9 pt.
3. Coluna direita com página, emissão, recorte/localidade, usuário responsável e data/hora.

Para A4 paisagem, usar como base:

- margens `[28, 100, 28, 34]`;
- colunas laterais com 190–220 pt;
- azul institucional `#1e4b7a`;
- azul claro de apoio `#eaf2f8` para faixas de recorte e resumos.

O rodapé deve informar o módulo/recorte e repetir a paginação ou identificação institucional.

## Aproveitamento da página

- Tabelas devem ocupar a largura útil da página.
- Usar ao menos uma coluna com largura `*` quando a soma de larguras fixas deixar espaço ocioso.
- Não aceitar tabela concentrada à esquerda com grande vazio à direita.
- Escolher retrato ou paisagem conforme o número e o conteúdo das colunas, não por conveniência.
- Antes de concluir, gerar o arquivo e inspecionar cabeçalho, quebra de páginas, alinhamento, legibilidade e áreas vazias.

## Estrutura visual da tabela PDF

- Incluir faixa de contexto/recorte acima da tabela quando aplicável.
- Cabeçalho da tabela com fundo azul institucional, texto branco, negrito e centralizado.
- Alternar linhas brancas e `#f4f6f8`.
- Usar bordas discretas `#c8d1da`/`#d8dee5`.
- Repetir o cabeçalho da tabela em novas páginas (`headerRows: 1`).
- Não quebrar uma linha entre páginas (`dontBreakRows: true`).

## Cabeçalho e acabamento do Excel

- Mesclar a primeira linha por toda a largura do relatório para `CONGREGAÇÃO CRISTÃ NO BRASIL`.
- Usar a segunda linha para `Regional Itapevi - São Paulo` e identificação do módulo.
- Usar a terceira/quarta linha para título, recorte, emissão e responsável.
- Aplicar azul institucional `#1e4b7a` tanto no cabeçalho principal quanto nos títulos das colunas.
- Não usar verde nos cabeçalhos de tabelas exportadas; todos os relatórios devem preservar a mesma estética azul.
- Congelar o cabeçalho da tabela, ativar filtro, ocultar gridlines e ajustar todas as larguras.
- Configurar impressão em orientação adequada, `fitToWidth = 1` e repetir o padrão em todas as abas relevantes.

## Validação obrigatória

Antes de entregar uma alteração:

1. Gerar ao menos um arquivo real ou um arquivo construído por teste automatizado.
2. Confirmar que o cabeçalho segue a referência canônica.
3. Confirmar que nenhuma coluna foi cortada e que a tabela usa a largura útil.
4. Confirmar nomes do arquivo, paginação, data/hora, responsável e recorte.
5. Executar os testes relacionados e `python manage.py check`.

## Formato obrigatório de datas

- Datas de execução e logs devem usar exatamente `dd/mm/AAAA HH:mm`.
- Datas pedagógicas de MSA, Método, Hinário, Provas, Escalas e Atividades devem usar `dd/mm/AAAA`, sem horário artificial.
- O banco deve preservar os tipos `date` e `timestamp`; a formatação acontece somente na apresentação/exportação.
- Não exportar datas ISO (`AAAA-mm-dd`) nem depender da formatação automática do Excel ou do navegador.
- Em nomes de arquivo, nos quais `/` e `:` não são permitidos, usar o equivalente seguro `dd-mm-AAAA_HH-mm`.
