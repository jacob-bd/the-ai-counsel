# Text File Upload Support Design

## Goal

Add simple, stable support for text-oriented file uploads across the UI, REST API, and MCP tools. Uploaded files should be converted into normalized text before any model call so every provider and model receives the same document context.

## Scope

Supported in v1:

- PDF files with embedded text.
- Scanned or mixed PDFs when OCR support is available.
- Plain text-like files: `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.yml`, `.xml`, `.html`, `.log`, and common source-code extensions.
- UI chat uploads.
- REST conversation and one-shot requests.
- MCP deliberation, single-model chat, iterative debate, and advisor debate.

Out of scope for v1:

- Images as standalone inputs.
- Audio and video.
- Provider-native file upload APIs.
- Storing raw uploaded files permanently.
- OCR as an unbounded background job.
- Document question answering through embeddings or retrieval.

## Recommended Approach

Build a backend document extraction layer that returns a small structured document object:

```json
{
  "name": "report.pdf",
  "mime_type": "application/pdf",
  "text": "...normalized extracted text...",
  "metadata": {
    "page_count": 12,
    "ocr_pages": [2, 7],
    "warnings": ["OCR used on 2 scanned/image-heavy pages."]
  }
}
```

The backend will format these documents into an "Attached Documents" prompt block and append it to the user query before Stage 1, Stage 2, Stage 3, iterative debate, model chat, and advisor debate paths. Provider adapters remain text-only.

## Data Shapes

Use separate request and storage shapes.

`DocumentInput` is accepted at REST and MCP boundaries and may include extracted text:

```json
{
  "name": "report.pdf",
  "mime_type": "application/pdf",
  "text": "...normalized extracted text...",
  "metadata": {
    "page_count": 12,
    "char_count": 125000,
    "truncated": false,
    "ocr_used": true,
    "warnings": ["OCR was used on scanned pages."]
  }
}
```

MCP may also accept base64 file input:

```json
{
  "name": "report.pdf",
  "mime_type": "application/pdf",
  "data_base64": "..."
}
```

`AttachmentMetadata` is the only document data stored in conversation history:

```json
{
  "name": "report.pdf",
  "mime_type": "application/pdf",
  "page_count": 12,
  "char_count": 125000,
  "truncated": false,
  "ocr_used": true,
  "warnings": ["OCR was used on scanned pages."]
}
```

Conversation JSON must not store raw uploaded bytes, base64 strings, or full extracted document text. Reloaded UI conversations render attachment metadata and warnings from the user message.

## Shared Query Augmentation

Add one canonical helper in `backend/documents.py`:

- `validate_documents_for_request(documents, limits)`
- `format_documents_for_prompt(documents)`
- `build_effective_query(content, documents)`

Every ingress path must validate documents before model calls, including pre-extracted MCP text. Every model path must receive the `build_effective_query()` result. Search-query generation and title generation intentionally use the raw user question, not attached document text.

Attached document text is injected only for the current request. Follow-up turns do not automatically rehydrate prior attachment text from storage; users must attach the document again if they want it included in a later turn.

## PDF Extraction

Use `pdfplumber` as the default PDF extractor because it is MIT licensed, handles embedded text well, and offers better layout/table extraction than a minimal `pypdf` path.

Use page-level detection only to decide whether OCR is needed:

1. Extract text from each page with `pdfplumber`.
2. Count useful words and characters.
3. Inspect page images and approximate image coverage.
4. Mark weak pages in metadata.
5. If OCR is enabled and any page needs OCR, run a single guarded OCR pass over the PDF.
6. Re-extract the OCR output with `pdfplumber`.

OCR trigger examples:

- No extracted text.
- Fewer than a configured minimum useful words.
- Large image coverage with little text.
- Extracted text has a low useful-word ratio or obvious garbling on an image-heavy page.

For mixed PDFs, OCR should preserve existing text and add text layers only where needed. The v1 OCR strategy is whole-document OCR with skip-text behavior, not hand-merged page-level OCR.

## OCR Engine

Use optional OCR fallback rather than making OCR a hard requirement.

Preferred v1 OCR path:

- Use `OCRmyPDF` when available to create a searchable temporary PDF.
- Use skip-text behavior so pages with embedded text are not re-OCRed.
- Disable expensive optimization for request-time processing.
- Re-run extraction with `pdfplumber` on the OCR output.
- If OCR dependencies are missing, return a warning and continue with available embedded text.

Equivalent command behavior:

```bash
ocrmypdf --skip-text --optimize 0 --output-type pdf input.pdf output.pdf
```

OCR must be guarded by limits:

- Max pages eligible for OCR.
- Max file size.
- Max processing seconds.
- Max extracted characters per file and per request.
- Global OCR concurrency of 1 process by default.

OCR is disabled by default unless `LLM_COUNCIL_OCR_ENABLED=1` is set and required binaries are available. When disabled or unavailable, scanned pages produce warnings rather than failing the entire extraction when other usable text exists.

If the number of weak pages exceeds the OCR page limit, skip OCR for that file and return a warning instead of running an unbounded OCR job.

## Security And Limits

Validation order:

1. Enforce file count and raw byte/base64 length limits before parsing.
2. Sanitize filenames with basename-only display names; reject null bytes and path traversal.
3. Sniff file type with magic bytes where applicable, including `%PDF-` for PDFs.
4. Parse with page/time/resource limits.
5. Extract and normalize text.
6. Truncate once at ingress.
7. Validate final `DocumentInput` objects before prompt injection.

Default limits:

| Limit | Default | Environment override |
|---|---:|---|
| Max files per request | 5 | `LLM_COUNCIL_MAX_DOCUMENTS` |
| Max upload bytes per file | 20 MB | `LLM_COUNCIL_MAX_DOCUMENT_BYTES` |
| Max base64 characters per file before decode | 28,000,000 chars | `LLM_COUNCIL_MAX_DOCUMENT_BASE64_CHARS` |
| Max PDF pages | 200 | `LLM_COUNCIL_MAX_PDF_PAGES` |
| Max OCR pages per file | 20 | `LLM_COUNCIL_MAX_OCR_PAGES` |
| Max extraction wall time | 60 s | `LLM_COUNCIL_DOCUMENT_TIMEOUT_SECONDS` |
| Max OCR wall time | 60 s | `LLM_COUNCIL_OCR_TIMEOUT_SECONDS` |
| Max extracted chars per file | 150,000 | `LLM_COUNCIL_MAX_DOCUMENT_CHARS` |
| Max extracted chars per request | 300,000 | `LLM_COUNCIL_MAX_DOCUMENT_CHARS_TOTAL` |
| OCR concurrency | 1 | `LLM_COUNCIL_OCR_CONCURRENCY` |

Security requirements:

- Temporary files use random names outside `data/conversations/`.
- Temporary files are deleted in `finally` blocks.
- OCR subprocesses use hard timeouts.
- Upload and OCR errors are redacted before returning to clients; do not expose local paths, temp filenames, or extracted snippets.
- `/api/documents/extract` applies the same limits as message endpoints and may use stricter defaults later if application-level rate limiting is added.
- Attachments are untrusted context; prompt formatting must label them as user-provided documents.

## Backend API

Add `backend/documents.py` with small, testable units:

- `extract_documents_from_uploads(files, options)`
- `extract_text_file(...)`
- `extract_pdf(...)`
- `detect_pdf_page_needs_ocr(...)`
- `format_documents_for_prompt(documents)`
- `build_effective_query(content, documents)`
- `validate_documents_for_request(documents, limits)`
- validation helpers for size, count, MIME type, extension, and character budget

Add `POST /api/documents/extract` for UI uploads:

- Accept multipart files.
- Return extracted document objects and warnings.
- Never return or persist raw file bytes.

Extend existing JSON request models with optional `documents`:

- `POST /api/ask`
- `POST /api/conversations/{id}/message`
- `POST /api/conversations/{id}/message/stream`
- `POST /api/conversations/{id}/message/debate`
- `POST /api/conversations/{id}/debate/stream` through `StartDebateRequest.question`

The stored user message should keep the user query and document metadata, never raw extracted text. Follow-up turns should include the normal chat history plus prior assistant summaries; raw document text should not be repeatedly duplicated into all future turns unless the user attaches it again.

## MCP API

Extend MCP tool schemas with optional `documents`:

- `council_deliberate`
- `model_chat`
- `run_iterative_debate`
- `advisor_debate`

MCP documents may be supplied as:

- Pre-extracted text: `{ "name": "...", "mime_type": "...", "text": "..." }`
- Base64 file content: `{ "name": "...", "mime_type": "...", "data_base64": "..." }`

When `data_base64` is provided, the MCP client layer should call the backend extraction endpoint. The result shape should include document metadata and warnings so agents can tell users when OCR was unavailable or partial.

`CouncilClient` must be extended so MCP tools can pass `documents` through:

- `ask(..., documents=None)`
- `stream_message(..., documents=None)`
- `stream_debate_message(..., documents=None)`
- advisor debate client method
- `extract_documents(...)` for base64 or file upload inputs when needed

The HTTP extraction endpoint is the canonical MCP path so stdio MCP against a remote backend behaves the same as co-mounted SSE MCP. In-process extraction may be used only as an internal optimization when it preserves identical validation and result shape.

## UI

Add a paperclip control to `ChatInterface` and equivalent document upload controls to `AdvisorSetup`.

Expected behavior:

- User selects supported files.
- UI shows chips with name, size, and extraction status.
- UI calls `/api/documents/extract` before sending the chat request.
- UI sends extracted `documents` with the message request.
- User messages render attachment names and warnings.
- Send is disabled while extraction is in progress.

The UI should not read large files into base64 and send them through normal chat JSON.

Optimistic user messages in `App.jsx` should store attachment metadata from the extraction response so reloads and in-flight views match.

## Integration Checklist

All of these paths must use the shared validation and query augmentation helpers:

- REST `/api/ask`
- REST `/api/conversations/{id}/message`
- REST `/api/conversations/{id}/message/stream`
- REST `/api/conversations/{id}/message/debate`
- REST `/api/conversations/{id}/debate/stream`
- `stage1_collect_responses`
- `run_iterative_debate`, including Stage 4 corrected draft context
- `run_debate` advisor rounds, tiebreaker, and verdict context
- MCP `council_deliberate`
- MCP `model_chat`
- MCP `run_iterative_debate`
- MCP `advisor_debate`
- MCP `CouncilClient` request helpers
- UI `ChatInterface.jsx`
- UI `AdvisorSetup.jsx`
- UI `api.js`
- UI `App.jsx` optimistic and stored message rendering
- Storage `add_user_message()` extended metadata shape

Excluded from document injection:

- `generate_search_query()`
- `generate_conversation_title()`
- Sidebar title derivation beyond user-visible text and attachment metadata

## Error Handling

Hard failures:

- Unsupported file type.
- File exceeds configured size.
- Too many files.
- Total extracted text exceeds configured request budget.
- PDF is encrypted and cannot be opened.
- Base64 payload exceeds size limit before decode.
- MIME sniffing contradicts a supported extension in a dangerous way.

Warnings:

- OCR not installed or disabled.
- Some pages had no extractable text.
- OCR timed out on some pages.
- Text was truncated to fit the configured budget.

Warnings should not block a run when usable text remains.

## Dependencies And Docker

Required Python dependencies:

- `pdfplumber`
- `python-multipart`

Optional OCR dependencies:

- Python package: `ocrmypdf`
- System binaries/packages: `tesseract-ocr`, `tesseract-ocr-eng`, `ghostscript`, and `qpdf`

The default Docker image may remain OCR-disabled if these system dependencies are not installed. If OCR is advertised as available in Docker, add an OCR build path or documented compose profile that installs the system packages and sets `LLM_COUNCIL_OCR_ENABLED=1`.

Runtime extraction responses should include OCR availability metadata so the UI and MCP callers can show whether scanned PDFs were processed or skipped.

## Testing

Backend tests:

- Text file extraction.
- PDF embedded text extraction.
- Scanned/image-only PDF warning when OCR is unavailable.
- Mixed PDF weak-page detection and whole-document OCR fallback behavior using mocked OCR.
- Prompt formatting and truncation.
- REST request models accept `documents`.
- Conversation storage does not persist raw file bytes.
- Oversized pre-extracted MCP text is rejected.
- MIME spoofing is rejected.
- Encrypted PDF returns a hard failure.
- Temporary files are cleaned up after OCR success and failure.
- Upload/OCR errors are redacted.
- Optional `@pytest.mark.ocr` integration test can verify local OCR when dependencies are installed.

MCP tests:

- `council_deliberate` forwards pre-extracted documents.
- `model_chat` forwards pre-extracted documents.
- `run_iterative_debate` forwards pre-extracted documents.
- `advisor_debate` forwards pre-extracted documents.
- Base64 document input takes the extraction path.
- Oversized pre-extracted text is rejected.
- Warnings appear in returned JSON.

Frontend tests or build verification:

- File chips render.
- Unsupported files show errors.
- Sending waits for extraction.
- Extracted documents are included in stream request payloads.
- Advisor upload controls follow the same extract-then-send flow.
- Run `npm run build` at minimum because the frontend has no dedicated test suite today.

## Documentation Sync

The implementation is not complete unless the user-facing docs and the API skill are updated in the same change set. Update these surfaces with the implementation:

- `docs/mcp/TOOLS.md`
- `docs/mcp/EXAMPLES.md`
- `docs/mcp/INSTRUCTIONS.md`
- `skills/the-ai-counsel-api/SKILL.md`
- `README.md` if upload support is user-facing in the release notes/install flow
- `AGENTS.md` only if architecture or operational guidance changes

Required documentation content:

- Supported file types and limits.
- OCR behavior, including when OCR is attempted and what happens when OCR dependencies are unavailable.
- REST request and response examples for `documents`.
- MCP tool parameter examples for pre-extracted text and base64 file input.
- UI behavior and warning states.
- Privacy/storage note that raw uploaded files are not persisted.

The `skills/the-ai-counsel-api/SKILL.md` update must include the new `documents` parameter wherever MCP or REST examples can accept file-derived context.

## Decision

Implement the provider-agnostic text extraction layer first. Keep model providers text-only. Use `pdfplumber` as the default PDF extractor and optional guarded OCR fallback for scanned or mixed PDFs.
