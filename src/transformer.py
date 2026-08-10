"""
transformer.py — Módulo de regras de negócio e transformação de dados.

Contém todas as funções de validação, formatação e mapeamento que
transformam os dicts parseados do JSONL em rows prontas para o CSV.

Este módulo é PURO — não faz I/O de arquivos. Todas as funções
recebem dados e retornam dados, facilitando testes unitários.

Regras de negócio implementadas:
  RN01 — Filtro por campeonato (Série A / Série B)
  RN03 — Formatação de cores com pipe (|)
  RN04 — Validação e formatação de datas (yyyy-MM-dd)
  RN05 — Campos ausentes ou nulos → campo vazio

Referências:
  spec/research.md §1.4 (Inventário de regras)
  spec/decisions.md ADR-002 (Erros de Validação vs. Estrutura)
  spec/decisions.md ADR-005 (Normalização de championship)
"""

from datetime import datetime

# ──────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────

# Campeonatos válidos para o filtro RN01 (normalizados em uppercase)
VALID_CHAMPIONSHIPS = {"SERIE A", "SERIE B"}

# Formatos de data aceitos no parse (tentados em ordem)
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]

# Cabeçalhos dos CSVs — nomes em português, na ordem exata exigida
# pelo enunciado (incluindo acentos, espaços e caixa).

CLUBS_HEADER = [
    "Id do Clube",
    "Nome",
    "Campeonato",
    "Data de Fundação",
    "Cidade",
    "Estado",
    "País",
    "Estádio",
    "Presidente",
    "Apelido",
    "Cores",
]

PLAYERS_HEADER = [
    "Id do Clube",
    "Id do Jogador",
    "Nome",
    "Idade",
    "Gols",
    "Data de Estreia",
    "Posição",
    "Número da Camisa",
]


# ──────────────────────────────────────────────────────────────
# Funções auxiliares de validação e formatação
# ──────────────────────────────────────────────────────────────

def is_valid_championship(record):
    """Verifica se o clube pertence à Série A ou Série B (RN01).

    A comparação é case-insensitive e tolerante a espaços extras.
    Aceita variações como "SERIE A", "Serie A", " serie b ",
    "Série A", "SÉRIE B" (com ou sem acento).

    Args:
        record (dict): O dict do clube parseado do JSONL.

    Returns:
        bool: True se o campeonato for Série A ou B, False caso contrário.

    Examples:
        >>> is_valid_championship({"championship": "SERIE A"})
        True
        >>> is_valid_championship({"championship": "SEM CAMPEONATO"})
        False
        >>> is_valid_championship({"championship": None})
        False
        >>> is_valid_championship({})
        False
    """
    championship = record.get("championship")

    if not championship or not isinstance(championship, str):
        return False

    # Normaliza: strip + uppercase + remove acento do É
    normalized = championship.strip().upper().replace("É", "E")

    return normalized in VALID_CHAMPIONSHIPS


def safe_str(record, key):
    """Extrai um campo do dict com fallback seguro para string vazia (RN05).

    Se a chave estiver ausente ou o valor for None, retorna "".
    Valores numéricos (int, float) são convertidos para string.

    Args:
        record (dict): O dicionário fonte.
        key (str): A chave a buscar.

    Returns:
        str: O valor como string, ou "" se ausente/None.

    Examples:
        >>> safe_str({"name": "Corinthians"}, "name")
        'Corinthians'
        >>> safe_str({"age": 26}, "age")
        '26'
        >>> safe_str({"nickname": None}, "nickname")
        ''
        >>> safe_str({}, "missing_key")
        ''
    """
    value = record.get(key)
    if value is None:
        return ""
    return str(value)


def format_date(value):
    """Valida e formata uma data para o padrão yyyy-MM-dd (RN04).

    Tenta parsear o valor em múltiplos formatos conhecidos.
    Se nenhum formato funcionar, retorna string vazia — sem exceções.
    A linha que contém uma data inválida continua no arquivo normalmente.

    Args:
        value: O valor bruto do campo de data. Pode ser str, None,
               int, ou qualquer outro tipo.

    Returns:
        str: A data formatada como "yyyy-MM-dd", ou "" se inválida.

    Examples:
        >>> format_date("2024-01-18")
        '2024-01-18'
        >>> format_date("18/01/2024")
        '2024-01-18'
        >>> format_date("abc")
        ''
        >>> format_date(None)
        ''
        >>> format_date(12345)
        ''
    """
    # Guarda: tipos não-string ou vazios
    if not value or not isinstance(value, str):
        return ""

    stripped = value.strip()
    if not stripped:
        return ""

    # Tenta cada formato conhecido
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(stripped, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Nenhum formato funcionou → campo vazio (Erro de Validação, não de Estrutura)
    return ""


def format_colors(colors):
    """Une uma lista de cores em um campo separado por pipe '|' (RN03).

    Exemplos de transformação:
      ["preto", "branco"]              → "preto|branco"
      ["azul", "branco", "vermelho"]   → "azul|branco|vermelho"
      []                               → ""
      None                             → ""

    Args:
        colors: O valor bruto do campo 'colors'. Espera-se uma lista
                de strings, mas pode ser qualquer tipo.

    Returns:
        str: As cores unidas por '|', ou "" se a lista for vazia/inválida.

    Examples:
        >>> format_colors(["preto", "branco"])
        'preto|branco'
        >>> format_colors([])
        ''
        >>> format_colors(None)
        ''
        >>> format_colors("azul")
        ''
    """
    if not colors or not isinstance(colors, list):
        return ""

    # Filtra elementos None ou não-string da lista
    valid_colors = [str(c) for c in colors if c is not None]

    if not valid_colors:
        return ""

    return "|".join(valid_colors)


# ──────────────────────────────────────────────────────────────
# Funções de transformação (mapeamento JSON → CSV row)
# ──────────────────────────────────────────────────────────────

def transform_club(record):
    """Transforma um dict de clube em uma row para clubs.csv.

    Aplica todas as regras de formatação (datas, cores, campos nulos)
    e retorna os 11 campos na ordem exata exigida pelo enunciado.

    Campos descartados do JSON (não mapeados): titles, players.

    Args:
        record (dict): O dict do clube parseado do JSONL.

    Returns:
        list[str]: Lista de 11 strings na ordem do cabeçalho CLUBS_HEADER.
    """
    return [
        safe_str(record, "club_id"),        # Id do Clube
        safe_str(record, "name"),            # Nome
        safe_str(record, "championship"),    # Campeonato
        format_date(record.get("founding_date")),  # Data de Fundação
        safe_str(record, "city"),            # Cidade
        safe_str(record, "state"),           # Estado
        safe_str(record, "country"),         # País
        safe_str(record, "stadium"),         # Estádio
        safe_str(record, "president"),       # Presidente
        safe_str(record, "nickname"),        # Apelido
        format_colors(record.get("colors")), # Cores
    ]


def transform_player(club_id, player):
    """Transforma um dict de jogador em uma row para players.csv.

    O club_id é recebido do clube pai para estabelecer a relação 1:N.

    Campos descartados do JSON (não mapeados): nationality, market_value.

    Args:
        club_id (str): O club_id do clube ao qual o jogador pertence.
        player (dict): O dict de um jogador do array 'players'.

    Returns:
        list[str]: Lista de 8 strings na ordem do cabeçalho PLAYERS_HEADER.
    """
    return [
        club_id,                                    # Id do Clube
        safe_str(player, "player_id"),              # Id do Jogador
        safe_str(player, "name"),                   # Nome
        safe_str(player, "age"),                    # Idade
        safe_str(player, "goals"),                  # Gols
        format_date(player.get("debut_date")),      # Data de Estreia
        safe_str(player, "position"),               # Posição
        safe_str(player, "shirt_number"),           # Número da Camisa
    ]
