"""
writer.py — Módulo de escrita CSV com compliance RFC 4180.

Encapsula a criação e configuração dos csv.writers para os arquivos
clubs.csv e players.csv, garantindo:
- Encoding UTF-8 (sem BOM)
- Separador vírgula
- Escape correto de campos com vírgulas, aspas e quebras de linha
- Terminador de linha CRLF (padrão RFC 4180)

Referência arquitetural: spec/architecture.md §2 (Estágio 4: Writer)
Decisão arquitetural: spec/decisions.md ADR-001 (RFC 4180 via csv nativo)
"""

import csv
import logging
from typing import Any, List, TextIO, Tuple

logger = logging.getLogger(__name__)



def create_csv_writer(filepath: str, header: List[str]) -> Tuple[TextIO, Any]:
    """Cria um arquivo CSV e retorna o handle e o writer configurado.

    O writer é configurado com o dialect padrão 'excel' do Python, que
    já implementa RFC 4180:
    - delimiter = ','
    - quotechar = '"'
    - quoting = QUOTE_MINIMAL (aspas apenas quando necessário)
    - doublequote = True (aspas internas são duplicadas)
    - lineterminator = '\\r\\n' (CRLF)

    IMPORTANTE: O arquivo é aberto com newline='' conforme exigido pela
    documentação do módulo csv do Python. Isso evita a duplicação de \\r
    no Windows (\\r\\r\\n), pois o csv.writer já insere \\r\\n.

    Args:
        filepath (str): Caminho do arquivo CSV de saída.
        header (list[str]): Lista com os nomes das colunas do cabeçalho.

    Returns:
        tuple[file, csv.writer]: Tupla contendo:
            - file_handle: O objeto de arquivo aberto (o chamador é
              responsável por fechá-lo).
            - writer: O csv.writer configurado e pronto para uso.

    Raises:
        PermissionError: Se não houver permissão de escrita.
        OSError: Para outros erros de I/O.

    Example:
        >>> fh, writer = create_csv_writer('clubs.csv', CLUBS_HEADER)
        >>> writer.writerow(['SCCP', 'Corinthians', ...])
        >>> fh.close()
    """
    file_handle = open(filepath, 'w', newline='', encoding='utf-8')
    writer = csv.writer(file_handle)

    # Escreve o cabeçalho como primeira linha do CSV
    writer.writerow(header)
    logger.debug("CSV criado: %s (colunas: %d)", filepath, len(header))

    return file_handle, writer
