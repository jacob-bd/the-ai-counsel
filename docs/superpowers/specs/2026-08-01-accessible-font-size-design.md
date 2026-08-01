# Accessible Font Size Preference

## Goal

Improve readability for users who find the Council UI too small by making the default typography slightly larger and adding persistent font-size choices in Settings → General. The preference must apply to all interface text, including existing conversation views and newly opened chats, without scaling icons or layout geometry like browser zoom.

## Approved behavior

The setting is a global application preference with three options:

| Option | Multiplier against the current typography baseline |
| --- | ---: |
| Default | 1.10× |
| Large | 1.50× |
| xLarge | 2.00× |

Examples: a current 12px label becomes 13.2px, 18px, and 24px respectively; a current 16px response becomes 17.6px, 24px, and 32px respectively.

The setting saves automatically with the existing General settings flow and takes effect immediately. It is not stored per conversation, so it applies to both previous chats and future chats. Existing users with no saved value receive `default` behavior through backend and frontend fallbacks.

## Architecture

### Persistence and API

- Add a `font_size` setting to the backend `Settings` model with the safe default `default`.
- Normalize invalid or missing stored values to `default` when settings are loaded or imported.
- Accept and validate `font_size` in `PUT /api/settings` against `default`, `large`, and `xlarge`.
- Include `font_size` in the `GET /api/settings` response so the Settings UI can initialize from the persisted value.
- Keep the setting non-secret and compatible with existing settings export/import behavior.

### Frontend state and application

- Load `font_size` with the existing Settings state and include it in the existing debounced auto-save payload.
- Add a clearly labeled Font Size control under General → Display Preferences with Default, Large, and xLarge options.
- Apply the selected value to the shared app root using a data attribute or class and CSS custom property.
- Use a root font-size scale and relative text units so all CSS-defined text sizes—including markdown, stages, sidebar, settings, advisor views, and responsive states—inherit the same multiplier.
- Convert hard-coded `font-size` pixel declarations to equivalent `rem` values where needed. Preserve relative `em`/`rem` declarations and responsive `clamp()` behavior unless they need an explicit adjustment for the shared scale.
- Update inline text-size styling that bypasses the stylesheet so it also follows the shared scale.
- Do not scale icons, borders, widths, heights, or layout spacing solely because the font-size preference changes.

## Layout safety

- Keep existing overflow and responsive rules in place.
- Check the narrow/mobile layouts at all three sizes, especially model selectors, sidebar rows, stage tabs, tables, buttons, and long labels.
- Preserve readable line-height by keeping existing unitless or relative line-height values where possible.
- Do not use CSS `zoom` or a whole-application transform, because those approaches enlarge non-text geometry and can introduce clipping.

## Error handling and compatibility

- Unknown API values are rejected with a validation error rather than persisted.
- Missing or legacy values resolve to `default` on both sides, preventing a blank control or invalid CSS state.
- If the auto-save request fails, the existing Settings error state is used and the local selection remains visible for retry.
- The preference does not alter conversation content, stored messages, or model prompts.

## Documentation synchronization

Update the project’s settings/API documentation surfaces required for a new General setting: `AGENTS.md`, `docs/DOC-SYNC.md` references as needed, the canonical API skill reference, and `CHANGELOG.md` under the current unreleased section if present. Keep the user-facing description focused on accessibility and automatic persistence.

## Verification

1. Add backend tests for the default value, invalid-value normalization, API validation, and settings response persistence.
2. Add frontend coverage for rendering the three options, initializing from saved settings, adding the value to auto-save, and applying the selected root scale.
3. Run the existing backend and frontend checks.
4. Build the frontend and inspect the generated app at Default, Large, and xLarge, including an existing conversation, to confirm no critical clipping or broken controls.
