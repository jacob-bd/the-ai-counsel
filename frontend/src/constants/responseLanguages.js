/**
 * UI fallback for response languages. Canonical source: backend/prompts.py
 * VALID_RESPONSE_LANGUAGES. The Settings UI prefers GET /api/settings →
 * valid_response_languages when the backend is up to date.
 */
export const RESPONSE_LANGUAGE_DEFAULT = 'English';

export const RESPONSE_LANGUAGES_FALLBACK = [
  RESPONSE_LANGUAGE_DEFAULT,
  'Spanish',
  'French',
  'German',
  'Italian',
  'Portuguese',
  'Dutch',
  'Polish',
  'Russian',
  'Ukrainian',
  'Arabic',
  'Hebrew',
  'Hindi',
  'Japanese',
  'Korean',
  'Chinese (Simplified)',
  'Chinese (Traditional)',
  'Greek',
];
