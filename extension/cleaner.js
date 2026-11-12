// The same cleaning logic as linkbroom.py (kept in sync by tests/test_parity.js).

export function hostMatches(host, domains) {
  return domains.some((d) => host === d || host.endsWith('.' + d));
}

export function isUrl(text) {
  const t = text.trim();
  return /^https?:\/\//i.test(t) && !/\s/.test(t);
}

export function cleanUrl(input, rules) {
  if (!isUrl(input)) return input;
  let url = input.trim();
  let frag = '';
  const hash = url.indexOf('#');
  if (hash >= 0) { frag = url.slice(hash); url = url.slice(0, hash); }
  const q = url.indexOf('?');
  if (q < 0) return url + frag;
  const head = url.slice(0, q);
  const query = url.slice(q + 1);
  const authority = head.split('://')[1].split('/')[0];
  const host = authority.split('@').pop().split(':')[0].toLowerCase();
  if (hostMatches(host, rules.exclude_hosts || [])) return head + '?' + query + frag;
  const remove = new Set(rules.global_remove || []);
  for (const site of rules.sites || []) {
    if (hostMatches(host, site.hosts || [])) site.remove.forEach((p) => remove.add(p));
  }
  const kept = query.split('&').filter((p) => p && !remove.has(p.split('=')[0]));
  return head + (kept.length ? '?' + kept.join('&') : '') + frag;
}
