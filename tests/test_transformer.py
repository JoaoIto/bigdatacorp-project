import pytest
from src.transformer import (
    is_valid_championship,
    safe_str,
    format_date,
    format_colors,
    _format_colors_cached,
)

class TestTransformer:
    def test_is_valid_championship(self):
        # Casos válidos
        assert is_valid_championship({"championship": "SERIE A"}) is True
        assert is_valid_championship({"championship": "Série B"}) is True
        assert is_valid_championship({"championship": " serie a "}) is True
        assert is_valid_championship({"championship": "série a"}) is True
        assert is_valid_championship({"championship": "SÉRIE B"}) is True
        
        # Casos inválidos
        assert is_valid_championship({"championship": "SERIE C"}) is False
        assert is_valid_championship({"championship": "SEM CAMPEONATO"}) is False
        assert is_valid_championship({"championship": ""}) is False
        assert is_valid_championship({"championship": None}) is False
        assert is_valid_championship({}) is False
        assert is_valid_championship({"championship": 123}) is False

    def test_safe_str(self):
        # Casos comuns
        assert safe_str({"name": "Clube"}, "name") == "Clube"
        assert safe_str({"age": 26}, "age") == "26"
        assert safe_str({"age": 0}, "age") == "0"
        
        # Fallbacks seguros (RN05)
        assert safe_str({"nickname": None}, "nickname") == ""
        assert safe_str({}, "missing") == ""

    def test_format_date(self):
        # Casos válidos
        assert format_date("2024-01-18") == "2024-01-18"
        assert format_date("18/01/2024") == "2024-01-18"
        assert format_date("2024/01/18") == "2024-01-18"
        assert format_date(" 2024-01-18 ") == "2024-01-18"
        
        # Datas inválidas ou nulas
        assert format_date("18-01-2024") == ""  # Formato não mapeado intencionalmente
        assert format_date("Data Inválida") == ""
        assert format_date("") == ""
        assert format_date("   ") == ""
        assert format_date(None) == ""
        assert format_date(2024) == ""

    def test_format_colors(self):
        # Casos válidos
        assert format_colors(["preto", "branco"]) == "preto|branco"
        assert format_colors(["azul", "branco", "vermelho"]) == "azul|branco|vermelho"
        assert format_colors(["verde"]) == "verde"
        
        # Casos inválidos ou nulos
        assert format_colors([]) == ""
        assert format_colors(None) == ""
        assert format_colors("vermelho") == "" # Espera lista, não string
        assert format_colors(["azul", None, "branco"]) == "azul|branco"
        assert format_colors([1, 2]) == "1|2" # Coerce pra string

        # Validar o comportamento do @lru_cache convertendo para tupla
        _format_colors_cached.cache_clear()
        
        format_colors(["amarelo", "preto"])
        info = _format_colors_cached.cache_info()
        assert info.misses == 1
        assert info.hits == 0
        
        # Chama a mesma combinação, deve usar o cache
        format_colors(["amarelo", "preto"])
        info = _format_colors_cached.cache_info()
        assert info.hits == 1
