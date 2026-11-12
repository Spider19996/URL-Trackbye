// Runs the shared test vectors against the extension's cleaner. Usage: node tests/test_extension.mjs
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { cleanUrl } from '../extension/cleaner.js';

const rules = JSON.parse(readFileSync(new URL('../rules.json', import.meta.url)));
const vectors = JSON.parse(readFileSync(new URL('./vectors.json', import.meta.url)));
for (const [given, expected] of vectors) assert.equal(cleanUrl(given, rules), expected, given);
console.log('extension cleaner: ' + vectors.length + ' vectors OK');
