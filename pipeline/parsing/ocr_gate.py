"""Step 3.2: OCR gate for scanned filings. Only invoked when
format_detection.is_text_native() is False. Requires the `tesseract` binary
and `pytesseract` + `pdf2image` (Poppler) — kept as a lazy import so the rest
of the pipeline doesn't require an OCR toolchain to run.
"""
from __future__ import annotations


def ocr_pdf_to_text(pdf_path: str, dpi: int = 300) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError(
            "OCR gate requires pytesseract + pdf2image (and the tesseract/poppler "
            "binaries) to be installed to process scanned FDD filings."
        ) from exc

    pages = convert_from_path(pdf_path, dpi=dpi)
    return "\n".join(pytesseract.image_to_string(page) for page in pages)
