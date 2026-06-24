import base64
import pytest
from backend.documents import (
    PreparedDocuments,
    prepare_documents,
    AttachmentCapabilities,
)

def test_prepared_documents_preserves_exact_bytes():
    original_data = b"%PDF-1.4\n%EOF\n"
    original_base64 = base64.b64encode(original_data).decode("utf-8")

    documents = [
        {
            "name": "report.pdf",
            "mime_type": "application/pdf",
            "text": "Extracted text content...",
            "data_base64": original_base64,
        }
    ]

    caps = AttachmentCapabilities(
        enabled=True,
        supported_mime_types={"application/pdf"},
        stateful=True,
    )

    prepared = prepare_documents(documents, caps)

    # Assert original bytes are preserved
    assert len(prepared.native_candidates) == 1
    assert prepared.native_candidates[0]["name"] == "report.pdf"
    assert prepared.native_candidates[0]["content_type"] == "application/pdf"
    assert prepared.native_candidates[0]["file_data"] == original_base64

    # Assert PDF bytes decode to original exact bytes
    decoded = base64.b64decode(prepared.native_candidates[0]["file_data"])
    assert decoded == original_data

    # Assert fallback list is empty since it was natively accepted
    assert len(prepared.fallback_documents) == 0

    # Assert storage metadata has NO file bytes
    assert len(prepared.storage_metadata) == 1
    assert "file_data" not in prepared.storage_metadata[0]
    assert "data_base64" not in prepared.storage_metadata[0]
    assert prepared.storage_metadata[0]["name"] == "report.pdf"
    assert prepared.storage_metadata[0]["mime_type"] == "application/pdf"

def test_fallback_mimetype_and_mislabeled_text():
    documents = [
        {
            "name": "notes.txt",
            "mime_type": "text/plain",
            "text": "Some plain text",
            "data_base64": None,  # no original bytes
        }
    ]

    caps = AttachmentCapabilities(
        enabled=True,
        supported_mime_types={"application/pdf"}, # does not support text/plain natively
        stateful=False,
    )

    prepared = prepare_documents(documents, caps)

    # Native list is empty (unsupported type + no bytes)
    assert len(prepared.native_candidates) == 0

    # Fallback list has the document text
    assert len(prepared.fallback_documents) == 1
    assert prepared.fallback_documents[0]["name"] == "notes.txt"
    assert prepared.fallback_documents[0]["text"] == "Some plain text"

def test_mixed_native_and_fallback_documents():
    pdf_data = b"%PDF-1.4\n%EOF\n"
    pdf_base64 = base64.b64encode(pdf_data).decode("utf-8")

    documents = [
        {
            "name": "report.pdf",
            "mime_type": "application/pdf",
            "text": "Extracted text content...",
            "data_base64": pdf_base64,
        },
        {
            "name": "notes.txt",
            "mime_type": "text/plain",
            "text": "Some plain text",
            "data_base64": None,
        }
    ]

    caps = AttachmentCapabilities(
        enabled=True,
        supported_mime_types={"application/pdf"},
        stateful=True,
    )

    prepared = prepare_documents(documents, caps)

    # PDF is native, notes.txt is fallback
    assert len(prepared.native_candidates) == 1
    assert prepared.native_candidates[0]["name"] == "report.pdf"

    assert len(prepared.fallback_documents) == 1
    assert prepared.fallback_documents[0]["name"] == "notes.txt"
    assert prepared.fallback_documents[0]["text"] == "Some plain text"

    # Both in storage metadata
    assert len(prepared.storage_metadata) == 2
    assert "file_data" not in prepared.storage_metadata[0]
    assert "file_data" not in prepared.storage_metadata[1]
