import pytest
from src.transformer import (
    run_validations,
    format_date,
    format_colors,
    _format_colors_cached,
)
from src.schema import safe_value

class TestTransformer:
    def test_run_validations(self):
        # Casos válidos
        assert run_validations({"championship": "SERIE A"}) == (True, "")
        assert run_validations({"championship": "Série B"}) == (True, "")
        assert run_validations({"championship": " serie a "}) == (True, "")
        assert run_validations({"championship": "série a"}) == (True, "")
        assert run_validations({"championship": "SÉRIE B"}) == (True, "")
        
        # Casos inválidos
        assert run_validations({"championship": "SERIE C"}) == (False, "CHAMPIONSHIP_OUT_OF_SCOPE")
        assert run_validations({"championship": "SEM CAMPEONATO"}) == (False, "CHAMPIONSHIP_OUT_OF_SCOPE")
        assert run_validations({"championship": ""}) == (False, "CHAMPIONSHIP_INVALID")
        assert run_validations({"championship": None}) == (False, "CHAMPIONSHIP_INVALID")
        assert run_validations({}) == (False, "CHAMPIONSHIP_INVALID")
        assert run_validations({"championship": 123}) == (False, "CHAMPIONSHIP_INVALID")

    def test_safe_value(self):
        # Casos comuns
        assert safe_value("Clube") == "Clube"
        assert safe_value(26) == "26"
        assert safe_value(0) == "0"
        
        # Fallbacks seguros (RN05)
        assert safe_value(None) == ""

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
