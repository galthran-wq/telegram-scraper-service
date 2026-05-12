from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from src.config import settings
from src.core.session_pool import SQLITE_SESSION_EXT, STRING_SESSION_EXT


def main() -> int:
    sessions_dir = Path(settings.sessions_dir)
    if not sessions_dir.exists():
        print(json.dumps([]))
        return 0
    entries = []
    for p in sorted(sessions_dir.iterdir()):
        if p.suffix not in (SQLITE_SESSION_EXT, STRING_SESSION_EXT):
            continue
        stat = p.stat()
        entries.append(
            {
                "name": p.stem,
                "filename": p.name,
                "kind": "string" if p.suffix == STRING_SESSION_EXT else "sqlite",
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
            }
        )
    print(json.dumps(entries, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
