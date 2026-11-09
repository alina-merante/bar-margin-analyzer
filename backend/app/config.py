import os
from pathlib import Path

UPLOAD_BASE_PATH = os.getenv("UPLOAD_BASE_PATH", "uploads")

UPLOAD_DOCUMENTS_DIR = os.path.join(UPLOAD_BASE_PATH, "documents")
UPLOAD_INVOICES_DIR = os.path.join(UPLOAD_BASE_PATH, "invoices")
UPLOAD_PREVIEWS_DIR = os.path.join(UPLOAD_BASE_PATH, "previews")


def ensure_upload_dirs():
    """Ensure all upload directories exist."""
    for directory in [UPLOAD_DOCUMENTS_DIR, UPLOAD_INVOICES_DIR, UPLOAD_PREVIEWS_DIR]:
        os.makedirs(directory, exist_ok=True)


def get_document_path(filename: str) -> str:
    """Get full path for a document file."""
    return os.path.join(UPLOAD_DOCUMENTS_DIR, filename)


def get_invoice_path(filename: str) -> str:
    """Get full path for an invoice file."""
    return os.path.join(UPLOAD_INVOICES_DIR, filename)


def get_preview_path(filename: str) -> str:
    """Get full path for a preview file."""
    return os.path.join(UPLOAD_PREVIEWS_DIR, filename)


def get_document_url(filename: str) -> str:
    """Get URL for a document file."""
    return f"/uploads/documents/{filename}"


def get_preview_url(filename: str) -> str:
    """Get URL for a preview file."""
    return f"/uploads/previews/{filename}"
