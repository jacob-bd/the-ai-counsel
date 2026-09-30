import { createContext, useContext } from 'react';
import zhTW from './locales/zh-TW.js';

export const I18nContext = createContext(null);
const catalogs = { 'zh-TW': zhTW };

export function translate(source, language, values = {}) {
  const phrase = catalogs[language]?.[source] ?? source;
  return phrase.replace(/\{([a-zA-Z0-9_]+)\}/g, (match, key) => (
    Object.hasOwn(values, key) ? String(values[key]) : match
  ));
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error('useI18n must be used inside LocaleProvider');
  return context;
}
