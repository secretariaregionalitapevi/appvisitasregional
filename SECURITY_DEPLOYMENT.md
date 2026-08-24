# Implantação segura na Vercel

Este projeto está vinculado na Vercel como `appvisitasregional`.

## 1. Abrir as variáveis do projeto

1. Entre em https://vercel.com/dashboard.
2. Abra o projeto **appvisitasregional**.
3. Acesse **Settings**.
4. No menu lateral, abra **Environment Variables**.
5. Cadastre cada variável da tabela abaixo separadamente.

Não coloque aspas ao redor dos valores e não adicione espaços antes ou depois.

## 2. Variáveis obrigatórias

| Variável | Ambiente | Valor/origem |
|---|---|---|
| `DJANGO_SECRET_KEY` | Production | Chave aleatória nova, com pelo menos 50 caracteres. Nunca reutilize senha pessoal. |
| `DJANGO_DEBUG` | Production | `False` |
| `DJANGO_ENV` | Production | `production` |
| `DJANGO_ALLOWED_HOSTS` | Production | `appvisitasregional.vercel.app` e eventuais domínios próprios, separados por vírgula. Não use `*`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Production | `https://appvisitasregional.vercel.app` e eventuais origens HTTPS próprias, separadas por vírgula. |
| `SUPABASE_URL` | Production | URL do projeto, encontrada no painel do Supabase. |
| `SUPABASE_ANON_KEY` | Production | Chave pública `anon`/publishable do Supabase. |
| `SUPABASE_SERVICE_ROLE_KEY` | Production | Chave secreta `service_role`/secret do Supabase. Marque como sensível. |
| `GOOGLE_MAPS_API_KEY` | Production | Chave do Google Maps usada pelo mapa e geocodificação. |

A Vercel fornece `VERCEL_ENV` automaticamente; não é necessário cadastrá-la.

### Gerar a chave secreta do Django

Execute localmente no PowerShell:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copie o resultado diretamente para `DJANGO_SECRET_KEY` na Vercel. Não salve o
resultado no Git, em mensagens ou em documentos compartilhados.

## 3. Localizar as chaves no Supabase

1. Abra o projeto correto em https://supabase.com/dashboard.
2. Entre em **Project Settings** e depois **API** (em algumas versões do painel,
   use **Connect** ou **API Keys**).
3. Copie a URL do projeto para `SUPABASE_URL`.
4. Copie a chave pública `anon`/publishable para `SUPABASE_ANON_KEY`.
5. Copie a chave secreta `service_role`/secret para
   `SUPABASE_SERVICE_ROLE_KEY`.

Não troque as duas chaves. A `service_role` concede acesso administrativo e
nunca pode aparecer em HTML, JavaScript, captura de tela ou repositório.

## 4. Production, Preview e Development

Para o primeiro deployment seguro, selecione **Production** para todas as
variáveis acima. Evite fornecer as chaves do banco de produção para Preview ou
Development, pois um deployment de teste passaria a operar nos dados reais.

Se Preview for necessário, o recomendado é criar outro projeto Supabase e
cadastrar no ambiente Preview as chaves desse banco separado. O domínio Preview
também precisa entrar em `DJANGO_ALLOWED_HOSTS` e, com `https://`, em
`DJANGO_CSRF_TRUSTED_ORIGINS`.

## 5. Aplicar a proteção no Supabase

Antes de liberar a nova versão:

1. No Supabase, abra **SQL Editor**.
2. Crie uma nova consulta.
3. Cole integralmente o conteúdo de
   `scripts/migrations/009_security_hardening_rls_storage.sql` e execute.
4. Em uma nova consulta, cole integralmente o conteúdo de
   `scripts/migrations/010_secure_shared_user_approval_rpc.sql` e execute.
5. Em uma nova consulta, cole integralmente o conteúdo de
   `scripts/migrations/011_user_module_access.sql` e execute.
6. Revise se o projeto selecionado é o de produção.

A migração habilita RLS, bloqueia acesso direto às tabelas sensíveis, torna o
bucket de fotos privado, limita arquivos e cria o controle compartilhado de
tentativas de login. Sem essa migração, o login em produção falhará de forma
segura, pois o limitador obrigatório ainda não existirá.

A migração `010` restaura a liberação de usuários do projeto `_GLOBAL`
por uma RPC administrativa validada, sem devolver ao navegador permissão
direta para alterar `profiles`.

A migração `011` separa o alcance territorial (global, regional, municipal e
local) da autorização funcional (Visitas e Musicalização). Concessões de uma
segunda pasta ficam restritas ao backend global e registradas na auditoria.

## 6. Publicar as novas variáveis

Variáveis adicionadas ou alteradas não modificam deployments antigos.

1. Abra a aba **Deployments** do projeto na Vercel.
2. No deployment mais recente, abra o menu de três pontos.
3. Clique em **Redeploy** e confirme.
4. Depois do deployment, teste login, calendário, cadastro e carregamento de
   fotos.

Se a aplicação informar que `DJANGO_SECRET_KEY` não está configurada, confirme
se a variável foi criada para **Production** e se o deployment também é de
produção.

## 7. Validação antes da liberação

Execute localmente:

```text
python manage.py test ColorAdminApp.tests
python -m pip_audit -r requirements.txt
```

O comando abaixo deve ser executado com as variáveis de produção disponíveis no
ambiente em que ele for rodado:

```text
python manage.py check --deploy
```

Por fim, entre com uma conta local e confirme que ela não consegue consultar,
alterar ou excluir dados de outra comum.
