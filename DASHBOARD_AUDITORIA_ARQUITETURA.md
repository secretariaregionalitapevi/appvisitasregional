# Arquitetura - Dashboard de Auditoria

## Componentes

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         NAVEGAÇÃO DO PROJETO                           │
│  /musicalizacao/              (dashboard principal)                     │
│  /musicalizacao/aulas/        (gerenciar atividades)                    │
│  /musicalizacao/criancas/     (cadastro de crianças)                    │
│  /musicalizacao/instrutores/  (cadastro de instrutores)                 │
│  /musicalizacao/polos/        (gerenciar polos)                         │
│  /musicalizacao/historico/    (aulas passadas)                          │
│  /musicalizacao/auditoria/    ← ★ NOVO - Dashboard de auditoria         │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┘
                    │
        ┌───────────▼──────────────┐
        │  musicalizacao.page()    │
        │  (ColorAdminApp/modules/ │
        │   musicalizacao.py)      │
        └───────────┬──────────────┘
                    │
        ┌───────────▼──────────────────────────┐
        │ if section == 'auditoria':           │
        │   render('musicalizacao_auditoria.   │
        │           html')                     │
        │ else:                                │
        │   render('musicalizacao.html')       │
        └───────────┬──────────────────────────┘
                    │
        ┌───────────▼────────────────────────────────────────┐
        │ musicalizacao_auditoria.html (template)            │
        │ ├─ KPIs (4 cards premium)                          │
        │ ├─ Filtros (resource, action, actor, days)         │
        │ ├─ Tabela de eventos (aulas + presenças)           │
        │ └─ JavaScript fetch → /musicalizacao/api/auditoria/│
        └───────────┬────────────────────────────────────────┘
                    │
                    │ fetch GET /musicalizacao/api/auditoria/?filters
                    │
        ┌───────────▼────────────────────────────────────────┐
        │ api_audit(request)                                 │
        │ (ColorAdminApp/modules/musicalizacao.py)           │
        │                                                    │
        │ 1. Valida acesso: can_open_module()               │
        │ 2. Extrai filtros: resource, action, actor, days  │
        │ 3. Calcula data limite (últimos N dias)           │
        │ 4. Consulta aulas em Supabase REST API            │
        │ 5. Consulta presenças em Supabase REST API        │
        │ 6. Filtra por escopo (municipal/local)            │
        │ 7. Filtra por operador (actor)                    │
        │ 8. Retorna JSON com resultados                    │
        └───────────┬────────────────────────────────────────┘
                    │
            ┌───────▼────────┐
            │  Supabase API  │
            │  (REST v1)     │
            │                │
            │ GET/rest/v1/   │
            │  musicalizacao │
            │  _aulas        │
            │                │
            │ GET/rest/v1/   │
            │  musicalizacao │
            │  _presenca     │
            └───────┬────────┘
                    │
        ┌───────────▼─────────────────────────────────┐
        │  PostgreSQL (Banco de Dados Remoto)         │
        │                                             │
        │ musicalizacao_aulas:                        │
        │  - id, data_aula, polo, cidade              │
        │  - created_by_user_id, created_by_name, ... │
        │  - updated_by_user_id, updated_by_name, ... │
        │                                             │
        │ musicalizacao_presenca:                     │
        │  - id, aula_id, aluno_id                    │
        │  - created_by_user_id, created_by_name, ... │
        └──────────────────────────────────────────────┘
```

## Fluxo de Dados

```
┌──────────────────────────────────────────────────────────────────┐
│                    USUÁRIO ABRE DASHBOARD                        │
│          GET /musicalizacao/auditoria/                           │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│              DJANGO RENDERIZA TEMPLATE HTML                      │
│           (musicalizacao_auditoria.html)                         │
│   - Exibe KPIs (carregando...)                                   │
│   - Exibe filtros vazios                                         │
│   - Spinner de carregamento                                      │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│        JAVASCRIPT EXECUTA loadAudit()                            │
│   Fetch: GET /musicalizacao/api/auditoria/?                      │
│           resource=&action=&actor=&days=30&limit=50&offset=0     │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│          API VALIDA E PROCESSA REQUISIÇÃO                        │
│                                                                  │
│  1. Verifica: can_open_module(request) → 403 ou continua         │
│  2. Extrai scope: user_scope(request)                            │
│  3. Prepara data_limite = now - 30 dias                          │
│  4. Monta query para Supabase aulas:                             │
│     - select: campos com auditoria                               │
│     - order: created_at.desc                                    │
│     - filter: created_at >= data_limite                          │
│     - filter: created_by_user_id IS NOT NULL (se action='created')│
│     - filter: updated_by_user_id IS NOT NULL (se action='updated')│
│  5. Monta query para Supabase presenças (similar)               │
│  6. Ambas requisições em paralelo (performance)                 │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│        SUPABASE RETORNA DADOS (JSON)                             │
│                                                                  │
│  {                                                               │
│    "results": {                                                  │
│      "aulas": [                                                  │
│        {                                                         │
│          "id": "abc123",                                         │
│          "resource": "aulas",                                    │
│          "description": "Aula em 2024-11-28 - Polo ABC (São...  │
│          "created_by": "João Silva",                             │
│          "created_at": "2024-11-28T10:30:00Z",                   │
│          "updated_by": null,                                     │
│          "updated_at": null                                      │
│        },                                                        │
│        ...                                                       │
│      ],                                                          │
│      "presencas": [...]                                          │
│    },                                                            │
│    "scope": { "level": "regional", "municipio": null, ... },     │
│    "filters": { ... }                                            │
│  }                                                               │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│      JAVASCRIPT PROCESSA RESPOSTA                                │
│                                                                  │
│  1. Salva em auditState.data                                    │
│  2. Calcula KPIs:                                                │
│     - Total de aulas                                             │
│     - Total de presenças                                         │
│     - Unique operators (created_by + updated_by)                 │
│     - Total de eventos                                           │
│  3. Renderiza tabela com eventos (mais recente primeiro)         │
│  4. Formatação de datas em pt-BR                                 │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│      DASHBOARD EXIBE DADOS AO USUÁRIO                            │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Auditoria de Musicalização                             │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ [123 Atividades] [45 Presenças] [12 Operadores] [168...]│   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ Filtros: [Tipo▼] [Ação▼] [Operador_____] [Período▼]   │   │
│  │ [Filtrar] [Limpar]                                      │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ Tipo  │ Descrição        │ Criado por │ Data    │ ...  │   │
│  │────────────────────────────────────────────────────────│   │
│  │ aulas │ Aula em 28-11... │ João Silva │ 28/11/24│ ...  │   │
│  │presença│ Presença lancada│ Maria Oliveira│ 27/11/24│ ...  │   │
│  │ aulas │ Aula em 27-11... │ João Silva │ 27/11/24│ ...  │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

## Validações de Segurança

```
┌─────────────────────────────────────────────────────────┐
│  TODAS AS REQUISIÇÕES PASSAM POR:                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. can_open_module(request)                            │
│     ├─ Verifica: request.session['user_profile']        │
│     └─ Confere: MODULE_MUSICALIZACAO e permissões       │
│        └─ Se falhar: Return 403 Forbidden               │
│                                                         │
│  2. user_scope(request)                                 │
│     ├─ Nível: "regional" | "municipal" | "local"        │
│     ├─ Município: null | nome (se scoped)               │
│     └─ Comum: null | polo (se coordenador)              │
│                                                         │
│  3. Filtros de Segurança                               │
│     ├─ Aulas: can_access(scope, location)              │
│     │         ├─ Verifica cidade (municipal/local)     │
│     │         └─ Verifica polo (coordenador)           │
│     │                                                  │
│     └─ Presenças: Idem                                 │
│                                                         │
│  Resultado: Apenas registros do escopo são retornados │
└─────────────────────────────────────────────────────────┘
```

## Estrutura de Resposta da API

```json
{
  "results": {
    "aulas": [
      {
        "resource": "aulas",
        "id": "uuid-abc123",
        "description": "Aula em 28/11/2024 - Polo Vida (Itapevi)",
        "created_by": "João Silva Santos",
        "created_at": "2024-11-28T10:30:45Z",
        "updated_by": "Maria Oliveira",
        "updated_at": "2024-11-28T15:22:10Z"
      }
    ],
    "presencas": [
      {
        "resource": "presencas",
        "id": "uuid-def456",
        "description": "Presença lançada (aula: abc123)",
        "created_by": "João Silva Santos",
        "created_at": "2024-11-28T11:00:00Z"
      }
    ]
  },
  "scope": {
    "level": "municipal",
    "municipio": "Itapevi",
    "comum": null
  },
  "filters": {
    "resource": "aulas",
    "action": "created",
    "actor": "João",
    "days": 30,
    "limit": 50,
    "offset": 0
  }
}
```

## Interações do Usuário

```
┌─────────────────────────────────────────────┐
│  Usuário clica em "Filtrar"                 │
└──────────────────┬──────────────────────────┘
                   │
     ┌─────────────▼──────────────┐
     │ Lê valores dos inputs:     │
     │ - filter-resource.value    │
     │ - filter-action.value      │
     │ - filter-actor.value       │
     │ - filter-days.value        │
     └─────────────┬──────────────┘
                   │
     ┌─────────────▼──────────────────────┐
     │ Atualiza auditState.filters        │
     │ Reset offset = 0                   │
     └─────────────┬──────────────────────┘
                   │
     ┌─────────────▼──────────────────────┐
     │ Chama loadAudit()                  │
     └─────────────┬──────────────────────┘
                   │
     ┌─────────────▼──────────────────────┐
     │ Monta URLSearchParams (filters)    │
     │ Fetch GET /api/auditoria/?params   │
     └──────────────────────────────────┘
```

---

**Diagrama atualizado**: 2024-11-28  
**Componentes**: 5 (3 routes, 1 template, 1 função API)  
**Dependências Externas**: Supabase REST API (já em uso)
