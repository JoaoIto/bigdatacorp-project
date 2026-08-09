"""
reader.py — Módulo de leitura JSONL em streaming.

Implementa o padrão Generator (yield) para leitura linha a linha,
garantindo complexidade de espaço O(1) independente do tamanho do arquivo.

Referência arquitetural: spec/architecture.md §2 (Estágio 1: Reader)
Decisão arquitetural: spec/decisions.md ADR-002 (Erros de Estrutura)
"""

import json
import logging

logger = logging.getLogger(__name__)


def read_jsonl(filepath, stats=None):
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

    with open(filepath, 'r', encoding='utf-8') as f:
        for line_number, raw_line in enumerate(f, start=1):
            stats['linhas_lidas'] += 1

            # ── Nível 1: Linhas vazias / whitespace-only ──
            stripped = raw_line.strip()
            if not stripped:
                stats['linhas_vazias'] += 1
                continue

            # ── Nível 2: JSON malformado ──
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Linha %d: JSON malformado — %s",
                    line_number,
                    e,
                )
                stats['linhas_json_invalido'] += 1
                continue

            # ── Nível 3: Tipo inesperado (JSON válido mas não é dict) ──
            if not isinstance(record, dict):
                logger.warning(
                    "Linha %d: esperado objeto JSON (dict), obteve %s",
                    line_number,
                    type(record).__name__,
                )
                stats['linhas_json_invalido'] += 1
                continue

            # ── Registro válido — yield para o próximo estágio ──
            yield line_number, record
