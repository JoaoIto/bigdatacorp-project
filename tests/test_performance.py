import os
import pytest
from unittest.mock import patch, MagicMock
from src.main import process

@pytest.fixture
def mock_jsonl(tmp_path):
    """Cria um arquivo de entrada vazio. Vamos mockar o reader de qualquer forma."""
    file_path = tmp_path / "dummy.jsonl"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("")
    return file_path

class TestPerformance:
    @patch('src.main.read_jsonl')
    @patch('src.main.gc')
    def test_deterministic_gc_call_count(self, mock_gc, mock_read_jsonl, tmp_path, mock_jsonl):
        """
        Prova de Performance do GC Determinístico:
        Verifica se o garbage collector da Geração 0 é chamado exatamente o número
        de vezes esperado baseado no GC_INTERVAL de 100.000 linhas.
        """
        output_dir = tmp_path / "out"
        os.makedirs(output_dir, exist_ok=True)
        
        # Simular a passagem de 250.000 linhas pelo orquestrador sem I/O real
        # read_jsonl é um generator, então precisamos criar um gerador mockado.
        def fake_generator(input_path, stats, dlq_fh):
            # Simulamos 250.000 registros, incrementando a estatística
            for i in range(1, 250001):
                stats["linhas_lidas"] += 1
                yield i, {"championship": "SERIE A", "name": f"Mock {i}"}
                
        mock_read_jsonl.side_effect = fake_generator
        
        # O mock_gc.collect.call_count deve ser 250.000 // 100.000 = 2
        process(str(mock_jsonl), str(output_dir))
        
        # O gc foi desativado no início
        mock_gc.disable.assert_called_once()
        
        # O gc da gen 0 deve ter sido chamado 2 vezes (na linha 100k e 200k)
        assert mock_gc.collect.call_count == 2
        # As chamadas devem ser gc.collect(0)
        mock_gc.collect.assert_called_with(0)
        
        # O gc foi reativado no finally
        mock_gc.enable.assert_called_once()
