# Genie Chatbot App

Interface de chat que se integra a múltiplas salas Genie para consultas em linguagem natural sobre dados.

<img width="1719" height="886" alt="Screenshot 2026-05-15 at 13 17 40" src="https://github.com/user-attachments/assets/a16eb5d8-d572-497c-ae68-c627e5333ee6" />

<img width="1717" height="881" alt="Screenshot 2026-05-15 at 13 19 38" src="https://github.com/user-attachments/assets/3f451f23-3d87-4a41-804c-1dc3bdbd7a69" />

<img width="1719" height="878" alt="Screenshot 2026-05-15 at 13 20 37" src="https://github.com/user-attachments/assets/090930bf-e852-4762-9389-39041380df36" />


## Funcionalidades

- **Chat com Genie**: Faça perguntas em linguagem natural e receba respostas com dados
- **Visualização de Dados**: Tabelas e gráficos automáticos baseados nos resultados
- **Múltiplos Genie Spaces**: Selecione entre diferentes Genie Spaces disponíveis
- **Histórico de Conversas**: Persistência opcional com Lakebase ou em memória
- **Autenticação OAuth**: On-behalf-of-user para respeitar permissões do usuário
- **Totalmente Configurável**: Cores, nome, descrição e comportamento via `settings.py`

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    Databricks App                           │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │   Frontend  │───▶│   FastAPI   │───▶│   Genie API     │ │
│  │   (HTML/JS) │    │   Backend   │    │   (Databricks)  │ │
│  └─────────────┘    └──────┬──────┘    └─────────────────┘ │
│                            │                                │
│                            ▼                                │
│                    ┌─────────────┐                         │
│                    │  Lakebase   │  (opcional)             │
│                    │  (Postgres) │                         │
│                    └─────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

## Estrutura de Arquivos

```
genie-chatbot-app/
├── app.py              # Aplicação FastAPI principal
├── app.yaml            # Configuração do Databricks App
├── settings.py         # ⭐ ARQUIVO DE CONFIGURAÇÃO
├── requirements.txt    # Dependências Python
└── server/
    ├── __init__.py
    ├── config.py       # Configuração de autenticação
    ├── database.py     # Conexão com Lakebase
    └── genie.py        # Integração com Genie API
```

## Configuração

Toda a personalização é feita no arquivo `settings.py`:

### Identidade Visual

```python
# Nome e descrição exibidos no app
APP_NAME = "Genie Chatbot"
APP_DESCRIPTION = "Assistente de dados powered by Databricks Genie"

# Badge "Powered by" no header (deixe "" para ocultar)
POWERED_BY = "Databricks"

# Cores da marca (formato hexadecimal)
BRAND_COLORS = {
    "primary": "#002855",      # Cor principal (header, botões)
    "secondary": "#426ca9",    # Cor secundária (elementos de destaque)
    "accent": "#28c18d",       # Cor de acento (sucesso, ações)
    "background": "#f5f5f5",   # Cor de fundo
    "light": "#e8f0f8",        # Cor clara (badges, backgrounds suaves)
}
```

### Persistência de Histórico

```python
# True = usa Lakebase (PostgreSQL) para salvar conversas
# False = usa memória (conversas perdidas ao reiniciar)
ENABLE_HISTORY_PERSISTENCE = True

# Configuração do Lakebase (somente se ENABLE_HISTORY_PERSISTENCE = True)
LAKEBASE_CONFIG = {
    "project": "genie-chatbot-db",      # Nome do projeto Lakebase
    "branch": "production",              # Branch (geralmente "production")
    "host": "ep-xxx.database.us-east-1.cloud.databricks.com",  # Endpoint
    "database": "databricks_postgres",   # Nome do banco
}
```

### Genie Spaces

```python
# Genie Spaces padrão (fallback se a API falhar)
# Deixe vazio [] para usar apenas os spaces que o usuário tem acesso
DEFAULT_GENIE_SPACES = [
    # {"space_id": "abc123", "title": "Meu Space", "description": "Descrição"}
]

# Timeout para chamadas ao Genie (segundos)
GENIE_TIMEOUT_SECONDS = 120
```

### Limites de Exibição

```python
# Máximo de linhas exibidas na tabela
MAX_TABLE_ROWS = 20

# Máximo de pontos no gráfico
MAX_CHART_ROWS = 50
```

## Como os Genie Spaces Funcionam

1. **Carregamento Dinâmico**: Quando o usuário acessa o app, a API `GET /api/2.0/genie/spaces` é chamada com o token OAuth do usuário
2. **Permissões Respeitadas**: Apenas os Genie Spaces que o usuário tem acesso são exibidos
3. **Fallback**: Se a API falhar, usa `DEFAULT_GENIE_SPACES` do `settings.py`

## Deploy

### Pré-requisitos

1. Databricks CLI configurado
2. Workspace com Databricks Apps habilitado
3. (Opcional) Lakebase para persistência de histórico

### Passos

1. **Configurar settings.py** com suas preferências

2. **Upload dos arquivos**:
```bash
databricks workspace import-dir . /Workspace/Users/seu-email/genie-chatbot-app --profile seu-profile
```

3. **Criar o app** (primeira vez):
```bash
databricks apps create genie-chatbot --profile seu-profile
```

4. **Deploy**:
```bash
databricks apps deploy genie-chatbot \
  --source-code-path /Workspace/Users/seu-email/genie-chatbot-app \
  --profile seu-profile
```

5. **Adicionar recursos** (via UI do Databricks):
   - Vá em Compute > Apps > genie-chatbot > Settings
   - Adicione recurso "SQL Warehouse" se necessário
   - Adicione recurso "Database" (Lakebase) se usando persistência

### Configurar Lakebase (Opcional)

Se `ENABLE_HISTORY_PERSISTENCE = True`:

1. Crie um projeto Lakebase no workspace
2. Atualize `LAKEBASE_CONFIG` em `settings.py`
3. Adicione o recurso Database no app
4. Redeploy

## Endpoints da API

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/` | GET | Frontend da aplicação |
| `/api/user` | GET | Informações do usuário logado |
| `/api/spaces` | GET | Lista Genie Spaces disponíveis |
| `/api/ask` | POST | Envia pergunta para o Genie |
| `/api/conversations` | GET | Lista conversas do usuário |
| `/api/conversations` | POST | Cria nova conversa |
| `/api/conversations/{key}` | GET | Detalhes de uma conversa |
| `/api/conversations/{key}` | DELETE | Deleta uma conversa |

## Autenticação

O app usa **On-behalf-of-user OAuth**:

- O token OAuth do usuário é passado via header `x-forwarded-access-token`
- Todas as chamadas ao Genie e Lakebase usam as permissões do usuário
- Não requer configuração adicional de credenciais

## Personalização para Clientes

Para criar uma versão personalizada para um cliente:

1. **Clone o repositório**

2. **Edite `settings.py`**:
   ```python
   APP_NAME = "Assistente de Dados - Cliente XYZ"
   APP_DESCRIPTION = "Consulte seus dados com linguagem natural"
   POWERED_BY = "Cliente XYZ"  # ou "" para ocultar

   BRAND_COLORS = {
       "primary": "#1a365d",    # Cor do cliente
       "secondary": "#2c5282",
       "accent": "#38a169",
       "background": "#f7fafc",
       "light": "#ebf8ff",
   }
   ```

3. **Configure Lakebase** (se necessário) ou desabilite:
   ```python
   ENABLE_HISTORY_PERSISTENCE = False  # Sem banco de dados
   ```

4. **Deploy** no workspace do cliente

## Troubleshooting

### App não carrega Genie Spaces

- Verifique se o usuário tem acesso a pelo menos um Genie Space
- Configure `DEFAULT_GENIE_SPACES` como fallback

### Erro de conexão com Lakebase

- Verifique se o recurso Database foi adicionado ao app
- Confirme se `LAKEBASE_CONFIG` está correto
- Ou desabilite: `ENABLE_HISTORY_PERSISTENCE = False`

### Gráficos não aparecem

- Verifique se a query retorna dados numéricos
- O app detecta automaticamente colunas numéricas para visualização

## Tecnologias

- **Backend**: FastAPI (Python)
- **Frontend**: HTML + TailwindCSS + Alpine.js
- **Gráficos**: Chart.js
- **Banco de Dados**: Lakebase (PostgreSQL gerenciado)
- **API**: Databricks Genie REST API
