#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from converter import LoadOptions, open_page, sanitize_filename
from output import save_pdf, save_markdown
from helpers import normalize_url

OUTPUT_ROOT = Path(__file__).parent.parent / "output"


def resolve_output_path(
    url: str, fmt: str, collection: str | None, output_root: Path
) -> Path:
    stem = sanitize_filename(url)
    suffix = ".pdf" if fmt == "pdf" else ".md"
    folder = output_root / collection.replace(" ", "_") if collection else output_root
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (stem + suffix)


def parse_batch_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Batch file not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def _process_url(
    url: str,
    fmt: str,
    collection: str | None,
    options: LoadOptions,
    output_root: Path,
) -> None:
    url = normalize_url(url)
    out_path = resolve_output_path(url, fmt, collection, output_root)
    print(f"Converting: {url}")
    print(f"  Output:    {out_path}")
    with open_page(url, options) as page:
        if fmt == "pdf":
            save_pdf(page, out_path)
        else:
            save_markdown(page, out_path)
    print("  Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert web pages to PDF or Markdown with paywall bypass.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py https://example.com/article
  python cli.py https://example.com/article --format md --collection "My Course"
  python cli.py --batch urls.txt --format md --collection "Salesforce Docs"
        """,
    )
    parser.add_argument("url", nargs="?", help="Single URL to convert")
    parser.add_argument("--batch", metavar="FILE", help="Text file with one URL per line")
    parser.add_argument("--format", choices=["pdf", "md"], default="pdf", help="Output format (default: pdf)")
    parser.add_argument("--collection", metavar="NAME", help="Group outputs into a named subfolder under output/")
    parser.add_argument("--output-dir", metavar="DIR", default=str(OUTPUT_ROOT), help=f"Output root directory (default: {OUTPUT_ROOT})")
    parser.add_argument("--no-headless", dest="headless", action="store_false", default=True, help="Show browser window")
    parser.add_argument("--no-extension", action="store_true", help="Skip paywall-removal Chrome extension")
    parser.add_argument("--no-images", action="store_true", help="Block images for faster loading")
    parser.add_argument("--freedium", action="store_true", help="Route Medium.com articles through Freedium proxy")

    args = parser.parse_args()

    if not args.url and not args.batch:
        parser.error("Provide either a URL or --batch FILE")
    if args.url and args.batch:
        parser.error("Provide either a URL or --batch FILE, not both")

    options = LoadOptions(
        headless=args.headless,
        use_extension=not args.no_extension,
        block_images=args.no_images,
        use_freedium=args.freedium,
    )
    output_root = Path(args.output_dir)

    if args.batch:
        urls = parse_batch_file(Path(args.batch))
        print(f"Batch: {len(urls)} URL(s) to process.")
        errors: list[tuple[str, str]] = []
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}]")
            try:
                _process_url(url, args.format, args.collection, options, output_root)
            except Exception as e:
                print(f"  ERROR: {e}")
                errors.append((url, str(e)))
        if errors:
            print(f"\n{len(errors)} URL(s) failed:")
            for url, err in errors:
                print(f"  {url}: {err}")
            sys.exit(1)
    else:
        try:
            _process_url(args.url, args.format, args.collection, options, output_root)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
