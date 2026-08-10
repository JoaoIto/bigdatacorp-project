import json
import random
import os

def generate_mass_data(filepath, num_records=1_000_000):
    """
    Gera um arquivo JSONL gigante para testes de estresse (Performance & Memory Profiling).
    
    Cria registros de clubes falsos contendo entre 0 e 5 jogadores cada.
    Aproximadamente 90% dos registros serão válidos (Série A ou B), e 10% serão filtrados.
    """
    print(f"Gerando {num_records:,} registros em {filepath}...")
    
    championships = ["SERIE A", "SERIE B", "SERIE C", "SEM CAMPEONATO"]
    weights = [0.45, 0.45, 0.05, 0.05]
    
    # Pre-cria o diretório se não existir
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    
    with open(filepath, "w", encoding="utf-8") as f:
        for i in range(1, num_records + 1):
            club_id = f"CLUB-{i}"
            championship = random.choices(championships, weights=weights)[0]
            
            # Gera 0 a 5 jogadores por clube
            num_players = random.randint(0, 5)
            players = []
            for j in range(num_players):
                players.append({
                    "player_id": f"{club_id}-P{j}",
                    "name": f"Jogador {j}",
                    "age": random.randint(16, 40),
                    "goals": random.randint(0, 100),
                    "debut_date": "2020-01-01",
                    "position": "Atacante",
                    "shirt_number": random.randint(1, 99)
                })
            
            record = {
                "club_id": club_id,
                "name": f"Clube Falso {i}",
                "championship": championship,
                "founding_date": "1900-01-01",
                "city": "Test City",
                "state": "TS",
                "country": "Brasil",
                "stadium": "Test Stadium",
                "president": "Presidente Teste",
                "nickname": "Test Nick",
                "colors": ["preto", "branco"],
                "titles": random.randint(0, 50),
                "players": players
            }
            
            f.write(json.dumps(record) + "\n")
            
            if i % 100_000 == 0:
                print(f"  {i:,} registros gerados...")
                
    print(f"Geração concluída! Arquivo: {filepath}")

if __name__ == "__main__":
    output_path = os.path.join(os.path.dirname(__file__), "..", "data", "input", "mass_data.jsonl")
    generate_mass_data(output_path, 1_000_000)
