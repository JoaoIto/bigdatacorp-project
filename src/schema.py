from typing import Any, Callable, Dict, List, Tuple
from transformer import format_date, format_colors

def safe_value(value: Any) -> str:
    """Extrai valor com fallback para string vazia."""
    return "" if value is None else str(value)

# Schema de mapeamento: (Nome da Coluna, Chave no JSON, Função de Transformação)
CLUBS_SCHEMA: List[Tuple[str, str, Callable[[Any], str]]] = [
    ("Id do Clube", "club_id", safe_value),
    ("Nome", "name", safe_value),
    ("Campeonato", "championship", safe_value),
    ("Data de Fundação", "foundation_date", format_date),
    ("Cidade", "city", safe_value),
    ("Estado", "state", safe_value),
    ("País", "country", safe_value),
    ("Estádio", "stadium", safe_value),
    ("Presidente", "president", safe_value),
    ("Apelido", "nickname", safe_value),
    ("Cores", "colors", format_colors),
]

PLAYERS_SCHEMA: List[Tuple[str, str, Callable[[Any], str]]] = [
    ("Id do Clube", "club_id", safe_value),
    ("Id do Jogador", "player_id", safe_value),
    ("Nome", "name", safe_value),
    ("Idade", "age", safe_value),
    ("Gols", "goals", safe_value),
    ("Data de Estreia", "debut_date", format_date),
    ("Posição", "position", safe_value),
    ("Número da Camisa", "shirt_number", safe_value),
]

CLUBS_HEADER = [col[0] for col in CLUBS_SCHEMA]
PLAYERS_HEADER = [col[0] for col in PLAYERS_SCHEMA]
