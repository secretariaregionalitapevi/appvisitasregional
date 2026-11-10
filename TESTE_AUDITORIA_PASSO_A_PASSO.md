# 🧪 Guia de Teste - Dashboard de Auditoria Centralizada

## Pré-requisitos
- ✅ Python 3.8+
- ✅ Django rodando (com Supabase conectado)
- ✅ Navegador moderno (Chrome, Firefox, Edge, Safari)
- ✅ Conexão internet (para acessar Supabase e CDN de ícones)

---

## 📌 Teste 1: Iniciar Servidor Django

### Passo 1.1: Abrir Terminal/PowerShell
```powershell
# Navegue até a pasta do projeto
cd "C:\Users\Usuário\OneDrive\APLICATIVOS REGIONAL\APP_VISITAS_CCB"
```

### Passo 1.2: Iniciar o servidor
```bash
python manage.py runserver
```

**Esperado:** Você vê algo como:
```
Watching for file changes with StatReloader
Starting development server at http://127.0.0.1:8000/
```

Se aparecer erro, verifique:
- [ ] Todas as dependências instaladas (`pip install -r requirements.txt`)
- [ ] Variáveis de ambiente corretas (arquivo `.env`)
- [ ] Supabase acessível (testar conexão)

---

## 🌐 Teste 2: Acessar Dashboard no Navegador

### Passo 2.1: Abrir o Navegador Externo
**IMPORTANTE:** Abra o navegador externo do Windows, NÃO pelo VS Code preview.

1. Clique em Chrome/Firefox/Edge na barra de tarefas
2. Digite na barra de endereços:
```
http://127.0.0.1:8000/auditoria/centralizada/
```
3. Pressione Enter

### Passo 2.2: Verificar Carregamento da Página

**Esperado na tela:**
- ✅ Cabeçalho: "Auditoria Centralizada"
- ✅ 6 botões coloridos em uma linha:
  - "Musicalização Infantil" (azul/roxo)
  - "DARPE (Serviços)" (verde)
  - "Cartas de Exames" (laranja)
  - "Programa de Visitas" (marrom)
  - "Sistema de Acompanhamento Musical" (cinza)
  - "GEM (Educação Musical)" (amarelo)
- ✅ 4 cards de KPI abaixo (total eventos, operadores, período, escopo)
- ✅ Área de filtros com dropdowns
- ✅ Tabela vazia ou com dados (dependendo da base)

**Se não aparecer nada:**
1. Abra o console do navegador (F12)
2. Procure por erros em vermelho
3. Verifique a aba "Network" se a requisição `/auditoria/centralizada/` retornou 200 OK

---

## 🔘 Teste 3: Testar Seletor de Módulos

### Passo 3.1: Clicar no Botão de Musicalização
1. Clique no botão "Musicalização Infantil"
2. Aguarde 2-3 segundos

**Esperado:**
- ✅ Botão fica destacado (azul mais forte)
- ✅ Dropdown "Tipo de Recurso" muda para mostrar: "Aulas" e "Presenças"
- ✅ Tabela carrega com dados (ou "Sem dados se nenhuma aula foi criada")

### Passo 3.2: Clicar em Outro Módulo (ex: DARPE)
1. Clique no botão "DARPE (Serviços)"
2. Aguarde carregamento

**Esperado:**
- ✅ Botão de DARPE fica destacado
- ✅ Dropdown "Tipo de Recurso" agora mostra: "Atendimentos"
- ✅ Tabela limpa e carrega dados de atendimentos (ou vazio)

**Repita para cada módulo:**
- ✅ Cartas de Exames → Mostrar "Cartas"
- ✅ Programa de Visitas → Mostrar "Apontamentos de Visitas"
- ✅ SAM → Mostrar "Eventos de Auditoria"
- ✅ GEM → Mostrar "Aulas GEM"

---

## 🔍 Teste 4: Testar Filtros

### Passo 4.1: Filtragem por Tipo de Recurso
1. Mantenha "Musicalização Infantil" selecionada
2. Clique no dropdown "Tipo de Recurso"
3. Selecione "Aulas"
4. Clique "Buscar"

**Esperado:**
- ✅ Tabela mostra apenas dados de aulas
- ✅ Se trocar para "Presenças" e buscar, mostra apenas presenças

### Passo 4.2: Filtragem por Período
1. Altere "Últimos (dias)" de 30 para 7
2. Clique "Buscar"

**Esperado:**
- ✅ Tabela mostra apenas registros dos últimos 7 dias
- ✅ Se voltar para 30, mostra mais registros

### Passo 4.3: Filtragem por Operador
1. Digite um nome (ex: "João" ou seu nome)
2. Clique "Buscar"

**Esperado:**
- ✅ Tabela mostra apenas registros criados/editados por esse operador
- ✅ Se digitar nome que não existe, tabela fica vazia

### Passo 4.4: Filtro de Ação
1. Selecione "Ação" = "Criado"
2. Clique "Buscar"

**Esperado:**
- ✅ Tabela mostra apenas registros que foram criados
- ✅ Coluna "Quem Atualizou" fica vazia para esses registros

---

## 📊 Teste 5: Verificar Dados na Tabela

### Passo 5.1: Colunas da Tabela
Confirme que aparecem as colunas:
- [ ] **Recurso** (ex: "Aulas", "Atendimentos")
- [ ] **Quem Criou** (nome do operador)
- [ ] **Data/Hora de Criação** (formato: DD/MM/YYYY HH:MM)
- [ ] **Quem Atualizou** (vazio se nunca foi editado)
- [ ] **Data/Hora de Atualização** (vazio se nunca foi editado)

### Passo 5.2: Cores e Badges
Confirme que os badges de recurso têm cores diferentes:
- [ ] **Aulas** → cor X
- [ ] **Presenças** → cor Y
- [ ] **Atendimentos** → cor Z
- (cores diferentes para cada recurso)

### Passo 5.3: Formato de Data
Confirme que as datas estão em formato português:
- ✅ `31/12/2024 14:30:45` (DD/MM/YYYY HH:MM:SS)
- ❌ `2024-12-31 14:30:45` (YYYY-MM-DD HH:MM:SS) ← se vir assim, há bug

---

## 🔌 Teste 6: Testar API Direta (Avançado)

### Passo 6.1: Via Navegador
Na barra de endereços, acesse:
```
http://127.0.0.1:8000/api/auditoria/generic/?module=musicalizacao&resource=aulas&days=30&limit=10
```

**Esperado:** Você vê JSON com estrutura:
```json
{
  "results": {
    "aulas": [
      {
        "id": "...",
        "resource": "aulas",
        "description": "Atividades (Aulas)",
        "created_by": "João Silva",
        "created_at": "2024-12-31T14:30:45",
        "updated_by": null,
        "updated_at": null
      }
    ]
  },
  "module": {
    "name": "musicalizacao",
    "display_name": "Musicalização Infantil",
    "icon": "fa-music"
  },
  "scope": {
    "type": "REGIONAL",
    "municipio": null,
    "comum": null
  },
  "filters": {
    "resource": "aulas",
    "action": "",
    "actor": "",
    "days": 30,
    "limit": 10,
    "offset": 0
  }
}
```

### Passo 6.2: Testar Outros Módulos via API
```
# DARPE
http://127.0.0.1:8000/api/auditoria/generic/?module=darpe&days=30

# Cartas
http://127.0.0.1:8000/api/auditoria/generic/?module=cartas&days=60

# Visitas
http://127.0.0.1:8000/api/auditoria/generic/?module=visitas&days=30
```

**Esperado:** JSON válido para cada módulo

---

## ⚠️ Teste 7: Verificar Erros Comuns

### Cenário 1: Acesso Negado
Se ver mensagem "Acesso negado a este módulo"
- [ ] Seu usuário tem permissão para o módulo?
- [ ] Verifique em `admin > Acesso do Usuário` sua configuração de módulos

### Cenário 2: Nenhum Dado Aparece
Se tabela fica sempre vazia:
- [ ] Há dados no Supabase para esse módulo? (verificar em Supabase Console)
- [ ] Os nomes de tabelas estão corretos? (pode ser que sejam diferentes em produção)
- [ ] Tente aumentar o período: "Últimos 90 dias"

### Cenário 3: Erro 404 na API
Se receber `{"error": "Módulo de auditoria não encontrado"}`
- [ ] O nome do módulo está correto? (tente `?module=musicalizacao`)
- [ ] Verifique em `audit_generic.py` se o módulo existe em `AUDIT_MODULES`

### Cenário 4: Erro 500
Se receber erro interno do servidor:
- [ ] Abra o terminal Django e veja a mensagem de erro
- [ ] Procure por `Traceback` e veja qual linha falhou
- [ ] Pode ser problema de conexão com Supabase

---

## 📋 Checklist Final de Validação

### ✅ Funcionalidade Básica
- [ ] Dashboard carrega sem erros
- [ ] 6 módulos aparecem com nomes corretos
- [ ] Cada módulo mostra seus recursos específicos
- [ ] Tabela mostra dados (ou vazio se não houver dados)

### ✅ Filtros
- [ ] Filtro por recurso funciona
- [ ] Filtro por período funciona
- [ ] Filtro por operador funciona
- [ ] Filtro por ação funciona
- [ ] Botão "Buscar" atualiza dados

### ✅ Dados Corretos
- [ ] Datas em formato pt-BR (DD/MM/YYYY)
- [ ] Nomes de operadores aparecem corretamente
- [ ] Recursos mostram badges coloridas
- [ ] Ordenação por data (mais recente primeiro)

### ✅ Acesso
- [ ] Escopo aparece corretamente (Regional/Municipal/Local)
- [ ] Dados respeitam escopo do usuário
- [ ] Não há acesso a dados de outro escopo

### ✅ API
- [ ] `/api/auditoria/generic/` retorna JSON válido
- [ ] Parâmetros funcionam: `module`, `resource`, `days`, `limit`, `offset`
- [ ] Cada módulo tem sua própria configuração

---

## 🚀 Próximo Passo Após Validação

Se tudo passou no checklist:
1. Commit as mudanças (já feito: `eb42ac1`)
2. Faça deploy: `git push origin main`
3. Teste em produção
4. Avise para usar o novo dashboard em `/auditoria/centralizada/`

---

## 📞 Troubleshooting

| Problema | Solução |
|----------|---------|
| "Página em branco" | F12 → Console → procure por erros vermelhos |
| "Sem dados" mas deveria ter | Verifique período (tente 90 dias) |
| Botões de módulo não reagem | Abra Console (F12) e veja erros JavaScript |
| Erro "CORS" | Problema de servidor - reinicie Django |
| Data errada | Verifique formato em `auditoria_centralizada.html` linha ~380 |
| Supabase timeout | Verifique conexão internet e credenciais |

---

**Boa sorte com os testes! 🎉**
