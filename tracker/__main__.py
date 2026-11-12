"""Command line.

    python -m tracker run     # daily run: fetch, build, status, Issue
    python -m tracker build   # rebuild data/history.csv from data/raw/ only
"""

import sys

from . import history, pipeline


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "run"
    if cmd == "build":
        rows = history.build(pipeline.RAW, pipeline.HISTORY)
        print(f"wrote {pipeline.HISTORY.relative_to(pipeline.ROOT)} ({len(rows)} rows)")
    elif cmd == "run":
        st = pipeline.run()
        print(f"items: {st['items']}  days: {st['days_with_success']}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
