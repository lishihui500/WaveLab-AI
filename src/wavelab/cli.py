"""Read-only inspection; JSON is written to stdout, never to source files."""
import argparse
import json
import sys

from .ingest import ParseError, parse_file


def inspect(path):
    dataset = parse_file(path)
    result = dataset.manifest.model_dump(mode="json")
    result["channel_statistics"] = [
        {"source_column_index": c.source_column_index,
         "min": float(dataset.values(c.channel_id).min()),
         "max": float(dataset.values(c.channel_id).max())}
        for c in dataset.manifest.channels
    ]
    return result


def main():
    # Windows pipes may default to a legacy code page: JSON output is always UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Inspect PSCAD TXT/CSV files without modifying them")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    reports, failed = [], False
    for path in args.paths:
        try:
            reports.append(inspect(path))
        except (ParseError, OSError, ValueError) as exc:
            reports.append({"source_path": path, "error": str(exc)})
            failed = True
    print(json.dumps(reports, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
