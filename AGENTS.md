# Instruções do projeto

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
