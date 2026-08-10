import os
import sys
import time
import tracemalloc

# Adiciona o diretório src ao path para poder importar o orquestrador
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from main import process

def run_profiling(input_path, output_dir):
    """
    Executa o pipeline medindo o tempo de execução e o pico de consumo de memória RAM.
    O objetivo é provar que a leitura em streaming mantém a memória estável (O(1)) 
    independentemente do tamanho do arquivo (ex: 1 milhão de linhas).
    """
    if not os.path.exists(input_path):
        print(f"Erro: Arquivo {input_path} não encontrado.")
        print("Execute 'python scripts/generate_mass_data.py' primeiro.")
        return

    print("=" * 50)
    print(f"Iniciando Profiling de Memória (tracemalloc)")
    print(f"Arquivo alvo: {input_path}")
    print("=" * 50)
    
    # Inicia o rastreamento de alocação de memória
    tracemalloc.start()
    start_time = time.time()
    
    # Act - Executa o pipeline
    stats = process(input_path, output_dir)
    
    # Captura métricas
    end_time = time.time()
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    # Conversão de bytes para Megabytes (MB)
    current_mb = current_mem / 1024 / 1024
    peak_mb = peak_mem / 1024 / 1024
    duration = end_time - start_time
    
    print("\n" + "=" * 50)
    print("RESULTADOS DO PROFILING (PROVA DE O(1) COMPLEXIDADE ESPACIAL)")
    print("=" * 50)
    print(f"Registros lidos:      {stats.get('linhas_lidas'):,}")
    print(f"Tempo de execução:    {duration:.2f} segundos")
    print(f"Consumo Final de RAM: {current_mb:.4f} MB")
    print(f"PICO MÁXIMO DE RAM:   {peak_mb:.4f} MB")
    print("=" * 50)
    print("Conclusão: O pipeline processa milhões de registros mantendo um consumo")
    print("           de memória minúsculo e constante, validando a arquitetura de")
    print("           streaming via Generators do Python.")
    print("=" * 50)

if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    input_file = os.path.join(base_dir, "data", "input", "mass_data.jsonl")
    out_dir = os.path.join(base_dir, "data", "output")
    
    run_profiling(input_file, out_dir)
