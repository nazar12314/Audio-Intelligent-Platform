"""Stand-ins for the analysis child process (importable by spawned processes)."""

import os
import time
from multiprocessing.connection import Connection


def hang(conn: Connection, source: str, target: str, max_duration_s: int) -> None:
    time.sleep(3600)


def crash(conn: Connection, source: str, target: str, max_duration_s: int) -> None:
    os._exit(3)  # like a segfault in native code: no result, no cleanup
