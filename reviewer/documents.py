"""Upload, extraction serialization and source preview helpers for the API."""

from fastapi import HTTPException
from fastapi.responses import Response

from ocr_ingestion.extraction import MAX_BYTES
from ocr_ingestion.models import Extraction, Table


def restore_extraction(payload):
    return Extraction(
        document_id=payload["document_id"],
        source_file=payload["source_file"],
        records=payload["records"],
        tables=[Table(**t) for t in payload["tables"]],
        issues=payload["issues"],
        pages=payload["pages"],
    )


async def receive_upload(upload, limit=MAX_BYTES):
    content = bytearray()
    try:
        while chunk := await upload.read(1024 * 1024):
            content.extend(chunk)
            if len(content) > limit:
                raise HTTPException(
                    413, f"This file exceeds the {limit // (1024 * 1024)} MB limit."
                )
    finally:
        await upload.close()
    if not content:
        raise ValueError("The uploaded file is empty.")
    return bytes(content)


def page_image(path, page_number):
    if page_number < 1:
        raise ValueError("Page numbers start at 1.")
    import pymupdf

    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            if page_number > len(doc):
                raise HTTPException(404, "This source page does not exist.")
            content = (
                doc[page_number - 1].get_pixmap(dpi=120, annots=False).tobytes("png")
            )
    else:
        import io

        from PIL import Image

        with Image.open(path) as image:
            try:
                image.seek(page_number - 1)
            except EOFError:
                raise HTTPException(404, "This source page does not exist.")
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="PNG")
            content = buffer.getvalue()
    return Response(content, media_type="image/png")
