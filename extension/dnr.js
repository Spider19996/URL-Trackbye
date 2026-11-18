// Builds the declarativeNetRequest rules from the rule list.
//
// Chrome compiles every regexFilter and refuses ("exceeded the 2KB memory limit") a regex with too many names, and one
// refused rule makes the whole update fail. So the parameter names go into small chunks, one rule per chunk.

export const CHUNK = 8;

const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function chunks(list, size) {
  const out = [];
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size));
  return out;
}

function redirectRule(id, names, domains, excluded) {
  const condition = {
    regexFilter: '[?&](' + names.map(escapeRegex).join('|') + ')(=|&|#|$)',
    resourceTypes: ['main_frame', 'sub_frame'],
  };
  if (domains) condition.requestDomains = domains;
  if (excluded.length) condition.excludedRequestDomains = excluded;
  return {
    id, priority: 1,
    action: { type: 'redirect', redirect: { transform: { queryTransform: { removeParams: names } } } },
    condition,
  };
}

// Drops a trailing path segment that starts with one of the given prefixes (e.g. "ref="), keeping the slash before it.
function pathRule(id, prefixes, domains, excluded) {
  const condition = {
    regexFilter: '^(https?://[^/?#]+/(?:[^?#]*/)?)(?:' + prefixes.map(escapeRegex).join('|') + ')[^/?#]*([?#].*)?$',
    resourceTypes: ['main_frame', 'sub_frame'],
    requestDomains: domains,
  };
  if (excluded.length) condition.excludedRequestDomains = excluded;
  return { id, priority: 1, action: { type: 'redirect', redirect: { regexSubstitution: '\\1\\2' } }, condition };
}

// Product pages: "/Some-Title/dp/B0ABC/ref=x" -> "/dp/B0ABC/". Two rules, so that the result (which must not match
// again, or the redirect would loop) is left alone: A needs something before the marker, B something after the id.
function productRules(ids, markers, domains, excluded) {
  const m = '(' + markers.map(escapeRegex).join('|') + ')';
  const make = (id, regexFilter) => {
    const condition = { regexFilter, resourceTypes: ['main_frame', 'sub_frame'], requestDomains: domains };
    if (excluded.length) condition.excludedRequestDomains = excluded;
    return { id, priority: 1, action: { type: 'redirect', redirect: { regexSubstitution: '\\1\\2/\\3/\\4' } }, condition };
  };
  return [
    make(ids[0], '^(https?://[^/?#]+/)[^?#]*/' + m + '/([^/?#]+)(?:/[^?#]*)?([?#].*)?$'),
    make(ids[1], '^(https?://[^/?#]+/)' + m + '/([^/?#]+)/[^?#]+([?#].*)?$'),
  ];
}

export function buildRules(rules, disabledSites) {
  const excluded = (rules.exclude_hosts || []).concat(disabledSites || []);
  const out = [];
  let id = 1;
  for (const part of chunks(rules.global_remove || [], CHUNK)) out.push(redirectRule(id++, part, null, excluded));
  for (const site of rules.sites || []) {
    if (!site.hosts || !site.hosts.length) continue;
    if (site.path_product && site.path_product.length) {
      out.push(...productRules([id, id + 1], site.path_product, site.hosts, excluded));
      id += 2;
    }
    if (site.path_remove && site.path_remove.length) out.push(pathRule(id++, site.path_remove, site.hosts, excluded));
    if (!site.remove || !site.remove.length) continue;
    for (const part of chunks(site.remove, CHUNK)) out.push(redirectRule(id++, part, site.hosts, excluded));
  }
  return out;
}
