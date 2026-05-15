# ============================================================
# GENIE CHATBOT - CONFIGURAÇÕES
# ============================================================
# Modifique as configurações abaixo conforme necessário
# ============================================================

# ------------------------------------------------------------
# CONFIGURAÇÕES DA APLICAÇÃO
# ------------------------------------------------------------

# Nome da aplicação (aparece no título e header)
APP_NAME = "Genie Chatbot"

# Descrição da aplicação
APP_DESCRIPTION = "Assistente de dados powered by Databricks Genie"

# Badge "Powered by" no header (deixe vazio "" para esconder)
POWERED_BY = "Databricks"

# ------------------------------------------------------------
# IDENTIDADE VISUAL (CORES)
# ------------------------------------------------------------
# Cores em formato hexadecimal

BRAND_COLORS = {
    "primary": "#002855",      # Cor principal (header, botões)
    "secondary": "#426ca9",    # Cor secundária
    "accent": "#28c18d",       # Cor de destaque (status online, sucesso)
    "background": "#f5f5f5",   # Cor de fundo
    "light": "#e8f0f8",        # Cor clara para hover/seleção
}

# ------------------------------------------------------------
# PERSISTÊNCIA DE HISTÓRICO (LAKEBASE)
# ------------------------------------------------------------

# Habilitar persistência de histórico no Lakebase?
# True = histórico salvo no banco de dados (persiste entre sessões)
# False = histórico apenas em memória (perdido ao recarregar página)
ENABLE_HISTORY_PERSISTENCE = True

# Configurações do Lakebase (apenas se ENABLE_HISTORY_PERSISTENCE = True)
LAKEBASE_CONFIG = {
    "project": "genie-chatbot-db",
    "branch": "production",
    "host": "ep-round-sky-d29cryqo.database.us-east-1.cloud.databricks.com",
    "database": "databricks_postgres",
}

# ------------------------------------------------------------
# GENIE SPACES PADRÃO (FALLBACK)
# ------------------------------------------------------------
# Lista de Genie Spaces exibidos caso a API falhe
# Deixe vazio [] para não ter fallback

DEFAULT_GENIE_SPACES = [
    # {
    #     "space_id": "seu-space-id-aqui",
    #     "title": "Nome do Space",
    #     "description": "Descrição do Space"
    # },
]

# ------------------------------------------------------------
# CONFIGURAÇÕES AVANÇADAS
# ------------------------------------------------------------

# Timeout para chamadas ao Genie (segundos)
GENIE_TIMEOUT_SECONDS = 120

# Máximo de linhas exibidas na tabela
MAX_TABLE_ROWS = 20

# Máximo de linhas para gerar gráfico automaticamente
MAX_CHART_ROWS = 50
