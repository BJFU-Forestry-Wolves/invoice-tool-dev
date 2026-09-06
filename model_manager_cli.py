from __future__ import annotations

import argparse
from pathlib import Path

from order_date.model_manager import download_and_install, inspect_models


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCR 模型管理")
    parser.add_argument("command", choices=("status", "download", "verify"))
    parser.add_argument("--source", choices=("auto", "github", "mirror"), default="auto")
    parser.add_argument("--models-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "download":
        status = download_and_install(
            source=args.source,
            models_dir=args.models_dir,
            progress=lambda event: print(
                f"[{event.get('source', '')}] {event.get('current', 0)}/{event.get('total', 0)} "
                f"{event.get('current_file', '')}"
            ),
        )
    else:
        status = inspect_models(args.models_dir)
    print(f"{'READY' if status.ready else 'NOT_READY'}: {status.message}")
    print(f"模型目录: {status.models_dir}")
    return 0 if status.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
