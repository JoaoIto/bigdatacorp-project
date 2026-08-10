import os
import pytest
from src.main import process

@pytest.fixture
def chaos_jsonl(tmp_path):
    """Fixture que cria um arquivo com dados severamente corrompidos (Chaos Testing)."""
    file_path = tmp_path / "chaos.jsonl"
    chaos_data = [
        '{"championship": "SERIE A", "name": "Valido 1"}', # OK
        '', # Linha vazia
        '{"championship": "SERIE B", "name": "Valido 2", "players": [{"name": "P1"}]}', # OK
        'isto nao e json', # JSON malformado
        '{"championship": "SERIE A", "colors": "nao sou lista"}', # Tipo errado (cores)
        '{"championship": "SERIE B", "players": "nao sou lista"}', # Tipo errado (players)
        '["lista em vez de dict"]', # Objeto raiz incorreto
        '12345', # Objeto raiz primitivo
    ]
    
    with open(file_path, "w", encoding="utf-8") as f:
        for line in chaos_data:
            f.write(line + "\n")
            
    return file_path

class TestResilience:
    def test_pipeline_fail_gracefully(self, tmp_path, chaos_jsonl):
        """
        Garante que o pipeline não lança exceções (não aborta) frente a dados absurdos.
        O sistema deve registrar os erros e processar apenas as linhas válidas.
        """
        output_dir = tmp_path / "out"
        os.makedirs(output_dir, exist_ok=True)
        
        # Act - Executa o pipeline. 
        # A asserção principal aqui é que NENHUMA exceção subirá desta chamada.
        stats = process(str(chaos_jsonl), str(output_dir))
        
        # Assert - Verifica se processou os válidos e engoliu os inválidos
        assert stats["linhas_lidas"] == 8
        assert stats["linhas_vazias"] == 1
        assert stats["linhas_json_invalido"] == 3 # "isto nao e json", lista pura, número
        
        # Apesar de tudo isso, os válidos e parciais devem ser escritos! (Total de 4 clubes que passam no filtro)
        assert stats["clubes_escritos"] == 4
        assert stats["jogadores_escritos"] == 1
        
        # O programa não aborta (Fail Gracefully)
        assert (output_dir / "clubs.csv").exists()
