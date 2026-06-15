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

## PDF Extraction

Use `pdfplumber` as the default PDF extractor because it is MIT licensed, handles embedded text well, and offers better layout/table extraction than a minimal `pypdf` path.

Use page-level detection for OCR fallback:

1. Extract text from each page with `pdfplumber`.
2. Count useful words and characters.
3. Inspect page images and approximate image coverage.
4. Mark only weak pages for OCR.
5. OCR marked pages when OCR support is installed and enabled.
6. Merge page text in source order with labels such as `[Page 2 - OCR text]`.

OCR trigger examples:

- No extracted text.
- Fewer than a configured minimum useful words.
- Large image coverage with little text.
- Extracted text has a low useful-word ratio or obvious garbling.

For mixed PDFs, OCR supplements weak/image-heavy pages only. It does not replace good embedded text.

## OCR Engine

Use optional OCR fallback rather than making OCR a hard requirement.

Preferred v1 OCR path:

- Use `OCRmyPDF` when available to create a searchable temporary PDF for weak pages or documents.
- Re-run extraction with `pdfplumber` on the OCR output.
- If OCR dependencies are missing, return a warning and continue with available embedded text.

OCR must be guarded by limits:

- Max pages eligible for OCR.
- Max file size.
- Max processing seconds.
- Max extracted characters per file and per request.

## Backend API

Add `backend/documents.py` with small, testable units:

- `extract_documents_from_uploads(files, options)`
- `extract_text_file(...)`
- `extract_pdf(...)`
- `detect_pdf_page_needs_ocr(...)`
- `format_documents_for_prompt(documents)`
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
- Advisor debate request

The stored user message should keep the user query and document metadata, not raw extracted text unless needed for conversation continuity. Follow-up turns should include the normal chat history plus prior assistant summaries; raw document text should not be repeatedly duplicated into all future turns unless the user attaches it again.

## MCP API

Extend MCP tool schemas with optional `documents`:

- `council_deliberate`
- `model_chat`
- `run_iterative_debate`
- `advisor_debate`

MCP documents may be supplied as:

- Pre-extracted text: `{ "name": "...", "mime_type": "...", "text": "..." }`
- Base64 file content: `{ "name": "...", "mime_type": "...", "data_base64": "..." }`

When `data_base64` is provided, the MCP client layer should call the same backend extraction endpoint or equivalent shared extraction helper. The result shape should include document metadata and warnings so agents can tell users when OCR was unavailable or partial.

## UI

Add a paperclip control to `ChatInterface`.

Expected behavior:

- User selects supported files.
- UI shows chips with name, size, and extraction status.
- UI calls `/api/documents/extract` before sending the chat request.
- UI sends extracted `documents` with the message request.
- User messages render attachment names and warnings.
- Send is disabled while extraction is in progress.

The UI should not read large files into base64 and send them through normal chat JSON.

## Error Handling

Hard failures:

- Unsupported file type.
- File exceeds configured size.
- Too many files.
- Total extracted text exceeds configured request budget.
- PDF is encrypted and cannot be opened.

Warnings:

- OCR not installed or disabled.
- Some pages had no extractable text.
- OCR timed out on some pages.
- Text was truncated to fit the configured budget.

Warnings should not block a run when usable text remains.

## Testing

Backend tests:

- Text file extraction.
- PDF embedded text extraction.
- Scanned/image-only PDF warning when OCR is unavailable.
- Mixed PDF page-level OCR detection behavior using mocked OCR.
- Prompt formatting and truncation.
- REST request models accept `documents`.
- Conversation storage does not persist raw file bytes.

MCP tests:

- `council_deliberate` forwards pre-extracted documents.
- `model_chat` forwards pre-extracted documents.
- Base64 document input takes the extraction path.
- Warnings appear in returned JSON.

Frontend tests or build verification:

- File chips render.
- Unsupported files show errors.
- Sending waits for extraction.
- Extracted documents are included in stream request payloads.

## Documentation Sync

Update these surfaces with the implementation:

- `docs/mcp/TOOLS.md`
- `docs/mcp/EXAMPLES.md`
- `docs/mcp/INSTRUCTIONS.md`
- `skills/the-ai-counsel-api/SKILL.md`
- `README.md` if upload support is user-facing in the release notes/install flow
- `AGENTS.md` only if architecture or operational guidance changes

## Decision

Implement the provider-agnostic text extraction layer first. Keep model providers text-only. Use `pdfplumber` as the default PDF extractor and optional guarded OCR fallback for scanned or mixed PDFs.
