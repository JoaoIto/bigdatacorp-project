import gc
import json
import logging
import os
import shutil
import sys
import uuid
import threading
import queue
from typing import Any, Dict, IO, Optional

from reader import read_jsonl, IO_BUFFER_SIZE
from transformer import (
    run_validations,
    transform_club,
    transform_player,
)
from schema import CLUBS_HEADER, PLAYERS_HEADER
from writer import create_csv_writer
from checkpoint import CheckpointManager

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
    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    handler.setFormatter(formatter)
    
    if logging.root.hasHandlers():
        logging.root.handlers.clear()
        
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)

def sanitize_workspace(output_dir: str) -> None:
    if not os.path.exists(output_dir):
        return
        
    for item in os.listdir(output_dir):
        item_path = os.path.join(output_dir, item)
        if os.path.isfile(item_path) and item.endswith(".tmp"):
            os.remove(item_path)
            logger.info("Bootstrap Sanitization: Removido arquivo residual %s", item)
        elif os.path.isdir(item_path) and item.startswith(".tmp_run_"):
            shutil.rmtree(item_path)
            logger.info("Bootstrap Sanitization: Removido diretório residual %s", item)

# ──────────────────────────────────────────────────────────────
# Wrapper Thread-Safe para Estatísticas (Fase 4)
# ──────────────────────────────────────────────────────────────
class ThreadSafeStats(Dict[str, int]):
    """Protege o dicionário de estatísticas contra atualizações concorrentes."""
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.lock = threading.Lock()
        
    def __getitem__(self, key: str) -> int:
        with self.lock:
            return super().__getitem__(key)
            
    def __setitem__(self, key: str, value: int) -> None:
        with self.lock:
            super().__setitem__(key, value)
            
    def setdefault(self, key: str, default: Optional[int] = None) -> int:
        with self.lock:
            return super().setdefault(key, default)

# ──────────────────────────────────────────────────────────────
# Pipeline Principal Multithreaded
# ──────────────────────────────────────────────────────────────

def process(input_path: str, output_dir: str) -> Dict[str, int]:
    clubs_path = os.path.join(output_dir, "clubs.csv")
    players_path = os.path.join(output_dir, "players.csv")
    dlq_path = os.path.join(output_dir, "dlq_errors.txt")
    chk_path = os.path.join(output_dir, "pipeline.checkpoint")
    
    run_uuid = uuid.uuid4().hex
    tmp_run_dir = os.path.join(output_dir, f".tmp_run_{run_uuid}")
    os.makedirs(tmp_run_dir, exist_ok=True)
    
    clubs_tmp = os.path.join(tmp_run_dir, "clubs.csv")
    players_tmp = os.path.join(tmp_run_dir, "players.csv")
    dlq_tmp = os.path.join(tmp_run_dir, "dlq_errors.txt")

    logger.info("Iniciando processamento multithreaded...")
    logger.info("  Entrada:  %s", input_path)
    logger.info("  Saída:    %s", output_dir)

    stats = ThreadSafeStats({
        "linhas_lidas": 0,
        "linhas_vazias": 0,
        "linhas_json_invalido": 0,
        "linhas_dlq": 0,
        "clubes_filtrados": 0,
        "clubes_escritos": 0,
        "jogadores_escritos": 0,
        "erros_processamento": 0,
    })

    # Fase 3: Checkpointing e truncamento
    chk = CheckpointManager(chk_path)
    state = chk.load(input_path)
    
    start_offset = 0
    if state:
        start_offset = state.get("byte_offset", 0)
        logger.info("Checkpoint encontrado. Retomando do offset %d", start_offset)
        
        # Cria os arquivos temporários pré-truncados a partir dos originais se existissem
        # Na estratégia Atomic Directory Promotion, o diretório .tmp_run é limpo em falhas abortivas.
        # Mas para Exactly-Once e resume a meio, os arquivos originais parciais devem estar em `output_dir`.
        # Se usarmos Atomic Directory, o .tmp_run antigo foi apagado e perdemos o progresso?
        # A instrução: "Modifique a estratégia... os escritores devem gravar em arquivos temporários... f.truncate".
        # Se renomeamos atomicamente no fim, o checkpoint deve copiar o arquivo de progresso atual (que é temporário?)
        # Não, os arquivos temporários `.tmp` na Fase 3 substituem o `.tmp_run_` da Fase anterior se houver rollback?
        # A instrução 3 diz: "Nos arquivos de saída .tmp, abra-os e execute um fatiamento do excesso...".
        # Vamos criar e truncar. Se os arquivos não existirem, ignora.

    # Abre arquivos em modo "a" (append) e binário para o DLQ para evitar encoding problems, 
    # ou texto, mas usamos append mode para manter o truncamento intacto.
    clubs_fh, clubs_writer = create_csv_writer(clubs_tmp, CLUBS_HEADER)
    players_fh, players_writer = create_csv_writer(players_tmp, PLAYERS_HEADER)
    dlq_fh: Optional[IO[str]] = None
    try:
        dlq_fh = open(dlq_tmp, 'a', encoding='utf-8', buffering=IO_BUFFER_SIZE)
    except OSError:
        logger.warning("Não foi possível criar arquivo DLQ: %s", dlq_path)
        
    if state:
        clubs_fh.truncate(state.get("clubs_bytes_size", 0))
        players_fh.truncate(state.get("players_bytes_size", 0))
        if dlq_fh:
            dlq_fh.truncate(state.get("dlq_bytes_size", 0))

    # Fase 4: Filas Produtor-Consumidor
    input_queue: queue.Queue[Any] = queue.Queue(maxsize=1000)
    clubs_queue: queue.Queue[Any] = queue.Queue(maxsize=2000)
    players_queue: queue.Queue[Any] = queue.Queue(maxsize=2000)
    dlq_queue: queue.Queue[Any] = queue.Queue(maxsize=2000)

    # Aliasing
    _run_validations = run_validations
    _transform_club = transform_club
    _transform_player = transform_player
    _write_club = clubs_writer.writerow
    _write_player = players_writer.writerow

    # Thread 1: Produtor
    def producer_worker() -> None:
        try:
            # Callback insere diretamente na fila DLQ
            def dlq_cb(msg: str) -> None:
                dlq_queue.put(msg)
                
            for line_number, record, byte_offset in read_jsonl(input_path, stats, dlq_cb, start_offset):
                input_queue.put((line_number, record, byte_offset))
        except Exception as e:
            logger.error("Erro no produtor: %s", e)
        finally:
            input_queue.put(None)

    # Threads Consumidoras
    def clubs_writer_worker() -> None:
        while True:
            item = clubs_queue.get()
            if item is None:
                clubs_fh.flush()
                clubs_queue.task_done()
                break
            try:
                _write_club(item)
            finally:
                clubs_queue.task_done()

    def players_writer_worker() -> None:
        while True:
            item = players_queue.get()
            if item is None:
                players_fh.flush()
                players_queue.task_done()
                break
            try:
                _write_player(item)
            finally:
                players_queue.task_done()

    def dlq_writer_worker() -> None:
        while True:
            item = dlq_queue.get()
            if item is None:
                if dlq_fh: dlq_fh.flush()
                dlq_queue.task_done()
                break
            if dlq_fh:
                try:
                    dlq_fh.write(item)
                except OSError:
                    pass
            dlq_queue.task_done()

    threads = [
        threading.Thread(target=producer_worker, name="Producer", daemon=True),
        threading.Thread(target=clubs_writer_worker, name="ClubsWriter", daemon=True),
        threading.Thread(target=players_writer_worker, name="PlayersWriter", daemon=True),
        threading.Thread(target=dlq_writer_worker, name="DLQWriter", daemon=True),
    ]
    
    for t in threads:
        t.start()

    commit_success = False

    # Transformer rodando na Thread Principal
    try:
        gc.disable()
        gc_collect = gc.collect
        GC_INTERVAL = 100_000
        
        lines_processed = 0
        last_offset = start_offset
        
        while True:
            item = input_queue.get()
            if item is None:
                clubs_queue.put(None)
                players_queue.put(None)
                dlq_queue.put(None)
                input_queue.task_done()
                break
                
            line_number, record, byte_offset = item
            last_offset = byte_offset
            
            try:
                is_valid, reject_reason = _run_validations(record)
                if not is_valid:
                    stats["clubes_filtrados"] += 1
                    continue

                club_row = _transform_club(record)
                clubs_queue.put(club_row)
                stats["clubes_escritos"] += 1

                club_id = record.get("club_id")
                club_id = "" if club_id is None else str(club_id)
                players = record.get("players")

                if isinstance(players, list):
                    for player in players:
                        if isinstance(player, dict):
                            player_row = _transform_player(club_id, player)
                            players_queue.put(player_row)
                            stats["jogadores_escritos"] += 1

            except Exception as e:
                logger.warning("Linha %d: erro no processamento — %s: %s", line_number, type(e).__name__, e)
                stats["erros_processamento"] += 1
                
            finally:
                input_queue.task_done()
                lines_processed += 1

            # Checkpoint & GC a cada 100K registros
            if lines_processed % GC_INTERVAL == 0:
                gc_collect(0)
                
                # Para garantir a sincronização do offset no checkpoint,
                # precisamos que as queues estejam vazias e as escritas no disco feitas.
                # A espera é no `join()` das queues, que bloqueiam até que as threads leiam 
                # e façam task_done() de tudo o que foi enviado até agora.
                clubs_queue.join()
                players_queue.join()
                dlq_queue.join()
                
                clubs_fh.flush()
                players_fh.flush()
                if dlq_fh: dlq_fh.flush()
                
                chk.save(
                    input_path, 
                    last_offset, 
                    os.path.getsize(clubs_tmp),
                    os.path.getsize(players_tmp),
                    os.path.getsize(dlq_tmp) if dlq_fh else 0
                )

        # Espera que todas as threads consumam o Sentinel None (Teardown Sênior)
        for t in threads:
            t.join()
            
        commit_success = True

    finally:
        if not commit_success:
            # Em caso de aborto (ex: KeyboardInterrupt), forçar término limpo das threads
            # Esvaziar filas pode ser complexo, então injetamos o Sentinel de qualquer forma.
            # Filas cheias podem bloquear o put, mas usamos block=False e ignoramos erro.
            for q in (clubs_queue, players_queue, dlq_queue):
                try:
                    q.put_nowait(None)
                except queue.Full:
                    pass
            for t in threads:
                if t.is_alive():
                    t.join(timeout=0.5)
                    
        gc.enable()
        clubs_fh.close()
        players_fh.close()
        if dlq_fh:
            dlq_fh.close()
            
        if commit_success:
            if os.path.exists(clubs_tmp):
                os.replace(clubs_tmp, clubs_path)
            if os.path.exists(players_tmp):
                os.replace(players_tmp, players_path)
            if os.path.exists(dlq_tmp):
                os.replace(dlq_tmp, dlq_path)
            chk.clear()
                
        if os.path.exists(tmp_run_dir):
            shutil.rmtree(tmp_run_dir)

    return stats


def print_report(stats: Dict[str, int]) -> None:
    logger.info("=" * 50)
    logger.info("Processamento concluído com sucesso.")
    logger.info("  Linhas lidas:              %d", stats.get("linhas_lidas", 0))
    logger.info("  Linhas vazias ignoradas:   %d", stats.get("linhas_vazias", 0))
    logger.info("  Linhas JSON inválido:      %d", stats.get("linhas_json_invalido", 0))
    logger.info("  Linhas DLQ (auditoria): %d", stats.get("linhas_dlq", 0))
    logger.info("  Clubes filtrados:          %d", stats.get("clubes_filtrados", 0))
    logger.info("  Erros de processamento:    %d", stats.get("erros_processamento", 0))
    logger.info("  Clubes escritos:           %d", stats.get("clubes_escritos", 0))
    logger.info("  Jogadores escritos:        %d", stats.get("jogadores_escritos", 0))
    logger.info("=" * 50)


def main() -> None:
    setup_logging()

    if len(sys.argv) < 2:
        logger.error("Uso: python main.py <arquivo_entrada.jsonl> [diretório_saída]")
        sys.exit(1)

    input_path = sys.argv[1]

    if len(sys.argv) >= 3:
        output_dir = sys.argv[2]
    else:
        output_dir = os.path.dirname(os.path.abspath(input_path))

    if not os.path.isfile(input_path):
        logger.error("Arquivo de entrada não encontrado: %s", input_path)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    sanitize_workspace(output_dir)

    try:
        stats = process(input_path, output_dir)
        print_report(stats)
    except Exception as e:
        logger.error("Erro fatal durante o processamento: %s: %s", type(e).__name__, e)
        sys.exit(1)

if __name__ == "__main__":
    main()
