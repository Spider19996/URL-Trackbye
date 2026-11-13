// Runs the shared test vectors against the extension's cleaner. Usage: node tests/test_extension.mjs
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { cleanUrl } from '../extension/cleaner.js';

const rules = JSON.parse(readFileSync(new URL('../rules.json', import.meta.url)));
const vectors = JSON.parse(readFileSync(new URL('./vectors.json', import.meta.url)));
for (const [given, expected] of vectors) assert.equal(cleanUrl(given, rules), expected, given);
console.log('extension cleaner: ' + vectors.length + ' vectors OK');

// The rules the extension installs: small regexes (Chrome refuses big ones), and they cover every parameter.
import { buildRules, CHUNK } from '../extension/dnr.js';
const built = buildRules(rules, []);
const ids = new Set(built.map((r) => r.id));
assert.equal(ids.size, built.length, 'rule ids must be unique');
for (const r of built) assert.ok(r.condition.regexFilter.length < 200, 'regexFilter too long: ' + r.condition.regexFilter.length);
for (const name of rules.global_remove) {
  const hit = built.filter((r) => !r.condition.requestDomains && new RegExp(r.condition.regexFilter).test('https://a.com/?x=1&' + name + '=2'));
  assert.equal(hit.length, 1, 'global parameter not covered: ' + name);
}
for (const site of rules.sites) {
  for (const name of site.remove) {
    const hit = built.filter((r) => r.condition.requestDomains && r.condition.requestDomains.includes(site.hosts[0]) &&
      new RegExp(r.condition.regexFilter).test('https://x.com/?' + name + '=2'));
    assert.ok(hit.length >= 1, 'site parameter not covered: ' + site.name + ' ' + name);
  }
}
console.log('extension rules: ' + built.length + ' rules (max ' + CHUNK + ' names each) OK');
