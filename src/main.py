"""
main.py — Orquestrador do pipeline de processamento batch.

Ponto de entrada do programa. Responsabilidades:
- Parse de argumentos CLI (caminho do arquivo de entrada e diretório de saída)
- Configuração do sistema de logging
- Composição e execução do pipeline: Reader → Transformer → Writer
- Gerenciamento do ciclo de vida dos arquivos (open/close)
- Contadores e relatório final de processamento

Uso:
    python src/main.py <arquivo_entrada.jsonl> [diretório_saída]

Referência arquitetural: spec/architecture.md §2 e §3
"""

import json
import logging
import os
import sys
from typing import Any, Dict

from reader import read_jsonl
from transformer import (
    CLUBS_HEADER,
    PLAYERS_HEADER,
    is_valid_championship,
    safe_str,
    transform_club,
    transform_player,
)
from writer import create_csv_writer

# ──────────────────────────────────────────────────────────────
# Configuração de Logging
# ──────────────────────────────────────────────────────────────

logger = logging.getLogger("bigdatacorp")


class JsonFormatter(logging.Formatter):
    """Formatter customizado nativo para serializar logs em JSON (ADR-006)."""
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(log_record)


def setup_logging() -> None:
    """Configura o sistema de logging com formato JSON nativo para Cloud.

    Nível INFO para o fluxo normal (início, fim, contadores).
    Nível WARNING para registros ignorados (JSON malformado, tipo errado).
    Nível ERROR para falhas de infraestrutura (arquivo não encontrado, I/O).
    """
    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    handler.setFormatter(formatter)
    
    # Evita adicionar handlers duplicados ao chamar múltiplas vezes (ex: em testes)
    if logging.root.hasHandlers():
        logging.root.handlers.clear()
        
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


# ──────────────────────────────────────────────────────────────
# Pipeline Principal
# ──────────────────────────────────────────────────────────────

def process(input_path: str, output_dir: str) -> Dict[str, int]:
    """Executa o pipeline completo de processamento JSONL → CSV.

    Fluxo para cada registro:
      1. Reader (generator) produz dicts válidos do JSONL.
      2. Filtro de campeonato (RN01): descarta clubes fora da Série A/B.
      3. Transformer: aplica regras de negócio (datas, cores, campos nulos).
      4. Writer: escreve imediatamente nos CSVs (streaming O(1)).

    Args:
        input_path (str): Caminho para o arquivo JSONL de entrada.
        output_dir (str): Diretório onde os CSVs serão escritos.

    Returns:
        dict: Dicionário com os contadores de processamento.
    """
    clubs_path = os.path.join(output_dir, "clubs.csv")
    players_path = os.path.join(output_dir, "players.csv")

    logger.info("Iniciando processamento...")
    logger.info("  Entrada:  %s", input_path)
    logger.info("  Saída:    %s", output_dir)

    # Contadores compartilhados com o reader (via dict mutável)
    stats = {
        "linhas_lidas": 0,
        "linhas_vazias": 0,
        "linhas_json_invalido": 0,
        "clubes_filtrados": 0,
        "clubes_escritos": 0,
        "jogadores_escritos": 0,
        "erros_processamento": 0,
    }

    # Abre os dois arquivos de saída
    clubs_fh, clubs_writer = create_csv_writer(clubs_path, CLUBS_HEADER)
    players_fh, players_writer = create_csv_writer(players_path, PLAYERS_HEADER)

    try:
        # Pipeline: Reader (generator) → Filter → Transform → Writer
        for line_number, record in read_jsonl(input_path, stats):
            try:
                # ── RN01: Filtro por campeonato ──
                if not is_valid_championship(record):
                    stats["clubes_filtrados"] += 1
                    continue

                # ── Transformar e escrever o clube (1:1) ──
                club_row = transform_club(record)
                clubs_writer.writerow(club_row)
                stats["clubes_escritos"] += 1

                # ── Transformar e escrever cada jogador (1:N) ──
                club_id = safe_str(record, "club_id")
                players = record.get("players")

                if isinstance(players, list):
                    for player in players:
                        if isinstance(player, dict):
                            player_row = transform_player(club_id, player)
                            players_writer.writerow(player_row)
                            stats["jogadores_escritos"] += 1

            except Exception as e:
                # Tolerância a falhas: erro em um registro não aborta o pipeline
                logger.warning(
                    "Linha %d: erro no processamento — %s: %s",
                    line_number,
                    type(e).__name__,
                    e,
                )
                stats["erros_processamento"] += 1
                continue

    finally:
        # Garante fechamento dos arquivos mesmo em caso de erro
        clubs_fh.close()
        players_fh.close()

    return stats


def print_report(stats: Dict[str, int]) -> None:
    """Exibe o relatório final de processamento no console.

    Args:
        stats (dict): Dicionário com os contadores.
    """
    logger.info("=" * 50)
    logger.info("Processamento concluído com sucesso.")
    logger.info("  Linhas lidas:              %d", stats.get("linhas_lidas", 0))
    logger.info("  Linhas vazias ignoradas:   %d", stats.get("linhas_vazias", 0))
    logger.info("  Linhas JSON inválido:      %d", stats.get("linhas_json_invalido", 0))
    logger.info("  Clubes filtrados:          %d", stats.get("clubes_filtrados", 0))
    logger.info("  Erros de processamento:    %d", stats.get("erros_processamento", 0))
    logger.info("  Clubes escritos:           %d", stats.get("clubes_escritos", 0))
    logger.info("  Jogadores escritos:        %d", stats.get("jogadores_escritos", 0))
    logger.info("=" * 50)


# ──────────────────────────────────────────────────────────────
# Ponto de Entrada CLI
# ──────────────────────────────────────────────────────────────

def main() -> None:
    """Ponto de entrada do programa.

    Uso:
        python src/main.py <arquivo_entrada.jsonl> [diretório_saída]

    Args (via sys.argv):
        arquivo_entrada: Caminho para o arquivo JSONL (obrigatório).
        diretório_saída: Diretório para os CSVs (opcional; padrão =
                         mesmo diretório do arquivo de entrada).
    """
    setup_logging()

    # ── Validação de argumentos ──
    if len(sys.argv) < 2:
        logger.error(
            "Uso: python main.py <arquivo_entrada.jsonl> [diretório_saída]"
        )
        sys.exit(1)

    input_path = sys.argv[1]

    # Diretório de saída: argumento opcional ou diretório do input
    if len(sys.argv) >= 3:
        output_dir = sys.argv[2]
    else:
        output_dir = os.path.dirname(os.path.abspath(input_path))

    # ── Validações de infraestrutura ──
    if not os.path.isfile(input_path):
        logger.error("Arquivo de entrada não encontrado: %s", input_path)
        sys.exit(1)

    # Cria o diretório de saída se não existir
    os.makedirs(output_dir, exist_ok=True)

    # ── Execução do pipeline ──
    try:
        stats = process(input_path, output_dir)
        print_report(stats)
    except Exception as e:
        logger.error(
            "Erro fatal durante o processamento: %s: %s",
            type(e).__name__,
            e,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
