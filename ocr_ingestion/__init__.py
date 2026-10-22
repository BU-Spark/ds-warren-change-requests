"""Local extraction and incremental ingestion of printed document tables."""

from .storage import append_records, load_records


def extract_document(*args, **kwargs):
    # Keep persistence usable without importing the optional PDF/OCR stack.
    from .extraction import extract_document as extract
    return extract(*args, **kwargs)


__all__ = ["extract_document", "append_records", "load_records"]
