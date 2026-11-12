import { cleanUrl } from './cleaner.js';

const T = {
  en: { enabled: 'Clean links automatically', site: 'Not on this site:', copy: 'Copy clean address of this tab',
    copied: 'Copied.', nothing: 'No address found.', program: 'Rules from the linkfeger program', bundled: 'Bundled rules (program not found)' },
  de: { enabled: 'Links automatisch säubern', site: 'Nicht auf dieser Seite:', copy: 'Saubere Adresse dieses Tabs kopieren',
    copied: 'Kopiert.', nothing: 'Keine Adresse gefunden.', program: 'Regeln vom linkfeger-Programm', bundled: 'Mitgelieferte Regeln (Programm nicht gefunden)' },
};
const t = T[(navigator.language || 'en').slice(0, 2)] || T.en;
document.querySelectorAll('[data-i18n]').forEach((e) => { e.textContent = t[e.dataset.i18n]; });

const $ = (id) => document.getElementById(id);

async function main() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let host = '';
  try { host = new URL(tab.url).hostname; } catch (e) { /* no web page */ }
  $('host').textContent = host;
  const s = await chrome.storage.local.get({ enabled: true, disabledSites: [], status: null });
  $('enabled').checked = s.enabled;
  $('site').checked = s.disabledSites.includes(host);
  $('site').disabled = !host;
  if (s.status) $('status').textContent = (s.status.source === 'program' ? t.program : t.bundled) + ' · ' + s.status.ruleCount;

  $('enabled').addEventListener('change', () => chrome.storage.local.set({ enabled: $('enabled').checked }));
  $('site').addEventListener('change', async () => {
    const cur = (await chrome.storage.local.get({ disabledSites: [] })).disabledSites.filter((h) => h !== host);
    await chrome.storage.local.set({ disabledSites: $('site').checked ? cur.concat(host) : cur });
  });
  $('copy').addEventListener('click', async () => {
    if (!tab || !tab.url) { $('msg').textContent = t.nothing; return; }
    const rules = await (await fetch(chrome.runtime.getURL('rules.json'))).json();
    let program = null;
    try { const r = await chrome.runtime.sendNativeMessage('de.linkfeger.host', { type: 'rules' }); if (r && r.ok) program = r.rules; } catch (e) { /* none */ }
    await navigator.clipboard.writeText(cleanUrl(tab.url, program || rules));
    $('msg').textContent = t.copied;
  });
}
main();
