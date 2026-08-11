import typing
from typing import Any, Dict, Generator, Protocol

if typing.TYPE_CHECKING:
    # Para mypy
    pass

class DataReader(Protocol):
    """Protocolo estrito para Leitores de Dados (DIP)."""
    def read_records(self) -> Generator[tuple[int, Dict[str, Any]], None, None]:
        ...

class DataWriter(Protocol):
    """Protocolo estrito para Escritores de Dados (DIP)."""
    def write_record(self, record: tuple[Any, ...]) -> None:
        ...
