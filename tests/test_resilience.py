import os
import pytest
from src.main import process

@pytest.fixture
def chaos_jsonl(tmp_path):
    """Fixture que cria um arquivo com BOM e dados corrompidos."""
    file_path = tmp_path / "chaos.jsonl"
    chaos_data = [
        '{"championship": "SERIE A", "name": "Valido 1"}',
        '',
        '{"championship": "SERIE B", "name": "Valido 2", "players": [{"name": "P1"}]}',
        'isto nao e json com teste@empresa.com e 123.456.789-00',
        '{"championship": "SERIE A", "colors": "nao sou lista"}',
        '{"championship": "SERIE B", "players": "nao sou lista"}',
        '["lista em vez de dict"]',
        '12345',
    ]
    
    # Gravando com utf-8-sig para adicionar o BOM (\ufeff)
    with open(file_path, "w", encoding="utf-8-sig") as f:
        for line in chaos_data:
            f.write(line + "\n")
            
    return file_path

class TestResilience:
    def test_pipeline_fail_gracefully_and_dlq(self, tmp_path, chaos_jsonl):
        """
        Testa resiliência a BOM, json quebrado e geração correta da DLQ.
        """
        output_dir = tmp_path / "out"
        os.makedirs(output_dir, exist_ok=True)
        
        # A execução não deve levantar exceções (Exit Code 0 equivalent)
        stats = process(str(chaos_jsonl), str(output_dir))
        
        # Total lidas deve ser 8
        assert stats["linhas_lidas"] == 8
        assert stats["linhas_vazias"] == 1
        assert stats["linhas_json_invalido"] == 3
        assert stats["linhas_dlq"] == 3
        
        # Arquivos criados com sucesso
        clubs_path = output_dir / "clubs.csv"
        dlq_path = output_dir / "dlq_errors.txt"
        
        assert clubs_path.exists()
        assert dlq_path.exists()
        
        # Valida conteúdo da DLQ e o Data Masking LGPD
        with open(dlq_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 3
            assert "[LINHA:4][JSON_MALFORMADO]" in lines[0]
            
            # Valida ofuscação (LGPD) no erro malformado
            assert "[EMAIL_OCULTO]" in lines[0]
            assert "[CPF_OCULTO]" in lines[0]
            assert "teste@empresa.com" not in lines[0]
            assert "123.456.789-00" not in lines[0]
            
            assert "[LINHA:7][TIPO_INVALIDO:list]" in lines[1]
            assert "[LINHA:8][TIPO_INVALIDO:int]" in lines[2]
