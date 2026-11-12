import errno
import mimetypes
import logging
import os
import re
import stat

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.bar_context import (
    BarContext,
    BarPermission,
    revalidate_active_bar_context,
    require_bar_permission,
)
from app.database import get_db
from app.models import Document, Invoice

router = APIRouter(prefix="/uploads", tags=["protected files"])
read_context = require_bar_permission(BarPermission.READ_DOCUMENTS)
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}")
logger = logging.getLogger(__name__)


def safe_filename(filename: str) -> bool:
    return bool(_FILENAME.fullmatch(filename))


def document_urls(document: Document) -> tuple[str, str]:
    filename = document.stored_filename
    expected_file = f"/uploads/documents/{filename}"
    if not safe_filename(filename) or document.file_url != expected_file:
        logger.warning("Invalid stored file URL for document %s", document.id)
        return "", ""

    stem = filename.rsplit(".", 1)[0]
    previews = document.preview_url.split(",") if document.preview_url else []
    allowed_previews = []
    for url in previews:
        if url == expected_file:
            allowed_previews.append(url)
            continue
        prefix = "/uploads/previews/"
        if not url.startswith(prefix):
            logger.warning("Invalid preview URL for document %s", document.id)
            return expected_file, ""
        preview = url[len(prefix):]
        if not safe_filename(preview) or not re.fullmatch(
            rf"{re.escape(stem)}(?:_[1-9][0-9]*)?\.png", preview
        ):
            logger.warning("Invalid preview URL for document %s", document.id)
            return expected_file, ""
        allowed_previews.append(url)
    return expected_file, ",".join(allowed_previews)


def invoice_url(invoice: Invoice) -> str | None:
    url = invoice.file_url
    prefix = "/uploads/invoices/"
    if not url or not url.startswith(prefix) or not safe_filename(url[len(prefix):]):
        if url:
            logger.warning("Invalid stored file URL for invoice %s", invoice.id)
        return None
    return url


def _read_file(directory: str, filename: str) -> StreamingResponse:
    fd = None
    try:
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        finally:
            os.close(directory_fd)
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            os.close(fd)
            fd = None
            raise HTTPException(status_code=404, detail="file not found")
        file = os.fdopen(fd, "rb")
        fd = None
    except OSError as exc:
        if fd is not None:
            os.close(fd)
        if exc.errno in {errno.ENOENT, errno.ENOTDIR, errno.EACCES, errno.ELOOP}:
            raise HTTPException(status_code=404, detail="file not found") from exc
        logger.exception("Could not open authorized upload")
        raise HTTPException(status_code=500, detail="file could not be opened") from exc

    def chunks():
        try:
            while chunk := file.read(64 * 1024):
                yield chunk
        finally:
            file.close()

    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    inline = media_type in {"application/pdf", "image/jpeg", "image/png", "image/webp"}
    return StreamingResponse(
        chunks(),
        media_type=media_type,
        headers={
            "Content-Length": str(file_stat.st_size),
            "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{filename}"',
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "Vary": "Cookie",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.get("/{kind}/{filename}")
def read_upload(
    kind: str,
    filename: str,
    request: Request,
    context: BarContext = Depends(read_context),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    if kind not in {"documents", "previews", "invoices"} or not safe_filename(filename):
        raise HTTPException(status_code=404, detail="file not found")
    context = revalidate_active_bar_context(
        request, db, context.bar.id, lock=True
    )
    read_context(context)
    url = f"/uploads/{kind}/{filename}"

    if kind == "invoices":
        invoices = db.scalars(select(Invoice).where(Invoice.file_url == url)).all()
        if (
            not invoices
            or any(invoice.bar_id != context.bar.id for invoice in invoices)
            or any(invoice_url(invoice) != url for invoice in invoices)
        ):
            raise HTTPException(status_code=404, detail="file not found")
        directory = config.UPLOAD_INVOICES_DIR
    else:
        documents = db.scalars(
            select(Document).where(
                (Document.file_url == url) if kind == "documents"
                else Document.preview_url.contains(url, autoescape=True),
            )
        ).all()
        if kind == "documents":
            referenced = [document for document in documents if document.file_url == url]
        else:
            referenced = [
                document for document in documents if url in document.preview_url.split(",")
            ]
        if (
            not referenced
            or any(document.bar_id != context.bar.id for document in referenced)
            or any(
                (url != file_url if kind == "documents" else url not in preview_url.split(","))
                for file_url, preview_url in (document_urls(document) for document in referenced)
            )
        ):
            raise HTTPException(status_code=404, detail="file not found")
        directory = config.UPLOAD_DOCUMENTS_DIR if kind == "documents" else config.UPLOAD_PREVIEWS_DIR

    return _read_file(directory, filename)
