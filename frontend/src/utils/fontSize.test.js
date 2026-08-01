import test from 'node:test';
import assert from 'node:assert/strict';
import {
  FONT_SIZE_OPTIONS,
  applyFontSize,
  getFontScale,
  normalizeFontSize,
} from './fontSize.js';

test('normalizes missing and invalid font-size values to default', () => {
  assert.equal(normalizeFontSize(undefined), 'default');
  assert.equal(normalizeFontSize('giant'), 'default');
  assert.equal(normalizeFontSize('xlarge'), 'xlarge');
});

test('returns the approved relative scale for each font-size option', () => {
  assert.equal(getFontScale('default'), 1.1);
  assert.equal(getFontScale('large'), 1.5);
  assert.equal(getFontScale('xlarge'), 2);
  assert.deepEqual(
    FONT_SIZE_OPTIONS.map(({ value, scale }) => ({ value, scale })),
    [
      { value: 'default', scale: 1.1 },
      { value: 'large', scale: 1.5 },
      { value: 'xlarge', scale: 2 },
    ],
  );
});

test('applies the normalized option to the shared root', () => {
  const root = {
    dataset: {},
    style: {
      values: {},
      setProperty(name, value) {
        this.values[name] = value;
      },
    },
  };

  assert.equal(applyFontSize('large', root), 'large');
  assert.equal(root.dataset.fontSize, 'large');
  assert.equal(root.style.values['--font-scale'], '1.5');
});
