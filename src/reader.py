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

import os
import json
import logging
import re
from typing import Any, Callable, Dict, Generator, IO, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Fase 2: Regex Estrito Plano para CPF e MAX_LINE_BYTES ──
RE_CPF_FLAT = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
MAX_LINE_BYTES: int = 10 * 1024 * 1024  # 10 MB limit por linha para previnir OOM

# Buffer de 256 KB para reduzir syscalls de I/O (ADR-008)
IO_BUFFER_SIZE: int = 262144

def mask_pii_linear(text: str) -> str:
    """Mascaramento O(N) linear para mitigar ReDoS."""
    res = []
    i = 0
    n = len(text)
    # Lista de separadores baseada em JSON e espaços
    separators = {' ', '"', "'", '{', '}', '[', ']', ',', '\\', '\n', '\r'}
    
    while i < n:
        idx = text.find('@', i)
        if idx == -1:
            res.append(text[i:])
            break
            
        start = idx
        while start > i and text[start-1] not in separators:
            start -= 1
            
        end = idx
        while end < n and text[end] not in separators:
            end += 1
            
        domain_part = text[idx:end]
        if "." in domain_part:
            res.append(text[i:start])
            res.append("[EMAIL_OCULTO]")
            i = end
        else:
            res.append(text[i:idx+1])
            i = idx + 1
            
    masked = "".join(res)
    return RE_CPF_FLAT.sub("[CPF_OCULTO]", masked)


def read_jsonl(
    filepath: str,
    stats: Optional[Dict[str, int]] = None,
    dlq_callback: Optional[Callable[[str], None]] = None,
    start_offset: int = 0,
) -> Generator[Tuple[int, Dict[str, Any], int], None, None]:
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
        tuple[int, dict, int]: (número_da_linha, registro_parseado, byte_offset)
            - número_da_linha é 1-indexed.
            - registro_parseado é o dict resultante de json.loads().
            - byte_offset é a posição atual em disco após a leitura.

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
        filepath, 'rb',
        buffering=IO_BUFFER_SIZE,
    ) as f:
        # Se houver checkpoint (start_offset > 0), pula direto para lá.
        if start_offset > 0:
            f.seek(start_offset)
        else:
            # Pula BOM do UTF-8 se existir no início do arquivo
            bom = f.read(3)
            if bom != b'\xef\xbb\xbf':
                f.seek(0)

        # ── Micro-otimização: LOAD_FAST em vez de LOAD_ATTR ──
        _parse_json = json.loads

        line_number = 0
        while True:
            # ── Fase 2: Proteção de I/O contra linhas hiper-massivas ──
            raw_line_bytes = f.readline(MAX_LINE_BYTES)
            if not raw_line_bytes:
                break
                
            line_number += 1
            stats['linhas_lidas'] += 1

            if len(raw_line_bytes) == MAX_LINE_BYTES and not raw_line_bytes.endswith(b'\n'):
                logger.critical("Linha %d ultrapassou 10MB e será descartada.", line_number)
                # Escaneamento linear em blocos de 4KB até achar o delimitador
                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    if b'\n' in chunk:
                        idx = chunk.index(b'\n')
                        f.seek(-(len(chunk) - idx - 1), os.SEEK_CUR)
                        break
                stats['linhas_json_invalido'] += 1
                continue

            raw_line = raw_line_bytes.decode('utf-8', errors='replace')
            stripped = raw_line.strip()

            # ── Nível 1: Linhas vazias / whitespace-only ──
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
                _write_dlq(dlq_callback, line_number, "JSON_MALFORMADO", stripped, stats)
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
                    dlq_callback, line_number,
                    f"TIPO_INVALIDO:{type(record).__name__}",
                    stripped, stats,
                )
                continue

            # ── Registro válido — yield para o próximo estágio ──
            yield line_number, record, f.tell()


def _write_dlq(
    dlq_callback: Optional[Callable[[str], None]],
    line_number: int,
    reason: str,
    raw_line: str,
    stats: Dict[str, int],
) -> None:
    """Grava uma linha rejeitada na Dead Letter Queue (ADR-009).

    Formato de saída:
        [LINHA:4][JSON_MALFORMADO] isto nao e json

    Args:
        dlq_callback: Função callback para despachar o erro. Se None, no-op.
        line_number: Número da linha no arquivo original (1-indexed).
        reason: Motivo do descarte (ex: 'JSON_MALFORMADO', 'TIPO_INVALIDO:list').
        raw_line: A string original bruta da linha rejeitada.
        stats: Dicionário mutável de contadores (incrementa 'linhas_dlq').
    """
    if dlq_callback is None:
        return
        
    # Data Masking Linear (Compliance LGPD) Fase 2
    masked_line = mask_pii_linear(raw_line)
    
    try:
        dlq_callback(f"[LINHA:{line_number}][{reason}] {masked_line}\n")
        stats['linhas_dlq'] += 1
    except Exception as e:
        logger.warning(
            "Falha ao gravar DLQ para linha %d — continuando processamento: %s",
            line_number, e
        )
