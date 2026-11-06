# Instruções do projeto

## Identidade visual da CCB

- Nunca utilizar cruzes, símbolos religiosos com cruz ou ícones de edifícios/livros que contenham cruz em páginas, gráficos, relatórios ou materiais do projeto. A CCB não adota essa representação.
- Para comuns e localidades, utilizar símbolos neutros de localização, mapa ou edifício sem cruz. A regra também vale para componentes de demonstração visíveis no sistema.

## Servidor local e navegador

- Nunca abrir URLs `localhost` ou `127.0.0.1` no navegador, preview ou visualização interna do Codex.
- Quando for necessário abrir a aplicação local, usar sempre o navegador externo padrão do Windows.
- Considerar como URL padrão deste projeto `http://127.0.0.1:8000/`, salvo quando o servidor informar outra porta.
- Ao iniciar o servidor Django, abrir a URL externamente somente depois de confirmar que o servidor está respondendo.

## Relatórios PDF e Excel — leitura obrigatória

- Antes de criar, alterar ou revisar qualquer exportação PDF, Excel, CSV imprimível ou relatório para download, ler integralmente `docs/REPORT_EXPORT_STANDARD.md`.
- É proibido inventar outro cabeçalho ou identidade visual. Reutilizar exatamente o cabeçalho institucional, as cores, a hierarquia, os metadados e a composição definidos nesse padrão.
- Conferir a utilização da largura útil da página/planilha e evitar tabelas estreitas com grandes áreas vazias sem finalidade.
- Toda alteração de relatório deve incluir validação do arquivo gerado e comparação com as implementações de referência indicadas no padrão.


## Botões de cancelamento — regra geral

- Todo botão **Cancelar** deve usar fundo vermelho, texto branco de alto contraste e ícone de fechar (`fa-xmark`), inclusive em modais, formulários e confirmações dinâmicas.
- Usar as classes `btn btn-danger app-btn-cancel`. Nunca usar cinza claro, `btn-light`, `btn-white`, `btn-default` ou texto pálido para a ação Cancelar.
- Preservar foco visível de teclado, estado desabilitado e os eventos de cancelamento existentes. O ícone de fechar é funcional e neutro.


## Feedback de progresso e resultado

- Avisos de geração, exportação, sucesso e erro devem reutilizar o feedback centralizado do sistema, com fundo escurecido e desfocado. Nunca posicionar esses avisos como toast lateral.
- O feedback deve permanecer centralizado e visível acima de modais abertos, preservando o círculo de carregamento do botão e a confirmação apenas após a operação concluir.

## Acesso municipal ao APP_CARTAS

- A pasta Música é independente de Musicalização. Secretários se cadastram no sistema existente e aguardam aprovação na trilha de auditoria com nível Municipal, município confirmado e pasta Música.
- A liberação exclusiva Música permite gestão municipal em APP_CARTAS/admin e não autoriza o dashboard principal. Conferir escopo no servidor em toda consulta e alteração.

- No APP_CARTAS, reutilizar `AppFeedback.show` de `static/js/app-feedback.js` e seu CSS, com `toast: true` para sobrepor modais. Não recriar esse feedback com SweetAlert ou diálogo com botão Continuar. Sucesso fecha automaticamente no tempo padrão.
