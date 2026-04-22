import sys
from pathlib import Path
from typing import List

from pypdf import PdfWriter  # Requires: pip install pypdf


def combine_pdfs(pdf_paths: List[str | Path], output_path: str | Path) -> None:
    """
    Combine multiple PDF files into one.

    Args:
        pdf_paths (List[str | Path]): List of input PDF file paths.
        output_path (str | Path): Path for the output combined PDF.

    Raises:
        FileNotFoundError: If any input PDF doesn't exist.
        ValueError: If merging fails (e.g., corrupted PDFs).
    """
    merger = PdfWriter()

    for pdf in pdf_paths:
        pdf_path = Path(pdf)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        try:
            merger.append(pdf_path)
        except Exception as e:
            raise ValueError(f"Failed to read {pdf_path}: {e}")

    output_path = Path(output_path)
    try:
        with output_path.open("wb") as output_file:
            merger.write(output_file)
        print(f"Successfully combined {len(pdf_paths)} PDFs into {output_path}")
    except Exception as e:
        raise ValueError(f"Failed to write output PDF: {e}")
    finally:
        merger.close()


def combine_pdfs_in_folder(folder_path: str | Path = ".", recursive: bool = False, output_name: str = "combined.pdf") -> None:
    """
    Combine all PDFs in a folder (optionally recursive) into a single file.

    Args:
        folder_path (str | Path): Path to the folder to scan. Defaults to current directory.
        recursive (bool): If True, scan subfolders too. Defaults to False.
        output_name (str): Name of the output PDF file. Defaults to 'combined.pdf'.

    Raises:
        ValueError: If no PDFs found or other issues.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise ValueError(f"Invalid folder: {folder}")

    # Find all PDFs (case-insensitive)
    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdf_files = sorted([p for p in folder.glob(pattern) if p.is_file()], key=lambda x: x.name.lower())

    if not pdf_files:
        raise ValueError(f"No PDF files found in {folder}")

    # Exclude existing output if it matches
    output_path = folder / output_name
    pdf_paths = [p for p in pdf_files if p.resolve() != output_path.resolve()]

    if not pdf_paths:
        raise ValueError("No PDFs to merge after filtering output file.")

    combine_pdfs(pdf_paths, output_path)


if __name__ == "__main__":
    # CLI usage:
    # - No args: Combine all PDFs in current folder (non-recursive) into combined.pdf
    # - python combine_pdfs.py /path/to/folder [recursive] [output_name]
    #   e.g., python combine_pdfs.py . True myoutput.pdf
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    recursive = sys.argv[2].lower() == "true" if len(sys.argv) > 2 else False
    output_name = sys.argv[3] if len(sys.argv) > 3 else "combined.pdf"

    try:
        combine_pdfs_in_folder(folder, recursive, output_name)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
