"""
main.py — Orquestrador do pipeline de processamento batch.

Ponto de entrada do programa. Responsabilidades:
- Parse de argumentos CLI (caminho do arquivo de entrada e diretório de saída)
- Configuração do sistema de logging
- Composição e execução do pipeline: Reader → Writer
- Gerenciamento do ciclo de vida dos arquivos (open/close via context manager)
- Contadores e relatório final de processamento

Uso:
    python src/main.py <arquivo_entrada.jsonl> [diretório_saída]

Referência arquitetural: spec/architecture.md §2 e §3
"""

import logging
import os
import sys

from reader import read_jsonl
from writer import CLUBS_HEADER, PLAYERS_HEADER, create_csv_writer

# ──────────────────────────────────────────────────────────────
# Configuração de Logging
# ──────────────────────────────────────────────────────────────

logger = logging.getLogger("bigdatacorp")


def setup_logging():
    """Configura o sistema de logging com formato padronizado.

    Nível INFO para o fluxo normal (início, fim, contadores).
    Nível WARNING para registros ignorados (JSON malformado, tipo errado).
    Nível ERROR para falhas de infraestrutura (arquivo não encontrado, I/O).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ──────────────────────────────────────────────────────────────
# Extração bruta de campos (sem regras de negócio)
#
# Nesta fase (Core I/O), fazemos apenas extração direta dos
# campos do JSON para provar que o pipeline funciona end-to-end.
# As transformações (datas, cores, filtro) virão na Fase 3.
# ──────────────────────────────────────────────────────────────

def safe_get(record, key, default=""):
    """Extrai um valor do dict com fallback seguro.

    Retorna o valor como string se presente e não-None.
    Retorna default se a chave estiver ausente ou o valor for None.

    Args:
        record (dict): O dicionário fonte.
        key (str): A chave a buscar.
        default (str): Valor padrão se ausente ou None.

    Returns:
        str: O valor extraído como string, ou default.
    """
    value = record.get(key)
    if value is None:
        return default
    return str(value)


def extract_club_row(record):
    """Extrai os campos do clube como uma lista de strings (sem formatação).

    Nesta fase, os campos são extraídos diretamente — sem formatação
    de datas, sem junção de cores com pipe, sem filtro de campeonato.
    Esses tratamentos serão adicionados no módulo transformer.py (Fase 3).

    Args:
        record (dict): O dict de um clube parseado do JSONL.

    Returns:
        list[str]: Lista de 11 strings na ordem do cabeçalho de clubs.csv.
    """
    # colors: converte lista para representação bruta por enquanto
    colors = record.get('colors')
    if isinstance(colors, list):
        colors_str = str(colors)
    else:
        colors_str = safe_get(record, 'colors')

    return [
        safe_get(record, 'club_id'),
        safe_get(record, 'name'),
        safe_get(record, 'championship'),
        safe_get(record, 'founding_date'),
        safe_get(record, 'city'),
        safe_get(record, 'state'),
        safe_get(record, 'country'),
        safe_get(record, 'stadium'),
        safe_get(record, 'president'),
        safe_get(record, 'nickname'),
        colors_str,
    ]


def extract_player_row(club_id, player):
    """Extrai os campos de um jogador como uma lista de strings (sem formatação).

    Args:
        club_id (str): O club_id do clube pai.
        player (dict): O dict de um jogador do array 'players'.

    Returns:
        list[str]: Lista de 8 strings na ordem do cabeçalho de players.csv.
    """
    return [
        club_id,
        safe_get(player, 'player_id'),
        safe_get(player, 'name'),
        safe_get(player, 'age'),
        safe_get(player, 'goals'),
        safe_get(player, 'debut_date'),
        safe_get(player, 'position'),
        safe_get(player, 'shirt_number'),
    ]


# ──────────────────────────────────────────────────────────────
# Pipeline Principal
# ──────────────────────────────────────────────────────────────

def process(input_path, output_dir):
    """Executa o pipeline completo de processamento JSONL → CSV.

    Lê o arquivo JSONL em streaming (O(1) de memória), extrai os
    campos de cada registro e escreve imediatamente nos CSVs.

    Args:
        input_path (str): Caminho para o arquivo JSONL de entrada.
        output_dir (str): Diretório onde os CSVs serão escritos.

    Returns:
        dict: Dicionário com os contadores de processamento.
    """
    clubs_path = os.path.join(output_dir, 'clubs.csv')
    players_path = os.path.join(output_dir, 'players.csv')

    logger.info("Iniciando processamento...")
    logger.info("  Entrada:  %s", input_path)
    logger.info("  Saída:    %s", output_dir)

    # Contadores compartilhados com o reader (via dict mutável)
    stats = {
        'linhas_lidas': 0,
        'linhas_vazias': 0,
        'linhas_json_invalido': 0,
        'clubes_escritos': 0,
        'jogadores_escritos': 0,
        'erros_processamento': 0,
    }

    # Abre os dois arquivos de saída
    clubs_fh, clubs_writer = create_csv_writer(clubs_path, CLUBS_HEADER)
    players_fh, players_writer = create_csv_writer(players_path, PLAYERS_HEADER)

    try:
        # Pipeline: Reader (generator) → processamento → Writer
        for line_number, record in read_jsonl(input_path, stats):
            try:
                # ── Extrair e escrever o clube ──
                club_row = extract_club_row(record)
                clubs_writer.writerow(club_row)
                stats['clubes_escritos'] += 1

                # ── Extrair e escrever cada jogador (1:N) ──
                club_id = safe_get(record, 'club_id')
                players = record.get('players')

                if isinstance(players, list):
                    for player in players:
                        if isinstance(player, dict):
                            player_row = extract_player_row(club_id, player)
                            players_writer.writerow(player_row)
                            stats['jogadores_escritos'] += 1

            except Exception as e:
                # Tolerância a falhas: erro em um registro não aborta o pipeline
                logger.warning(
                    "Linha %d: erro no processamento — %s: %s",
                    line_number,
                    type(e).__name__,
                    e,
                )
                stats['erros_processamento'] += 1
                continue

    finally:
        # Garante fechamento dos arquivos mesmo em caso de erro
        clubs_fh.close()
        players_fh.close()

    return stats


def print_report(stats):
    """Exibe o relatório final de processamento no console.

    Args:
        stats (dict): Dicionário com os contadores.
    """
    logger.info("=" * 50)
    logger.info("Processamento concluído com sucesso.")
    logger.info("  Linhas lidas:              %d", stats.get('linhas_lidas', 0))
    logger.info("  Linhas vazias ignoradas:   %d", stats.get('linhas_vazias', 0))
    logger.info("  Linhas JSON inválido:      %d", stats.get('linhas_json_invalido', 0))
    logger.info("  Erros de processamento:    %d", stats.get('erros_processamento', 0))
    logger.info("  Clubes escritos:           %d", stats.get('clubes_escritos', 0))
    logger.info("  Jogadores escritos:        %d", stats.get('jogadores_escritos', 0))
    logger.info("=" * 50)


# ──────────────────────────────────────────────────────────────
# Ponto de Entrada CLI
# ──────────────────────────────────────────────────────────────

def main():
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


if __name__ == '__main__':
    main()
