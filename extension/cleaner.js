// The same cleaning logic as trackbye.py (kept in sync by tests/test_parity.js).

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
  let head = q < 0 ? url : url.slice(0, q);
  const query = q < 0 ? null : url.slice(q + 1);
  const authority = head.split('://')[1].split('/')[0];
  const host = authority.split('@').pop().split(':')[0].toLowerCase();
  if (hostMatches(host, rules.exclude_hosts || [])) return url + frag;
  const remove = new Set(rules.global_remove || []);
  const pathRemove = [];
  const product = [];
  for (const site of rules.sites || []) {
    if (hostMatches(host, site.hosts || [])) {
      site.remove.forEach((p) => remove.add(p));
      pathRemove.push(...(site.path_remove || []));
      product.push(...(site.path_product || []));
    }
  }
  // Product pages: ".../Some-Title/dp/B0ABC/ref=x" becomes "/dp/B0ABC/" (the title and anything after the id go).
  if (product.length) {
    const sep = head.indexOf('://') + 3;
    const slash = head.indexOf('/', sep);
    if (slash >= 0) {
      const parts = head.slice(slash + 1).split('/');
      for (let i = 0; i < parts.length - 1; i++) {
        if (product.includes(parts[i]) && parts[i + 1]) {
          const short = [parts[i], parts[i + 1]];
          const same = parts.length === 2 && parts[0] === short[0] && parts[1] === short[1];
          const sameSlash = parts.length === 3 && parts[0] === short[0] && parts[1] === short[1] && parts[2] === '';
          if (!same && !sameSlash) head = head.slice(0, slash + 1) + short.join('/') + '/';
          break;
        }
      }
    }
  }
  // A trailing path segment such as Amazon's "ref=sr_1_6" is dropped; the slash before it stays.
  if (pathRemove.length) {
    const cut = head.lastIndexOf('/');
    const base = head.slice(0, cut);
    if ((base.match(/\//g) || []).length >= 3 && pathRemove.some((p) => head.slice(cut + 1).startsWith(p))) head = base + '/';
  }
  if (query === null) return head + frag;
  const kept = query.split('&').filter((p) => p && !remove.has(p.split('=')[0]));
  return head + (kept.length ? '?' + kept.join('&') : '') + frag;
}
