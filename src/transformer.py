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

import functools
from datetime import datetime
from typing import Any, Dict, List, Tuple

# ──────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────

# Campeonatos válidos para o filtro RN01 (normalizados em uppercase)
VALID_CHAMPIONSHIPS = {"SERIE A", "SERIE B"}

# Formatos de data aceitos no parse (tentados em ordem)
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]

# Cabeçalhos estão agora em schema.py


# ──────────────────────────────────────────────────────────────
# Funções auxiliares de validação e formatação
# ──────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────
# Padrão: Chain of Responsibility para Validações Modulares
# ──────────────────────────────────────────────────────────────

class Validator:
    """Base protocol para validação na cadeia."""
    def validate(self, record: Dict[str, Any]) -> Tuple[bool, str]:
        """Retorna (is_valid, error_reason_if_any)."""
        raise NotImplementedError

class ChampionshipFilter(Validator):
    """Verifica se o clube pertence à Série A ou Série B (RN01)."""
    def validate(self, record: Dict[str, Any]) -> Tuple[bool, str]:
        championship = record.get("championship")
        if not championship or not isinstance(championship, str):
            return False, "CHAMPIONSHIP_INVALID"
            
        normalized = championship.strip().upper().replace("É", "E")
        if normalized in VALID_CHAMPIONSHIPS:
            return True, ""
        return False, "CHAMPIONSHIP_OUT_OF_SCOPE"


# Instanciação da cadeia de validação
VALIDATION_CHAIN: List[Validator] = [
    ChampionshipFilter(),
]

def run_validations(record: Dict[str, Any]) -> Tuple[bool, str]:
    """Passa o registro pela esteira de validadores (Chain of Responsibility)."""
    for validator in VALIDATION_CHAIN:
        is_valid, reason = validator.validate(record)
        if not is_valid:
            return False, reason
    return True, ""


def format_date(value: Any) -> str:
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


@functools.lru_cache(maxsize=256)
def _format_colors_cached(colors: Tuple[str, ...]) -> str:
    """Função interna com memoization (cache) para strings de cores.
    Espera receber uma tupla de strings (que é hashável).
    """
    return "|".join(colors)


def format_colors(colors: Any) -> str:
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

    # Filtra elementos None e converte para tupla de strings para o cache
    colors_tuple = tuple(str(c) for c in colors if c is not None)
    
    if not colors_tuple:
        return ""
        
    return _format_colors_cached(colors_tuple)


# ──────────────────────────────────────────────────────────────
# Funções de transformação (mapeamento JSON → CSV row)
# ──────────────────────────────────────────────────────────────

def transform_by_schema(record: Dict[str, Any], schema: List[Tuple[str, str, Any]]) -> List[str]:
    """Aplica uma transformação dinâmica baseada no schema declarativo.
    
    Args:
        record: O dict parseado do JSON.
        schema: A lista de tuplas (Coluna, ChaveJSON, FunçãoTransformação).
        
    Returns:
        list[str]: Lista de strings prontas para o CSV.
    """
    return [transform_fn(record.get(json_key)) for _, json_key, transform_fn in schema]

def transform_club(record: Dict[str, Any]) -> List[str]:
    """Aplica as transformações e retorna uma linha pronta para o CSV."""
    from schema import CLUBS_SCHEMA
    return transform_by_schema(record, CLUBS_SCHEMA)

def transform_player(club_id: str, player: Dict[str, Any]) -> List[str]:
    """Associa um jogador ao ID do clube e aplica as transformações (RN02)."""
    # Injeta a referência (RN02)
    from schema import PLAYERS_SCHEMA
    player_copy = dict(player)
    player_copy["club_id"] = club_id
    return transform_by_schema(player_copy, PLAYERS_SCHEMA)
