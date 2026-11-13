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

export function buildRules(rules, disabledSites) {
  const excluded = (rules.exclude_hosts || []).concat(disabledSites || []);
  const out = [];
  let id = 1;
  for (const part of chunks(rules.global_remove || [], CHUNK)) out.push(redirectRule(id++, part, null, excluded));
  for (const site of rules.sites || []) {
    if (!site.remove || !site.remove.length || !site.hosts || !site.hosts.length) continue;
    for (const part of chunks(site.remove, CHUNK)) out.push(redirectRule(id++, part, site.hosts, excluded));
  }
  return out;
}
