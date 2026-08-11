"""
reader.py — Módulo de leitura JSONL em streaming.

Implementa o padrão Generator (yield) para leitura linha a linha,
garantindo complexidade de espaço O(1) independente do tamanho do arquivo.

Referência arquitetural: spec/architecture.md §2 (Estágio 1: Reader)
Decisão arquitetural: spec/decisions.md ADR-002 (Erros de Estrutura)
Decisão arquitetural: spec/decisions.md ADR-007 (Resiliência de Encoding)
Decisão arquitetural: spec/decisions.md ADR-008 (Buffer Tuning I/O)
Decisão arquitetural: spec/decisions.md ADR-009 (Dead Letter Queue)
"""

import json
import logging
from typing import Any, Dict, Generator, IO, Optional, Tuple

logger = logging.getLogger(__name__)

# Buffer de 256 KB para reduzir syscalls de I/O (ADR-008)
IO_BUFFER_SIZE: int = 262144


def read_jsonl(
    filepath: str,
    stats: Optional[Dict[str, int]] = None,
    dlq_writer: Optional[IO[str]] = None,
) -> Generator[Tuple[int, Dict[str, Any]], None, None]:
    """Generator que lê um arquivo JSONL linha a linha com tolerância a falhas.

    Faz yield de tuplas (line_number, record) para cada linha que contenha
    um objeto JSON válido. Linhas vazias e JSONs malformados são ignorados
    com log de warning — o pipeline nunca aborta por um registro ruim.

    Este generator garante O(1) de memória: apenas uma linha e seu dict
    parseado existem em memória por vez.

    Args:
        filepath (str): Caminho absoluto ou relativo para o arquivo JSONL.
        stats (dict, optional): Dicionário mutável para acumular contadores
            de processamento. Se None, um dict interno é criado (mas o
            chamador não terá acesso a ele). Chaves atualizadas:
            - 'linhas_lidas': total de linhas percorridas
            - 'linhas_vazias': linhas em branco ignoradas
            - 'linhas_json_invalido': linhas com JSON malformado ou tipo errado
            - 'linhas_dlq': linhas gravadas na Dead Letter Queue
        dlq_writer (IO[str], optional): File handle aberto para escrita
            da Dead Letter Queue. Se fornecido, linhas rejeitadas são
            gravadas com prefixo auditável (ADR-009). Se None, linhas
            rejeitadas são apenas logadas e descartadas.

    Yields:
        tuple[int, dict]: (número_da_linha, registro_parseado)
            - número_da_linha é 1-indexed.
            - registro_parseado é o dict resultante de json.loads().

    Raises:
        FileNotFoundError: Se o arquivo não existir.
        PermissionError: Se não houver permissão de leitura.
        OSError: Para outros erros de I/O na abertura do arquivo.

    Example:
        >>> stats = {}
        >>> for line_num, record in read_jsonl('dados.jsonl', stats):
        ...     print(record['club_id'])
        >>> print(f"Total lido: {stats['linhas_lidas']}")
    """
    if stats is None:
        stats = {}

    # Inicializa contadores para garantir que existem mesmo com arquivo vazio
    stats.setdefault('linhas_lidas', 0)
    stats.setdefault('linhas_vazias', 0)
    stats.setdefault('linhas_json_invalido', 0)
    stats.setdefault('linhas_dlq', 0)

    with open(
        filepath, 'r',
        encoding='utf-8-sig',
        errors='replace',
        buffering=IO_BUFFER_SIZE,
    ) as f:
        # ── Micro-otimização: LOAD_FAST em vez de LOAD_ATTR ──
        # Aliasing de funções frequentes para variáveis locais reduz
        # lookups de atributo no hot loop (cada chamada evita 1 LOAD_ATTR).
        _parse_json = json.loads

        for line_number, raw_line in enumerate(f, start=1):
            stats['linhas_lidas'] += 1

            # ── Nível 1: Linhas vazias / whitespace-only ──
            stripped = raw_line.strip()
            if not stripped:
                stats['linhas_vazias'] += 1
                continue

            # ── Nível 2: JSON malformado ──
            try:
                record = _parse_json(stripped)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Linha %d: JSON malformado — %s",
                    line_number,
                    e,
                )
                stats['linhas_json_invalido'] += 1
                _write_dlq(dlq_writer, line_number, "JSON_MALFORMADO", stripped, stats)
                continue

            # ── Nível 3: Tipo inesperado (JSON válido mas não é dict) ──
            if not isinstance(record, dict):
                logger.warning(
                    "Linha %d: esperado objeto JSON (dict), obteve %s",
                    line_number,
                    type(record).__name__,
                )
                stats['linhas_json_invalido'] += 1
                _write_dlq(
                    dlq_writer, line_number,
                    f"TIPO_INVALIDO:{type(record).__name__}",
                    stripped, stats,
                )
                continue

            # ── Registro válido — yield para o próximo estágio ──
            yield line_number, record


def _write_dlq(
    dlq_writer: Optional[IO[str]],
    line_number: int,
    reason: str,
    raw_line: str,
    stats: Dict[str, int],
) -> None:
    """Grava uma linha rejeitada na Dead Letter Queue (ADR-009).

    Formato de saída:
        [LINHA:4][JSON_MALFORMADO] isto nao e json

    Args:
        dlq_writer: File handle aberto para escrita. Se None, operação é no-op.
        line_number: Número da linha no arquivo original (1-indexed).
        reason: Motivo do descarte (ex: 'JSON_MALFORMADO', 'TIPO_INVALIDO:list').
        raw_line: A string original bruta da linha rejeitada.
        stats: Dicionário mutável de contadores (incrementa 'linhas_dlq').
    """
    if dlq_writer is None:
        return
    try:
        dlq_writer.write(f"[LINHA:{line_number}][{reason}] {raw_line}\n")
        stats['linhas_dlq'] += 1
    except OSError:
        # Falha na escrita da DLQ não deve abortar o pipeline principal
        logger.warning(
            "Falha ao gravar DLQ para linha %d — continuando processamento",
            line_number,
        )
