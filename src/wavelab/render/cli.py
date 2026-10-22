"""Replay a local FigureSpec without UI or AI services."""
import argparse
from pathlib import Path
import sys

from wavelab.domain.figure import load_spec
from .engine import export_figure, render_figure, reopen_datasets


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Render local FigureSpec JSON to PDF/PNG/SVG")
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        spec = load_spec(args.spec)
        result = render_figure(spec, reopen_datasets(spec, base_dir=args.spec.resolve().parent))
        for fmt in ("pdf", "png", "svg"):
            print(export_figure(result, args.output_dir / f"{args.spec.stem}.{fmt}"))
        for message in result.warnings:
            print(f"Warning: {message}")
        result.figure.clear()
        return 0
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
