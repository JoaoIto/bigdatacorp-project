import os
import json
import pytest
from src.main import process

@pytest.fixture
def sample_jsonl(tmp_path):
    """Fixture que cria um arquivo JSONL controlado para testes de integração."""
    file_path = tmp_path / "test_input.jsonl"
    data = [
        # Clube 1 - Válido, Série A, 2 jogadores
        {
            "club_id": "C1", "name": "Clube 1", "championship": "Série A",
            "founding_date": "1990-01-01", "city": "SP", "state": "SP", "country": "BR",
            "stadium": "Estadio 1", "president": "Pres 1", "nickname": "Apelido", "colors": ["azul"],
            "players": [
                {"player_id": "P1", "name": "J1", "age": 20, "goals": 10, "debut_date": "2020-01-01", "position": "Ata", "shirt_number": 9},
                {"player_id": "P2", "name": "J2", "age": 25, "goals": 5, "debut_date": "2019-01-01", "position": "Zag", "shirt_number": 3}
            ]
        },
        # Clube 2 - Válido, Série B, 0 jogadores, dados incompletos
        {
            "club_id": "C2", "name": "Clube 2", "championship": "Serie B",
            "players": []
        },
        # Clube 3 - Inválido, Sem Campeonato (deve ser filtrado)
        {
            "club_id": "C3", "name": "Clube 3", "championship": "Serie C",
            "players": [{"player_id": "P3", "name": "J3"}]
        }
    ]
    
    with open(file_path, "w", encoding="utf-8") as f:
        for record in data:
            f.write(json.dumps(record) + "\n")
            
    return file_path

class TestPipeline:
    def test_end_to_end_pipeline(self, tmp_path, sample_jsonl):
        """Teste de integração que executa o pipeline completo e verifica contadores e CSVs."""
        output_dir = tmp_path / "out"
        os.makedirs(output_dir, exist_ok=True)
        
        # Executa o pipeline
        stats = process(str(sample_jsonl), str(output_dir))
        
        # Verifica contadores retornados pelo orquestrador
        assert stats["linhas_lidas"] == 3
        assert stats["clubes_filtrados"] == 1  # Clube 3 foi filtrado
        assert stats["clubes_escritos"] == 2   # C1 e C2
        assert stats["jogadores_escritos"] == 2 # P1 e P2 (P3 filtrado junto com C3)
        assert stats["erros_processamento"] == 0
        
        # Verifica se os arquivos foram criados
        clubs_csv = output_dir / "clubs.csv"
        players_csv = output_dir / "players.csv"
        assert clubs_csv.exists()
        assert players_csv.exists()
        
        # Verifica o conteúdo (linhas = header + dados)
        with open(clubs_csv, "r", encoding="utf-8") as f:
            clubs_lines = f.readlines()
            assert len(clubs_lines) == 3 # Header + C1 + C2
            
        with open(players_csv, "r", encoding="utf-8") as f:
            players_lines = f.readlines()
            assert len(players_lines) == 3 # Header + P1 + P2
