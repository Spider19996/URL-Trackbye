import { cleanUrl } from './cleaner.js';

const HOST = 'de.trackbye.host';
const DEFAULT_SETTINGS = { enabled: true, disabledSites: [] };

async function getSettings() {
  return Object.assign({}, DEFAULT_SETTINGS, await chrome.storage.local.get(DEFAULT_SETTINGS));
}

// Rules from the trackbye program if it is installed (they include your own additions), else the bundled copy.
async function loadRules() {
  try {
    const reply = await chrome.runtime.sendNativeMessage(HOST, { type: 'rules' });
    if (reply && reply.ok && reply.rules) return { rules: reply.rules, source: 'program' };
  } catch (e) { /* program not installed: use the bundled rules */ }
  const bundled = await (await fetch(chrome.runtime.getURL('rules.json'))).json();
  return { rules: bundled, source: 'bundled' };
}

const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

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

async function applyRules() {
  const settings = await getSettings();
  const { rules, source } = await loadRules();
  const excluded = (rules.exclude_hosts || []).concat(settings.disabledSites);
  const add = [];
  if (settings.enabled) {
    let id = 1;
    if ((rules.global_remove || []).length) add.push(redirectRule(id++, rules.global_remove, null, excluded));
    for (const site of rules.sites || []) {
      if (site.remove && site.remove.length && site.hosts && site.hosts.length) {
        add.push(redirectRule(id++, site.remove, site.hosts, excluded));
      }
    }
  }
  const old = await chrome.declarativeNetRequest.getDynamicRules();
  await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: old.map((r) => r.id), addRules: add });
  await chrome.storage.local.set({ status: { source, ruleCount: add.length, time: Date.now() } });
}

// Context menu: copy the address of a link without tracking parameters.
function setupMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: 'copy-clean-link', title: 'Copy clean link address', contexts: ['link'] });
  });
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== 'copy-clean-link' || !tab) return;
  const { rules } = await loadRules();
  const text = cleanUrl(info.linkUrl, rules);
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (value) => {
      const fallback = () => {
        const ta = document.createElement('textarea');
        ta.value = value;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(value).catch(fallback);
      else fallback();
    },
    args: [text],
  });
});

// With the program installed: pick up changed rules regularly, and reload this extension when the program's copy of
// it (the files on disk) has a newer version. For an unpacked extension, reload() re-reads the files from disk.
async function checkForUpdate() {
  try {
    const reply = await chrome.runtime.sendNativeMessage(HOST, { type: 'version' });
    if (reply && reply.ok && reply.version && reply.version !== chrome.runtime.getManifest().version) {
      chrome.runtime.reload();
    }
  } catch (e) { /* program not installed */ }
}

async function refresh() {
  await checkForUpdate();
  await applyRules();
}

chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === 'refresh') refresh(); });
function scheduleRefresh() { chrome.alarms.create('refresh', { periodInMinutes: 30 }); }

chrome.runtime.onInstalled.addListener(() => { setupMenu(); scheduleRefresh(); applyRules(); });
chrome.runtime.onStartup.addListener(() => { scheduleRefresh(); refresh(); });
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && (changes.enabled || changes.disabledSites)) applyRules();
});
chrome.runtime.onMessage.addListener((msg) => { if (msg && msg.type === 'refresh') refresh(); });
