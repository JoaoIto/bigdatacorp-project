import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class CheckpointManager:
    """Gerenciador de checkpointing para o pipeline O(1) com semântica Exactly-Once."""
    
    def __init__(self, checkpoint_filepath: str):
        self.filepath = checkpoint_filepath
        
    def save(self, input_filepath: str, byte_offset: int, clubs_size: int, players_size: int, dlq_size: int) -> None:
        """Salva o estado do processo atomicamente usando os.replace."""
        state = {
            "input_filepath": input_filepath,
            "byte_offset": byte_offset,
            "clubs_bytes_size": clubs_size,
            "players_bytes_size": players_size,
            "dlq_bytes_size": dlq_size
        }
        
        tmp_filepath = self.filepath + ".tmp"
        try:
            with open(tmp_filepath, "w", encoding="utf-8") as f:
                json.dump(state, f)
            # Operação atômica em sistemas POSIX e Windows modernos
            os.replace(tmp_filepath, self.filepath)
        except OSError as e:
            logger.warning("Falha ao salvar checkpoint em %s: %s", self.filepath, e)
            if os.path.exists(tmp_filepath):
                try:
                    os.remove(tmp_filepath)
                except OSError:
                    pass

    def load(self, input_filepath: str) -> Optional[Dict[str, Any]]:
        """Carrega o checkpoint, garantindo que pertence ao mesmo arquivo de entrada."""
        if not os.path.exists(self.filepath):
            return None
            
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                state = json.load(f)
                
            if state.get("input_filepath") == input_filepath:
                return state
            else:
                logger.info("Checkpoint pertence a um arquivo diferente. Ignorando.")
                return None
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Falha ao ler checkpoint %s: %s", self.filepath, e)
            return None

    def clear(self) -> None:
        """Remove o arquivo de checkpoint após o sucesso total da pipeline."""
        if os.path.exists(self.filepath):
            try:
                os.remove(self.filepath)
            except OSError as e:
                logger.warning("Não foi possível apagar arquivo de checkpoint: %s", e)
