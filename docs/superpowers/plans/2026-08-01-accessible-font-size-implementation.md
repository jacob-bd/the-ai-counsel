# Accessible Font Size Preference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted Default/Large/xLarge accessibility preference that scales all application text proportionally across existing and future conversations without scaling icons or layout geometry.

**Architecture:** Store a validated `font_size` enum in the existing backend settings model and expose it through the settings API. The React app loads the preference once, applies a CSS root scale immediately, and the General settings modal updates it through the existing debounced auto-save flow. Convert stylesheet pixel font sizes to rem-based values so the root multiplier reaches all text, while preserving layout dimensions and icon sizing.

**Tech Stack:** FastAPI/Pydantic settings API, React 19, Vite, CSS custom properties/rem units, pytest, Node’s built-in test runner for the frontend typography utility.

## Global Constraints

- Default uses `1.10×`, Large uses `1.50×`, and xLarge uses `2.00×` of the current typography baseline.
- The preference applies to all interface text, including markdown/model responses, existing chats, and future chats.
- Icons, borders, widths, heights, and layout spacing must not be scaled solely by the font-size preference.
- Invalid or missing persisted values resolve to `default`; API updates reject unknown values.
- Use relative units for CSS-defined text and do not use CSS `zoom` or an application-wide transform.
- API keys and other secrets remain outside `settings.json` behavior.
- Use relative imports in backend modules and preserve existing auto-save behavior.

---

### Task 1: Add backend setting, normalization, API validation, and tests

**Files:**
- Modify: `backend/settings.py` — add the `font_size` field and normalization constant/logic.
- Modify: `backend/main.py` — accept and validate `font_size` in `UpdateSettingsRequest` and `/api/settings` updates.
- Modify: `backend/settings_payload.py` — return `font_size` from `GET /api/settings`.
- Create: `backend/tests/test_font_size.py` — test defaults, normalization, API acceptance/rejection, and response persistence.

**Interfaces:**
- Produces the persisted setting name `font_size` with values `default`, `large`, or `xlarge`.
- Produces `VALID_FONT_SIZES` and `FONT_SIZE_DEFAULT` from `backend.settings` for validation/tests.

- [ ] **Step 1: Write the failing backend tests.**

  Add tests covering:

  ```python
  def test_font_size_defaults_to_default():
      from backend.settings import FONT_SIZE_DEFAULT, Settings
      assert FONT_SIZE_DEFAULT == "default"
      assert Settings().font_size == "default"

  def test_invalid_font_size_normalizes_to_default():
      from backend.settings import _normalize_prompt_defaults
      assert _normalize_prompt_defaults({"font_size": "giant"})["font_size"] == "default"

  def test_valid_font_size_is_preserved():
      from backend.settings import _normalize_prompt_defaults
      assert _normalize_prompt_defaults({"font_size": "xlarge"})["font_size"] == "xlarge"
  ```

  Use the existing `client` fixture pattern from `backend/tests/test_settings_backup.py` for API tests. Verify `PUT /api/settings` accepts `{"font_size": "large"}`, returns the setting in the response, and rejects `{"font_size": "giant"}` with HTTP 400.

- [ ] **Step 2: Run the focused tests and verify they fail for the missing feature.**

  Run:

  ```bash
  uv run pytest backend/tests/test_font_size.py -q
  ```

  Expected: failures showing that `Settings` has no `font_size`, the normalizer does not provide the fallback, and the API does not accept/validate the field.

- [ ] **Step 3: Implement the minimal backend setting contract.**

  In `backend/settings.py`, define:

  ```python
  FONT_SIZE_DEFAULT = "default"
  VALID_FONT_SIZES = ("default", "large", "xlarge")
  ```

  Add `font_size: str = FONT_SIZE_DEFAULT` beside the other display preferences. Extend `_normalize_display_preferences` so a missing or invalid value becomes `FONT_SIZE_DEFAULT`, and preserve valid values.

  In `backend/main.py`, add `font_size: Optional[str] = None` to `UpdateSettingsRequest`. Validate membership in `VALID_FONT_SIZES`, raising the same style of HTTP 400 error used for `date_format`, then include it in `updates`.

  In `backend/settings_payload.py`, include the persisted `settings.font_size` in the returned settings dictionary.

- [ ] **Step 4: Run the focused backend tests and verify they pass.**

  Run:

  ```bash
  uv run pytest backend/tests/test_font_size.py backend/tests/test_response_language.py -q
  ```

  Expected: all focused settings tests pass.

- [ ] **Step 5: Commit the backend contract.**

  ```bash
  git add backend/settings.py backend/main.py backend/settings_payload.py backend/tests/test_font_size.py
  git commit -m "feat: persist accessible font size preference"
  ```

### Task 2: Add frontend font-size scale utility and General settings control

**Files:**
- Create: `frontend/src/utils/fontSize.js` — canonical frontend values, normalization, and CSS scale application.
- Create: `frontend/src/utils/fontSize.test.js` — Node-testable behavior for the utility.
- Modify: `frontend/src/App.jsx` — load, store, apply, and refresh the global font-size preference.
- Modify: `frontend/src/components/Settings.jsx` — include font size in state, load, change detection, and auto-save.
- Modify: `frontend/src/components/settings/GeneralSettings.jsx` — render the accessible Font Size select.
- Modify: `frontend/src/components/Settings.css` — add focused layout styles for the control if needed.

**Interfaces:**
- `FONT_SIZE_OPTIONS` contains `{ value, label, scale }` entries for `default`, `large`, and `xlarge`.
- `normalizeFontSize(value)` returns a valid enum, falling back to `default`.
- `getFontScale(value)` returns `1.1`, `1.5`, or `2`.
- `applyFontSize(value, root = document.documentElement)` sets `data-font-size` and `--font-scale` on the shared root.

- [ ] **Step 1: Write failing frontend utility tests.**

  Add Node-compatible tests for normalization, exact multipliers, and root attribute/property application using a tiny fake root object with `dataset` and `style.setProperty`.

- [ ] **Step 2: Run the frontend utility tests and verify they fail.**

  Run:

  ```bash
  node --test frontend/src/utils/fontSize.test.js
  ```

  Expected: module/function import failures because the utility does not exist yet.

- [ ] **Step 3: Implement the utility and app-level application.**

  Implement the canonical option map and safe normalization in `fontSize.js`. In `App.jsx`, add state initialized to `default`, apply the loaded `settings.font_size` in `checkInitialSetup`, refresh it in `handleSettingsClose`, and apply it from an effect so the root updates immediately after load or settings changes.

  Keep the preference global to the app root; do not pass it into conversation components or persist it in conversation data.

- [ ] **Step 4: Extend Settings state and the General control.**

  In `Settings.jsx`, add `fontSize` state, load `data.font_size || 'default'`, include it in the `settingsChanged` comparison, dependency array, and debounced `updates` payload. Pass `fontSize` and `onFontSizeChange` into `GeneralSettings`.

  In `GeneralSettings.jsx`, add a Font Size row below Date Format with a native select labeled `Font Size`, options `Default (slightly larger)`, `Large`, and `xLarge`, and helper text explaining that it applies to all text and saves automatically.

- [ ] **Step 5: Run frontend utility tests, lint, and build.**

  Run:

  ```bash
  node --test frontend/src/utils/fontSize.test.js
  npm run lint --prefix frontend
  npm run build --prefix frontend
  ```

  Expected: utility tests pass, lint reports no new errors, and Vite builds successfully.

- [ ] **Step 6: Commit the frontend control and state wiring.**

  ```bash
  git add frontend/src/utils/fontSize.js frontend/src/utils/fontSize.test.js frontend/src/App.jsx frontend/src/components/Settings.jsx frontend/src/components/settings/GeneralSettings.jsx frontend/src/components/Settings.css
  git commit -m "feat: add accessible font size controls"
  ```

### Task 3: Convert typography to relative scaling without changing layout geometry

**Files:**
- Modify: `frontend/src/index.css` — define the root typography baseline and scale variables; convert global/markdown text sizes.
- Modify: all `frontend/src/**/*.css` files containing hard-coded `font-size: Npx` declarations — convert text sizes to equivalent rem values, including media-query declarations.
- Modify: `frontend/src/components/SearchableModelSelect.jsx` — convert inline `fontSize` pixel values to the shared relative unit or CSS class.

**Interfaces:**
- `--font-scale` is set by `fontSize.js` and defaults to `1.1`.
- `html` uses the shared baseline multiplied by `--font-scale`; `rem` text values resolve against that root size.

- [ ] **Step 1: Add a regression test for the scale constants before changing styles.**

  Extend the utility test to assert that the default scale is 1.1 and that the option values are stable. Run it to establish the red/green boundary for the CSS-facing contract.

- [ ] **Step 2: Add root scaling variables and global relative units.**

  In `index.css`, add `--font-scale: 1.1` and a baseline variable, then set the root font size from that multiplier. Convert global markdown/table/code text pixel sizes to rem equivalents based on the current 16px baseline. Leave `em` values relative and preserve line-height values.

- [ ] **Step 3: Mechanically convert remaining CSS font-size pixels.**

  Convert each literal `font-size: Npx` to `font-size: (N / 16)rem`, preserving `!important`, comments, media-query location, and all non-font dimensions. Do not convert pixel sizes used for icons unless they are explicitly text font sizes; icon selectors should retain their current sizing if the control is visual-only.

  Review unusual fractional sizes (8.5px, 9.5px, 10px, 11px, 12px, etc.) for accurate rem conversion rather than rounding them up/down.

- [ ] **Step 4: Update inline font-size declarations.**

  Replace the inline `fontSize` values in `SearchableModelSelect.jsx` with CSS classes or `rem` values so they inherit the root multiplier. Keep model picker widths and row heights unchanged unless the existing CSS already derives them from text.

- [ ] **Step 5: Run static checks and inspect all remaining font-size declarations.**

  Run:

  ```bash
  rg -n --glob '*.css' --glob '*.jsx' "font-size\\s*:\\s*[0-9.]+px|fontSize:\\s*'[0-9.]+px'" frontend/src
  npm run lint --prefix frontend
  npm run build --prefix frontend
  ```

  Expected: no unreviewed hard-coded text pixel sizes remain, lint is clean, and the build passes. Any intentional icon-only sizes must be documented in the review notes and excluded from text scaling by design.

- [ ] **Step 6: Commit the typography conversion.**

  ```bash
  git add frontend/src/index.css frontend/src/**/*.css frontend/src/components/SearchableModelSelect.jsx
  git commit -m "feat: scale application typography for accessibility"
  ```

### Task 4: Sync documentation and complete verification

**Files:**
- Modify: `AGENTS.md` — document General font-size choices and global behavior.
- Modify: `skills/the-ai-counsel-api/SKILL.md` — add the settings field and valid values to the API reference.
- Modify: `docs/DOC-SYNC.md` — add the new General setting to the sync matrix/checklist.
- Modify: `CHANGELOG.md` — add the accessibility font-size preference under the current unreleased/user-facing section.

- [ ] **Step 1: Update the settings documentation.**

  Document `font_size` as a non-secret persisted General setting with valid values `default`, `large`, and `xlarge`; state that Default is 110%, Large is 150%, and xLarge is 200% of the current typography baseline and applies to all UI text, including existing chats.

- [ ] **Step 2: Run the complete automated checks.**

  Run:

  ```bash
  uv run pytest backend/tests -q
  node --test frontend/src/utils/fontSize.test.js
  npm run lint --prefix frontend
  npm run build --prefix frontend
  git diff --check HEAD~4..HEAD
  ```

  Expected: all backend tests pass, frontend utility tests pass, lint/build pass, and the diff has no whitespace errors.

- [ ] **Step 3: Perform the visual/accessibility smoke test.**

  Start the app with `./start.sh`, open an existing conversation, and test Default, Large, and xLarge from Settings → General. Confirm model response text, markdown, sidebar, settings labels, stage tabs, model selectors, tables, buttons, and mobile/narrow layouts scale without critical clipping or horizontal overflow. Confirm reopening the app retains the selected value through the backend settings API.

- [ ] **Step 4: Review the final diff and status.**

  Run:

  ```bash
  git status --short
  git diff --stat HEAD~4..HEAD
  git diff --check HEAD~4..HEAD
  ```

  Ensure only the accessibility preference, its tests, typography conversion, documentation, and the design/plan records are included.
