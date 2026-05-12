from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.config import settings
from src.core.session_pool import SQLITE_SESSION_EXT, STRING_SESSION_EXT


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    args = parser.parse_args()

    sessions_dir = Path(settings.sessions_dir)
    removed: list[str] = []
    for ext in (STRING_SESSION_EXT, SQLITE_SESSION_EXT):
        p = sessions_dir / f"{args.name}{ext}"
        if p.exists():
            p.unlink()
            removed.append(p.name)
    journal = sessions_dir / f"{args.name}.session-journal"
    if journal.exists():
        journal.unlink()
        removed.append(journal.name)

    if not removed:
        print(json.dumps({"error": f"no session files found for '{args.name}'"}), file=sys.stderr)
        return 1
    print(json.dumps({"removed": removed}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
