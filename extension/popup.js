import { cleanUrl } from './cleaner.js';

const HOST = 'de.trackbye.host';
const VERSION = chrome.runtime.getManifest().version;
const T = {
  en: {
    subtitle: 'Removes tracking from links', prefs: 'Preferences', page: 'This page', stats: 'Statistics',
    enabled: 'Clean links automatically', site: 'Not on this site:', sync: 'Refresh', synced: 'Updated {t}',
    rulesProgram: 'Rules from the program', rulesBundled: 'Bundled rules', ruleCount: '{n} rules',
    address: 'Address of this tab', clean: 'Without tracking', copy: 'Copy clean address', copied: 'Copied.',
    nothing: 'No web page open.', same: 'This address has no tracking parts.',
    today: 'Cleaned today', total: 'Cleaned in total', recent: 'Recently cleaned', noStats: 'Statistics need the URL Trackbye program (see the README).',
    noneYet: 'Nothing cleaned yet.', removed: 'Removed:', progOn: 'Program connected', progOff: 'Program not found (bundled rules)',
    perm: 'The browser has not yet allowed access to all websites, so no links are cleaned.', grant: 'Allow access to all websites',
    justNow: 'just now', minAgo: '{n} min ago', hAgo: '{n} h ago', dAgo: '{n} d ago',
  },
  de: {
    subtitle: 'Entfernt Tracking aus Links', prefs: 'Einstellungen', page: 'Diese Seite', stats: 'Statistik',
    enabled: 'Links automatisch säubern', site: 'Nicht auf dieser Seite:', sync: 'Aktualisieren', synced: 'Aktualisiert {t}',
    rulesProgram: 'Regeln vom Programm', rulesBundled: 'Mitgelieferte Regeln', ruleCount: '{n} Regeln',
    address: 'Adresse dieses Tabs', clean: 'Ohne Tracking', copy: 'Saubere Adresse kopieren', copied: 'Kopiert.',
    nothing: 'Keine Webseite geöffnet.', same: 'Diese Adresse hat keine Tracking-Teile.',
    today: 'Heute gesäubert', total: 'Insgesamt gesäubert', recent: 'Zuletzt gesäubert', noStats: 'Die Statistik braucht das Programm URL Trackbye (siehe README).',
    noneYet: 'Noch nichts gesäubert.', removed: 'Entfernt:', progOn: 'Programm verbunden', progOff: 'Programm nicht gefunden (mitgelieferte Regeln)',
    perm: 'Der Browser hat den Zugriff auf alle Webseiten noch nicht erlaubt, deshalb werden keine Links gesäubert.', grant: 'Zugriff auf alle Webseiten erlauben',
    justNow: 'gerade eben', minAgo: 'vor {n} Min.', hAgo: 'vor {n} Std.', dAgo: 'vor {n} Tg.',
  },
};
const t = T[(navigator.language || 'en').slice(0, 2)] || T.en;
const fill = (s, vars) => s.replace(/\{(\w+)\}/g, (_, k) => vars[k]);
const $ = (id) => document.getElementById(id);
const ALL_SITES = { origins: ['http://*/*', 'https://*/*'] };

function ago(ms) {
  const min = Math.round((Date.now() - ms) / 60000);
  if (min < 1) return t.justNow;
  if (min < 60) return fill(t.minAgo, { n: min });
  if (min < 1440) return fill(t.hAgo, { n: Math.round(min / 60) });
  return fill(t.dAgo, { n: Math.round(min / 1440) });
}

async function ask(msg) {
  try {
    const reply = await chrome.runtime.sendNativeMessage(HOST, Object.assign({ ext: VERSION }, msg));
    return reply && reply.ok ? reply : null;
  } catch (e) { return null; }
}

function texts() {
  document.documentElement.lang = (navigator.language || 'en').slice(0, 2);
  $('subtitle').textContent = t.subtitle;
  $('tabPrefs').textContent = t.prefs;
  $('tabPage').textContent = t.page;
  $('tabStats').textContent = t.stats;
  $('lblEnabled').textContent = t.enabled;
  $('lblSite').textContent = t.site;
  $('sync').textContent = t.sync;
  $('lblAddress').textContent = t.address;
  $('lblClean').textContent = t.clean;
  $('copy').textContent = t.copy;
  $('lblToday').textContent = t.today;
  $('lblTotal').textContent = t.total;
  $('lblRecent').textContent = t.recent;
  $('noStats').textContent = t.noStats;
  $('permText').textContent = t.perm;
  $('grant').textContent = t.grant;
  $('version').textContent = 'v' + VERSION;
}

function tabs() {
  const buttons = document.querySelectorAll('.tab');
  buttons.forEach((b) => b.addEventListener('click', () => {
    buttons.forEach((x) => x.classList.toggle('active', x === b));
    document.querySelectorAll('.panel').forEach((p) => { p.hidden = p.id !== b.dataset.tab; });
    if (b.dataset.tab === 'stats') loadStats();
  }));
}

// Firefox does not always grant the "all websites" access at install; without it nothing can be cleaned.
async function checkHostAccess() {
  try {
    if (await chrome.permissions.contains(ALL_SITES)) return;
  } catch (e) { return; }
  $('perm').hidden = false;
  $('grant').addEventListener('click', async () => {
    if (await chrome.permissions.request(ALL_SITES)) {
      $('perm').hidden = true;
      chrome.runtime.sendMessage({ type: 'refresh' }).catch(() => {});
    }
  });
}

async function showStatus() {
  const { status } = await chrome.storage.local.get({ status: null });
  const program = await ask({ type: 'version' });
  $('dot').classList.toggle('on', !!program);
  $('progState').textContent = program ? t.progOn : t.progOff;
  if (!status) { $('statusTitle').textContent = '…'; return; }
  $('statusTitle').textContent = status.source === 'program' ? t.rulesProgram : t.rulesBundled;
  $('statusSub').innerHTML = '';
  const count = document.createElement('span');
  count.textContent = fill(t.ruleCount, { n: status.ruleCount }) + ' · ';
  const when = document.createElement('span');
  when.className = 'ok';
  when.textContent = fill(t.synced, { t: ago(status.time) });
  $('statusSub').append(count, when);
}

async function loadStats() {
  const stats = await ask({ type: 'stats' });
  $('noStats').hidden = !!stats;
  $('recent').innerHTML = '';
  if (!stats) { $('nToday').textContent = '–'; $('nTotal').textContent = '–'; return; }
  $('nToday').textContent = stats.today;
  $('nTotal').textContent = stats.total;
  if (!stats.recent.length) {
    const li = document.createElement('li');
    li.className = 'muted';
    li.textContent = t.noneYet;
    $('recent').append(li);
  }
  for (const e of stats.recent) {
    const li = document.createElement('li');
    const to = document.createElement('div');
    to.className = 'to';
    to.textContent = e.to;
    const removed = document.createElement('div');
    removed.className = 'removed';
    removed.textContent = t.removed + ' ' + e.removed.join(', ');
    li.append(to, removed);
    $('recent').append(li);
  }
}

async function main() {
  texts();
  tabs();
  chrome.runtime.sendMessage({ type: 'refresh' }).catch(() => {});
  checkHostAccess();
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let host = '';
  try { host = new URL(tab.url).hostname; } catch (e) { /* no web page */ }
  $('host').textContent = host;
  const s = await chrome.storage.local.get({ enabled: true, disabledSites: [] });
  $('enabled').checked = s.enabled;
  $('site').checked = s.disabledSites.includes(host);
  $('site').disabled = !host;
  await showStatus();
  setTimeout(showStatus, 1200);

  $('enabled').addEventListener('change', () => chrome.storage.local.set({ enabled: $('enabled').checked }));
  $('site').addEventListener('change', async () => {
    const cur = (await chrome.storage.local.get({ disabledSites: [] })).disabledSites.filter((h) => h !== host);
    await chrome.storage.local.set({ disabledSites: $('site').checked ? cur.concat(host) : cur });
  });
  $('sync').addEventListener('click', async () => {
    chrome.runtime.sendMessage({ type: 'refresh' }).catch(() => {});
    setTimeout(showStatus, 900);
  });

  // "This page": the address and its clean version
  let rules = await (await fetch(chrome.runtime.getURL('rules.json'))).json();
  const fromProgram = await ask({ type: 'rules' });
  if (fromProgram && fromProgram.rules) rules = fromProgram.rules;
  const url = tab && tab.url && /^https?:/i.test(tab.url) ? tab.url : '';
  const cleaned = url ? cleanUrl(url, rules) : '';
  $('currentUrl').textContent = url || t.nothing;
  $('cleanUrl').textContent = url ? (cleaned === url ? t.same : cleaned) : '–';
  $('copy').disabled = !url;
  $('copy').addEventListener('click', async () => {
    await navigator.clipboard.writeText(cleaned || url);
    $('msg').textContent = t.copied;
  });
}
main();
