import os
import pytest
from unittest.mock import patch
from src.main import process

@pytest.fixture
def partial_jsonl(tmp_path):
    """Fixture para testar falha no meio do processo."""
    file_path = tmp_path / "partial.jsonl"
    data = [
        '{"championship": "SERIE A", "name": "Clube 1"}',
        '{"championship": "SERIE A", "name": "Clube 2"}',
        '{"championship": "SERIE B", "name": "Clube 3"}',
    ]
    with open(file_path, "w", encoding="utf-8") as f:
        for line in data:
            f.write(line + "\n")
    return file_path

class TestIdempotency:
    @patch('src.main.is_valid_championship')
    def test_idempotency_atomic_writes(self, mock_is_valid, tmp_path, partial_jsonl):
        """
        O Teste do Cisne Negro: Garante que se uma exceção não-tratada (abortiva)
        acontecer a meio do processamento, os ficheiros .tmp são apagados no finally
        e nenhum ficheiro corrupto (CSV) é mantido.
        """
        output_dir = tmp_path / "out"
        os.makedirs(output_dir, exist_ok=True)
        
        # O mock vai funcionar na primeira linha e explodir na segunda com KeyboardInterrupt
        # (Usamos KeyboardInterrupt porque ele herda de BaseException e fura o `except Exception:` do pipeline)
        mock_is_valid.side_effect = [True, KeyboardInterrupt("Simulate fatal failure mid-process!"), True]
        
        with pytest.raises(KeyboardInterrupt, match="Simulate fatal failure mid-process!"):
            process(str(partial_jsonl), str(output_dir))
            
        # Verifica que o diretório não contém nenhuma pasta temporária nem os csv parciais
        files = os.listdir(output_dir)
        
        # Não deve haver diretório .tmp_run_ ou arquivos csv consolidados
        for f in files:
            assert not f.startswith(".tmp_run_")
            assert not f.endswith(".tmp")
            
        assert "clubs.csv" not in files
        assert "players.csv" not in files
