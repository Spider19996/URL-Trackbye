import { cleanUrl } from './cleaner.js';
import { buildRules } from './dnr.js';

const HOST = 'de.trackbye.host';
const VERSION = chrome.runtime.getManifest().version; // reported to the program, which warns when it is outdated
const DEFAULT_SETTINGS = { enabled: true, disabledSites: [] };

async function getSettings() {
  return Object.assign({}, DEFAULT_SETTINGS, await chrome.storage.local.get(DEFAULT_SETTINGS));
}

// Rules from the trackbye program if it is installed (they include your own additions), else the bundled copy.
async function loadRules() {
  try {
    const reply = await chrome.runtime.sendNativeMessage(HOST, { type: 'rules', ext: VERSION });
    if (reply && reply.ok && reply.rules) return { rules: reply.rules, source: 'program' };
  } catch (e) { /* program not installed: use the bundled rules */ }
  const bundled = await (await fetch(chrome.runtime.getURL('rules.json'))).json();
  return { rules: bundled, source: 'bundled' };
}

// Colored icon while cleaning, gray icon while switched off.
function setIconState(enabled) {
  const prefix = enabled ? 'icon' : 'off';
  chrome.action.setIcon({ path: { 16: 'icons/' + prefix + '16.png', 32: 'icons/' + prefix + '32.png', 48: 'icons/' + prefix + '48.png' } });
  chrome.action.setTitle({ title: enabled ? 'URL Trackbye' : 'URL Trackbye (off)' });
}

let logRules = null; // what the Firefox fallback logging needs: the active rules and the sites switched off

async function applyRules() {
  const settings = await getSettings();
  setIconState(settings.enabled);
  const { rules, source } = await loadRules();
  logRules = settings.enabled ? { rules, disabledSites: settings.disabledSites } : null;
  const add = settings.enabled ? buildRules(rules, settings.disabledSites) : [];
  try {
    const old = await chrome.declarativeNetRequest.getDynamicRules();
    await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: old.map((r) => r.id), addRules: add });
  } catch (e) {
    // Without these rules nothing is cleaned in the browser: tell the program, so it shows up in its Messages.
    reportDiag('error', 'The browser extension could not install its cleaning rules: ' + e.message);
    throw e;
  }
  await chrome.storage.local.set({ status: { source, ruleCount: add.length, time: Date.now() } });
}

// Long-lived connection to the program: it can tell this extension to reload itself right away (new version on disk,
// or `trackbye reload-extension`). The open port also keeps this service worker alive.
let port = null;

// Only an unpacked / temporary install ("development") picks up new files when it reloads. An installed, signed or
// store version would just load the same code again and again, so it never reloads itself on request.
async function isDevInstall() {
  try { return (await chrome.management.getSelf()).installType === 'development'; } catch (e) { return false; }
}

async function connectHost() {
  if (port) return;
  try {
    const connection = chrome.runtime.connectNative(HOST);
    port = connection;
    const dev = await isDevInstall();
    connection.onMessage.addListener((msg) => { if (dev && msg && msg.type === 'reload') chrome.runtime.reload(); });
    connection.onDisconnect.addListener(() => { port = null; void chrome.runtime.lastError; });
    connection.postMessage({ type: 'hello', ext: VERSION, dev });
  } catch (e) { port = null; }
}
connectHost();

function reportDiag(level, message) {
  chrome.runtime.sendNativeMessage(HOST, { type: 'diag', level, message, ext: VERSION }).catch(() => {});
}

// Tell the program which links the browser cleaned, so they show up in its log. Only an unpacked extension gets these
// match events; for the program the cleaning is simply repeated on the original address.
function reportToLog(source, url) {
  chrome.runtime.sendNativeMessage(HOST, { type: 'log', source, url, ext: VERSION }).catch(() => {});
}
if (chrome.declarativeNetRequest.onRuleMatchedDebug) {
  chrome.declarativeNetRequest.onRuleMatchedDebug.addListener((info) => {
    if (info.request && info.request.type === 'main_frame') reportToLog('browser', info.request.url);
  });
} else if (chrome.webRequest && chrome.webRequest.onBeforeRequest) {
  // Firefox has no match events: watch the original request (without changing it) and report links that carry
  // tracking parts. The rules from the last applyRules() tell what the cleaning will remove.
  chrome.webRequest.onBeforeRequest.addListener((details) => {
    if (!logRules) return;
    let host = '';
    try { host = new URL(details.url).hostname; } catch (e) { return; }
    if (logRules.disabledSites.includes(host)) return;
    if (cleanUrl(details.url, logRules.rules) !== details.url) reportToLog('browser', details.url);
  }, { urls: ['http://*/*', 'https://*/*'], types: ['main_frame'] });
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
  reportToLog('browser-copy', info.linkUrl);
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
    const reply = await chrome.runtime.sendNativeMessage(HOST, { type: 'version', ext: VERSION });
    if (reply && reply.ok && reply.version && reply.version !== chrome.runtime.getManifest().version && await isDevInstall()) {
      chrome.runtime.reload();
    }
  } catch (e) { /* program not installed */ }
}

async function refresh() {
  connectHost();
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
