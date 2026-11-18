// Runs the shared test vectors against the extension's cleaner. Usage: node tests/test_extension.mjs
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { cleanUrl } from '../extension/cleaner.js';

const rules = JSON.parse(readFileSync(new URL('../extension/rules.json', import.meta.url)));
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
assert.ok(built.length < 600, 'too many rules for the browser: ' + built.length);
console.log('extension rules: ' + built.length + ' rules (max ' + CHUNK + ' names each) OK');

// The path rules (product page shortening) as the browser applies them: first matching rule rewrites the URL, and the
// result must not match any rule again (otherwise the browser would redirect forever).
{
  const { buildRules } = await import('../extension/dnr.js');
  const all = buildRules(rules, []).filter((r) => r.action.redirect.regexSubstitution);
  const apply = (url) => {
    for (const r of all) {
      const re = new RegExp(r.condition.regexFilter);
      if (re.test(url)) return url.replace(re, r.action.redirect.regexSubstitution.replace(/\\(\d)/g, '$$$1'));
    }
    return url;
  };
  const cases = [
    ['https://www.amazon.de/Some-Title/dp/B0ABC/ref=sr_1_6', 'https://www.amazon.de/dp/B0ABC/'],
    ['https://www.amazon.de/Some-Title/dp/B0ABC/ref=sr_1_6?x=1#f', 'https://www.amazon.de/dp/B0ABC/?x=1#f'],
    ['https://www.amazon.de/dp/B0ABC/ref=sr_1_6', 'https://www.amazon.de/dp/B0ABC/'],
    ['https://www.amazon.de/dp/B0ABC/', 'https://www.amazon.de/dp/B0ABC/'],
    ['https://www.amazon.de/dp/B0ABC', 'https://www.amazon.de/dp/B0ABC'],
    ['https://www.amazon.de/s?k=x', 'https://www.amazon.de/s?k=x'],
  ];
  for (const [given, want] of cases) {
    const got = apply(given);
    assert.strictEqual(got, want, given);
    assert.strictEqual(apply(got), got, 'must not rewrite again: ' + got);
  }
  console.log('extension path rules: ' + cases.length + ' cases OK');
}
