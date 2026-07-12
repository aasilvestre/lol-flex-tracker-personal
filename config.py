# =============================================================================
# config.py — Configurações do Personal Flex Tracker
#
# Este é o único arquivo que você precisa editar para adaptar o tracker
# ao seu jogador, servidor e filas monitoradas.
# =============================================================================


# =============================================================================
# IDENTIFICAÇÃO DO JOGADOR
#
# Nome e tag do seu invocador, no formato exibido no cliente do jogo.
# Exemplo: se seu nome aparece como "Faker#KR1", use:
#   PLAYER_NAME = "Faker"
#   PLAYER_TAG  = "KR1"
#
# Atenção: diferencia maiúsculas/minúsculas. Use exatamente como aparece no jogo.
# =============================================================================
PLAYER_NAME = "Uga Chaka"
PLAYER_TAG  = "Uga"


# =============================================================================
# SERVIDOR (PLATAFORMA)
#
# Código do servidor onde sua conta está registrada.
# Escolha apenas UM dos valores abaixo:
#
#   Brasil             → "br1"
#   América do Norte   → "na1"
#   Europa Oeste       → "euw1"
#   Europa Nórdica     → "eun1"
#   Coreia             → "kr"
#   Japão              → "jp1"
#   América Latina N.  → "la1"
#   América Latina S.  → "la2"
#   Oceania            → "oc1"
#   Turquia            → "tr1"
#   Rússia             → "ru"
# =============================================================================
PLATFORM = "br1"


# =============================================================================
# ROTEAMENTO REGIONAL
#
# A API da Riot usa dois tipos de URL:
#   - Platform: para dados de partidas e ranking (usa PLATFORM acima)
#   - Regional: para dados de conta (gameName, tagLine, puuid)
#
# Escolha o REGIONAL_HOST correspondente ao seu servidor:
#
#   "americas"  → br1, na1, la1, la2
#   "europe"    → euw1, eun1, tr1, ru
#   "asia"      → kr, jp1
#   "sea"       → oc1
# =============================================================================
REGIONAL_HOST = "americas"


# =============================================================================
# FILAS MONITORADAS
#
# Define quais filas ranqueadas serão monitoradas para:
#   - Heatmap de atividade dos jogadores de elite
#   - Linha de corte de tier (Challenger/GM)
#   - Seu progresso pessoal de LP
#
# Valores disponíveis:
#   "RANKED_FLEX_SR"    → Ranqueada Flex 5x5
#   "RANKED_SOLO_5x5"   → Ranqueada Solo/Duo
#
# Você pode monitorar uma ou duas filas. Para monitorar só uma, deixe
# apenas ela na lista. Para as duas, mantenha ambas.
#
# Exemplo com apenas Flex:
#   QUEUES = ["RANKED_FLEX_SR"]
#
# Exemplo com ambas (padrão):
#   QUEUES = ["RANKED_SOLO_5x5", "RANKED_FLEX_SR"]
# =============================================================================
QUEUES = ["RANKED_SOLO_5x5", "RANKED_FLEX_SR"]


# =============================================================================
# RÓTULOS DAS FILAS (para exibição no dashboard)
#
# Nome amigável de cada fila, exibido nos gráficos e abas.
# Ajuste se quiser textos diferentes, mas mantenha as chaves iguais aos
# valores em QUEUES.
# =============================================================================
QUEUE_LABELS = {
    "RANKED_SOLO_5x5": "Solo/Duo",
    "RANKED_FLEX_SR":  "Flex 5x5",
}


# =============================================================================
# ESCALA DO GRÁFICO DE PROGRESSO PESSOAL
#
# O gráfico de progresso usa Mestre 0 LP como referência (zero do eixo Y).
# Divisões abaixo de Mestre têm valor negativo.
#
# Esta tabela define quantos LP cada divisão está abaixo de Mestre 0.
# Exemplo: Diamante 1 começa 100 LP abaixo de Mestre → offset = -100
#          Se você tiver 30 LP em D1, sua posição no gráfico = -100 + 30 = -70
#
# Você não precisa alterar isso a menos que a Riot mude a estrutura de divisões.
# =============================================================================
DIVISION_OFFSETS = {
    "MASTER":     0,
    "DIAMOND":   -100,   # D1 = -100 a -1  |  D2 = -200 a -101  | etc.
    "EMERALD":   -500,
    "PLATINUM":  -900,
    "GOLD":     -1300,
    "SILVER":   -1700,
    "BRONZE":   -2100,
    "IRON":     -2500,
}

# Quantos LP por divisão dentro de um tier (padrão Riot: 100)
LP_PER_DIVISION = 100


# =============================================================================
# HORÁRIO DE CAPTURA DO PISO DE TIER
#
# A Riot atualiza as listas de Challenger/GM uma vez por dia.
# O collector captura o LP mínimo de cada tier nessa janela.
#
# Horário em fuso horário de Brasília (UTC-3).
# Altere apenas se a Riot mudar o horário de atualização.
# =============================================================================
FLOOR_WINDOW_START = (23, 40)   # 23h40
FLOOR_WINDOW_END   = (23, 55)   # 23h55


# =============================================================================
# CORES DOS TIERS NO DASHBOARD (opcional)
#
# Cores usadas nos gráficos para cada tier.
# Formato: código hexadecimal HTML (#RRGGBB).
# =============================================================================
TIER_COLORS = {
    "challenger": "#f4c874",   # dourado
    "gm":         "#9d52ac",   # roxo
    "master":     "#4a90d9",   # azul
}

QUEUE_COLORS = {
    "RANKED_SOLO_5x5": "#3b82f6",   # azul
    "RANKED_FLEX_SR":  "#10b981",   # verde
}
