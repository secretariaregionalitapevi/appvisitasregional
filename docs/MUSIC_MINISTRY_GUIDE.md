# Acompanhamento do Ministério da Música

Página: **Música > Acompanhamento do Ministério**, em `/musica/ministerio/`.

## Ativação

Aplicar `scripts/migrations/036_musica_ministerio_acompanhamento.sql` no SQL Editor do Supabase.
É uma migração aditiva: não modifica os encontros ou as presenças antigas. Todas as novas tabelas
têm RLS habilitado e acesso restrito ao serviço do servidor. O aplicativo reaplica as permissões
territoriais antes de montar consultas e exportações.

Sem a migração, a página permite consultar o histórico nominal dos ensaios/RTs existentes e informa
que os novos cadastros ainda não podem ser gravados. Não usa armazenamento temporário como banco de produção.

## Consulta e exportação

- A tela abre nos encarregados locais; outros cargos e todos os cargos são opções do filtro.
- Selecionar nenhum município consulta a Regional inteira, dentro do escopo do usuário.
- Selecionar um ou vários municípios limita as comuns, as pessoas e os arquivos exportados.
- Os filtros de ano, cargo, tipo de evento, comum e pesquisa também valem para Excel e PDF.
- Abrir o nome mostra cada encontro e a situação individual.
- A fração representa **presenças / encontros conferidos**, não arquivos carregados.
- Presença, justificativa e ausência conferida entram no denominador.
- Conferência pendente, sem dados e não aplicável ficam fora do denominador.
- Ausência total entre encontros conferidos aparece em vermelho. Sem conferência não aparece como 0/0.

Os documentos repetem o cabeçalho institucional de `docs/REPORT_EXPORT_STANDARD.md`, têm um resumo
individual e o histórico detalhado do mesmo recorte. O nome é curto: `Ministerio_Regional_2026.pdf`
ou `Ministerio_Selecao_2026.xlsx`. Datas no documento usam `dd/mm/AAAA` e emissões `dd/mm/AAAA HH:mm`.

## Reunião do Brás em 06/10/2026

1. Abrir **Novo encontro / Importar lista**.
2. Selecionar o Excel nominal e clicar em **Conferir planilha**.
3. Confirmar a data sugerida, título, tipo **Reunião do Ministério da Música**, modalidade presencial e local Brás.
4. Conferir os municípios e cargos abrangidos. A prévia sugere os encontrados na lista; isso não comprova
   que outros municípios estejam ausentes. A administração e o município da comum são campos distintos.
5. Revisar o vínculo de cada linha. A sugestão exige nome e comum compatíveis ou ID de origem.
   Nomes ambíguos não recebem associação automática. É possível manter uma identidade própria da lista,
   que será reutilizável nos próximos encontros. Comuns não reconhecidas exigem seleção do cadastro.
6. Os encarregados locais cadastrados do público selecionado que não constam na lista ficam como
   **Não participou**, conforme a regra definida pela administração. Marcar lista completa aplica essa
   conclusão também aos demais cargos. A ausência não significa automaticamente “não justificou”.
7. Confirmar a conferência e salvar. A operação é transacional e registra autoria.

O mesmo arquivo, identificado por SHA-256, não cria outro encontro. Outro arquivo para um encontro já
importado é recusado pelo identificador data/tipo/modalidade/título; correções individuais usam **Conferir**.
Uma atualização integral da lista de um evento já importado exige um fluxo específico futuro.

## Encontro ainda sem lista

Cadastrar data, público previsto, modalidade e local sem anexar Excel. As pessoas ficam como **Sem dados**.
Quando a lista chegar, usar **Carregar lista deste encontro**, preservando data e público do registro original.
A reunião online é um encontro distinto da presencial, da mesma categoria, com data e modalidade próprias.
Não cadastrar uma data estimada como se fosse confirmada.

## Identidade e histórico

IDs SAM e da irmandade são preservados como aliases quando a correspondência entre os cadastros é única
por nome, comum e cargo. Homônimos com IDs diferentes na mesma fonte permanecem separados.
O número da linha da planilha é uma referência da fonte, não um identificador universal da pessoa.

Os encontros novos congelam nome, comum, município e cargos do público conferido. O cadastro atual
apenas sugere o público; o operador deve conferir a situação na data histórica. Cadastros preservados
de listas antigas não geram ausência em novos encontros sem conferência. Em RTs por família,
cadastros de outra família não entram automaticamente no público; família desconhecida fica pendente.

Nos ensaios/RTs antigos, uma presença nominal inequívoca confirma a pessoa. Para encarregados locais
cadastrados, não constar na lista carregada de um encontro aplicável significa **Não participou**.
Encontros sem lista continuam como **Sem dados**. A ausência não vira NJ individual.
A administração regional pode conferir cada pessoa, com justificativa quando aplicável.
Uma presença nominal positiva precisa ser corrigida na fonte antes de receber outra situação.
Todas as conferências têm auditoria e controle de versão para impedir sobrescrita por outra sessão.

## Validação

```text
python manage.py test ColorAdminApp.tests.tests_music_ministry --noinput
node scripts/test_music_ministry.cjs
python manage.py check
```

O script `scripts/validation/validate_music_ministry.py`, executado pelo shell Django,
gera arquivos de validação com dados fictícios para a Regional e para dois municípios.
As imagens e documentos ficam em `tmp/pdfs/ministerio/`.
