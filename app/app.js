// ── Settings ─────────────────────────────────────────────────────────────────
const DEFAULTS = { owner: 'baker1129', repo: 'health-project', branch: 'main' };

const cfg = {
  get token()  { return localStorage.getItem('gh_token')  || ''; },
  get owner()  { return localStorage.getItem('gh_owner')  || DEFAULTS.owner; },
  get repo()   { return localStorage.getItem('gh_repo')   || DEFAULTS.repo; },
  get branch() { return localStorage.getItem('gh_branch') || DEFAULTS.branch; },
};

function saveSettings() {
  localStorage.setItem('gh_token',  $('s-token').value.trim());
  localStorage.setItem('gh_owner',  $('s-owner').value.trim()  || DEFAULTS.owner);
  localStorage.setItem('gh_repo',   $('s-repo').value.trim()   || DEFAULTS.repo);
  localStorage.setItem('gh_branch', $('s-branch').value.trim() || DEFAULTS.branch);
}

// ── Draft store ───────────────────────────────────────────────────────────────
const drafts = {};
let currentDate = '';

// ── DOM helpers ───────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

function showMsg(text, type = 'info') {
  const el = $('msg');
  el.textContent = text;
  el.className = `msg ${type}`;
  if (type === 'success') setTimeout(() => { el.className = 'msg hidden'; }, 5000);
}

function setLoading(on) {
  $('submit-btn').disabled = on;
  $('submit-btn').textContent = on ? '送信中...' : '記録する';
}

// ── Date ─────────────────────────────────────────────────────────────────────
function todayLocal() {
  const d = new Date();
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, '0'),
    String(d.getDate()).padStart(2, '0'),
  ].join('-');
}

// ── Base64 (UTF-8 safe) ───────────────────────────────────────────────────────
function toB64(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = '';
  bytes.forEach(b => (bin += String.fromCharCode(b)));
  return btoa(bin);
}

function fromB64(str) {
  const bin = atob(str.replace(/\n/g, ''));
  const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

// ── Draft helpers ─────────────────────────────────────────────────────────────

function saveDraft(date) {
  if (!date) return;
  drafts[date] = {
    weight:     $('weight').value,
    bodyfat:    $('bodyfat').value,
    amBp1:      $('am-bp1').value,
    amBp2:      $('am-bp2').value,
    cpap:       document.querySelector('input[name="cpap"]:checked')?.value || '',
    pmBp1:      $('pm-bp1').value,
    pmBp2:      $('pm-bp2').value,
    eatingOut:  $('eating-out').value,
    snackCount: $('snack-count').value,
    breakfast:  $('breakfast').value,
    lunch:      $('lunch').value,
    dinner:     $('dinner').value,
    foodNote:   $('food-note').value,
    exercise:   $('exercise').value,
  };
}

function applyDraft(draft) {
  $('weight').value      = draft.weight;
  $('bodyfat').value     = draft.bodyfat;
  $('am-bp1').value      = draft.amBp1;
  $('am-bp2').value      = draft.amBp2;
  document.querySelector(`input[name="cpap"][value="${draft.cpap}"]`).checked = true;
  $('pm-bp1').value      = draft.pmBp1;
  $('pm-bp2').value      = draft.pmBp2;
  $('eating-out').value  = draft.eatingOut;
  $('snack-count').value = draft.snackCount;
  $('breakfast').value   = draft.breakfast;
  $('lunch').value       = draft.lunch;
  $('dinner').value      = draft.dinner;
  $('food-note').value   = draft.foodNote;
  $('exercise').value    = draft.exercise;
}

// ── GitHub API ────────────────────────────────────────────────────────────────
const API = 'https://api.github.com';

async function ghGet(path) {
  const r = await fetch(`${API}/repos/${cfg.owner}/${cfg.repo}/contents/${path}`, {
    headers: {
      Authorization: `token ${cfg.token}`,
      Accept: 'application/vnd.github.v3+json',
    },
  });
  if (!r.ok) throw new Error(`GET ${path}: ${r.status}`);
  const d = await r.json();
  return { content: fromB64(d.content), sha: d.sha };
}

async function ghPut(path, content, sha, message) {
  const r = await fetch(`${API}/repos/${cfg.owner}/${cfg.repo}/contents/${path}`, {
    method: 'PUT',
    headers: {
      Authorization: `token ${cfg.token}`,
      Accept: 'application/vnd.github.v3+json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, content: toB64(content), sha, branch: cfg.branch }),
  });
  if (!r.ok) {
    const e = await r.json();
    throw new Error(e.message || String(r.status));
  }
}

// ── File formatters (upsert: 新規→追記 / 差分あり→上書き / 差分なし→null) ──────

function upsertWeight(src, date, weight, bodyfat) {
  if (!weight) return null;
  const newRow = `${date},${weight},${bodyfat || ''}`;
  const lines = src.split('\n');
  const i = lines.findIndex(l => l.startsWith(date + ','));
  if (i === -1) return src.trimEnd() + '\n' + newRow + '\n';
  if (lines[i] === newRow) return null;
  lines[i] = newRow;
  return lines.join('\n');
}

function parseBP(text) {
  if (!text || !text.trim()) return null;
  const p = text.trim().split('/').map(s => Number(s.trim()));
  if (p.length !== 3 || p.some(isNaN)) return null;
  return p;
}

function upsertBP(src, date, time, bp1text, bp2text, memo) {
  const bp1 = parseBP(bp1text);
  if (!bp1) return null;
  const bp2 = parseBP(bp2text) || bp1;
  const newRow = [date, time, ...bp1, ...bp2, memo || ''].join(',');
  const lines = src.split('\n');
  const i = lines.findIndex(l => l.startsWith(`${date},${time},`));
  if (i === -1) return src.trimEnd() + '\n' + newRow + '\n';
  if (lines[i] === newRow) return null;
  lines[i] = newRow;
  return lines.join('\n');
}

function toList(text) {
  if (!text || !text.trim()) return '';
  if (text.trim() === 'なし') return '- なし\n';
  return (
    text
      .split(/[、,，]/)
      .map(s => s.trim())
      .filter(Boolean)
      .map(s => `- ${s}`)
      .join('\n') + '\n'
  );
}

function buildMealsSection(date, { breakfast, lunch, dinner, note, eatingOut, snackCount }) {
  const hasEatingOut  = eatingOut  !== '' && eatingOut  != null;
  const hasSnackCount = snackCount !== '' && snackCount != null;
  if (!breakfast && !lunch && !dinner && !note && !hasEatingOut && !hasSnackCount) return null;
  let s = `## ${date}\n`;
  if (hasEatingOut)  s += `外食: ${eatingOut}回\n`;
  if (hasSnackCount) s += `夜食・間食: ${snackCount}回\n`;
  if (breakfast) s += `\n### 朝\n${toList(breakfast)}`;
  if (lunch)     s += `\n### 昼\n${toList(lunch)}`;
  if (dinner)    s += `\n### 夜\n${toList(dinner)}`;
  if (note)      s += `\n### 気づき\n- ${note.trim()}\n`;
  return s;
}

function buildExerciseSection(date, exercise) {
  if (!exercise || !exercise.trim()) return null;
  return `## ${date}\n- ${exercise.trim()}\n`;
}

// セクション単位でupsert（新規→追記 / 差分あり→置換 / 差分なし→null）
function upsertMdSection(src, date, newSection) {
  if (!newSection) return null;

  const marker = `## ${date}`;
  const useHr  = src.includes('\n---\n');
  const sep    = useHr ? '\n\n---\n\n' : '\n\n';
  const si     = src.indexOf(marker);

  if (si === -1) {
    return src.trimEnd() + sep + newSection.trimEnd() + '\n';
  }

  const rest    = src.slice(si + marker.length);
  const nextH2  = rest.search(/\n## /);
  const oldBody = nextH2 === -1 ? rest : rest.slice(0, nextH2);
  const after   = nextH2 === -1 ? ''   : rest.slice(nextH2 + 1);

  // 差分比較（セパレータ・空白を正規化）
  const norm = s => s.replace(/\n---\n/g, '').replace(/\s+/g, ' ').trim();
  if (norm(marker + oldBody) === norm(newSection)) return null;

  const before = src.slice(0, si);
  if (!after) {
    return before.trimEnd() + '\n\n' + newSection.trimEnd() + '\n';
  }
  return before.trimEnd() + '\n\n' + newSection.trimEnd() + sep + after.trimStart();
}

// ── Existing data parsers ─────────────────────────────────────────────────────

function parseWeight(src, date) {
  const line = src.split('\n').find(l => l.startsWith(date + ','));
  if (!line) return null;
  const [, weight, bodyfat] = line.split(',');
  return { weight: weight || '', bodyfat: (bodyfat || '').trim() };
}

function parseBPRow(src, date, time) {
  const line = src.split('\n').find(l => l.startsWith(`${date},${time},`));
  if (!line) return null;
  const [,, s1, d1, p1, s2, d2, p2, ...memoParts] = line.split(',');
  const bp1 = `${s1}/${d1}/${p1}`;
  const bp2 = `${s2}/${d2}/${p2}`;
  const memo = memoParts.join(',');
  const cpap = memo.includes('cpap:on') ? 'on' : memo.includes('cpap:off') ? 'off' : '';
  return { bp1, bp2: bp1 === bp2 ? '' : bp2, cpap };
}

function parseDateSection(src, date) {
  const idx = src.indexOf(`## ${date}`);
  if (idx === -1) return null;
  const after = src.slice(idx + `## ${date}`.length);
  const end = after.search(/\n## /);
  return end === -1 ? after : after.slice(0, end);
}

function extractCount(section, key) {
  const m = section.match(new RegExp(key + ': (\\d+)回'));
  return m ? m[1] : '';
}

function extractSubsection(section, heading) {
  const idx = section.indexOf(`### ${heading}`);
  if (idx === -1) return '';
  const after = section.slice(idx + `### ${heading}`.length);
  const next = after.search(/\n###/);
  const block = next === -1 ? after : after.slice(0, next);
  return block
    .split('\n')
    .filter(l => l.trim().startsWith('- '))
    .map(l => l.trim().slice(2).trim())
    .filter(Boolean)
    .join('、');
}

// ── Load existing data ────────────────────────────────────────────────────────

function setLoadIndicator(on) {
  $('load-indicator').classList.toggle('hidden', !on);
}

async function loadForDate(date) {
  if (!cfg.token || !date) return;

  if (drafts[date]) {
    applyDraft(drafts[date]);
    return;
  }

  setLoadIndicator(true);

  try {
    const [wFile, bpFile, mealsFile, exFile] = await Promise.all([
      ghGet('logs/daily/weight.csv'),
      ghGet('logs/daily/blood_pressure.csv'),
      ghGet('logs/lifestyle/meals.md'),
      ghGet('logs/lifestyle/exercise.md'),
    ]);

    const w = parseWeight(wFile.content, date);
    $('weight').value  = w?.weight  || '';
    $('bodyfat').value = w?.bodyfat || '';

    const am = parseBPRow(bpFile.content, date, 'morning');
    $('am-bp1').value = am?.bp1 || '';
    $('am-bp2').value = am?.bp2 || '';
    document.querySelector(`input[name="cpap"][value="${am?.cpap || ''}"]`).checked = true;

    const pm = parseBPRow(bpFile.content, date, 'night');
    $('pm-bp1').value = pm?.bp1 || '';
    $('pm-bp2').value = pm?.bp2 || '';

    const mealsSection = parseDateSection(mealsFile.content, date);
    $('eating-out').value  = mealsSection ? extractCount(mealsSection, '外食')       : '';
    $('snack-count').value = mealsSection ? extractCount(mealsSection, '夜食・間食') : '';
    $('breakfast').value   = mealsSection ? extractSubsection(mealsSection, '朝')    : '';
    $('lunch').value       = mealsSection ? extractSubsection(mealsSection, '昼')    : '';
    $('dinner').value      = mealsSection ? extractSubsection(mealsSection, '夜')    : '';
    $('food-note').value   = mealsSection ? extractSubsection(mealsSection, '気づき'): '';

    const exSection = parseDateSection(exFile.content, date);
    $('exercise').value = exSection
      ? exSection.split('\n').filter(l => l.trim().startsWith('- '))
          .map(l => l.trim().slice(2).trim()).filter(Boolean).join('、')
      : '';

  } catch (e) {
    console.error('load error:', e);
  }

  setLoadIndicator(false);
}

// ── Submit ────────────────────────────────────────────────────────────────────
async function submit() {
  if (!cfg.token) {
    showMsg('⚙️ 設定から GitHub Token を入力してください', 'error');
    openSettings();
    return;
  }

  // 現在の入力をドラフトに保存してから全日付を送信
  saveDraft(currentDate);

  const datesToSubmit = Object.keys(drafts).sort();
  if (datesToSubmit.length === 0) {
    showMsg('入力がありません', 'error');
    return;
  }

  setLoading(true);
  showMsg('送信中...', 'info');

  const updated = [], unchanged = [], errors = [];
  const dateLabel = datesToSubmit.length > 1
    ? `${datesToSubmit[0]} 他${datesToSubmit.length - 1}日`
    : datesToSubmit[0];

  // 体重（全日付を1ファイルにまとめて書き込み）
  try {
    const { content, sha } = await ghGet('logs/daily/weight.csv');
    let cur = content, changed = false;
    for (const date of datesToSubmit) {
      const d = drafts[date];
      const next = upsertWeight(cur, date, d.weight, d.bodyfat);
      if (next) { cur = next; changed = true; }
    }
    if (changed) {
      await ghPut('logs/daily/weight.csv', cur, sha, `Update 体重 for ${dateLabel}`);
      updated.push('体重');
    } else {
      unchanged.push('体重');
    }
  } catch (e) {
    errors.push(`体重: ${e.message}`);
  }

  // 血圧（全日付を1ファイルにまとめて書き込み）
  try {
    const { content, sha } = await ghGet('logs/daily/blood_pressure.csv');
    let cur = content, changed = false;
    for (const date of datesToSubmit) {
      const d = drafts[date];
      if (parseBP(d.amBp1)) {
        const next = upsertBP(cur, date, 'morning', d.amBp1, d.amBp2, d.cpap ? `cpap:${d.cpap}` : '');
        if (next) { cur = next; changed = true; }
      }
      if (parseBP(d.pmBp1)) {
        const next = upsertBP(cur, date, 'night', d.pmBp1, d.pmBp2, '');
        if (next) { cur = next; changed = true; }
      }
    }
    if (changed) {
      await ghPut('logs/daily/blood_pressure.csv', cur, sha, `Update BP for ${dateLabel}`);
      updated.push('血圧');
    } else {
      unchanged.push('血圧');
    }
  } catch (e) {
    errors.push(`血圧: ${e.message}`);
  }

  // 食事（全日付を1ファイルにまとめて書き込み）
  try {
    const { content, sha } = await ghGet('logs/lifestyle/meals.md');
    let cur = content, changed = false;
    for (const date of datesToSubmit) {
      const d = drafts[date];
      const next = upsertMdSection(cur, date, buildMealsSection(date, {
        breakfast: d.breakfast, lunch: d.lunch, dinner: d.dinner,
        note: d.foodNote, eatingOut: d.eatingOut, snackCount: d.snackCount,
      }));
      if (next) { cur = next; changed = true; }
    }
    if (changed) {
      await ghPut('logs/lifestyle/meals.md', cur, sha, `Update 食事 for ${dateLabel}`);
      updated.push('食事');
    } else {
      unchanged.push('食事');
    }
  } catch (e) {
    errors.push(`食事: ${e.message}`);
  }

  // 運動（全日付を1ファイルにまとめて書き込み）
  try {
    const { content, sha } = await ghGet('logs/lifestyle/exercise.md');
    let cur = content, changed = false;
    for (const date of datesToSubmit) {
      const d = drafts[date];
      const next = upsertMdSection(cur, date, buildExerciseSection(date, d.exercise));
      if (next) { cur = next; changed = true; }
    }
    if (changed) {
      await ghPut('logs/lifestyle/exercise.md', cur, sha, `Update 運動 for ${dateLabel}`);
      updated.push('運動');
    } else {
      unchanged.push('運動');
    }
  } catch (e) {
    errors.push(`運動: ${e.message}`);
  }

  setLoading(false);

  if (errors.length > 0) {
    showMsg('❌ エラー:\n' + errors.join('\n'), 'error');
  } else {
    const parts = [];
    if (updated.length)   parts.push(`✅ 更新(${dateLabel}): ` + updated.join('・'));
    if (unchanged.length) parts.push('— 変更なし: ' + unchanged.join('・'));
    showMsg(parts.join('\n') || '変更なし', 'success');
    clearForm();
  }
}

function clearForm() {
  Object.keys(drafts).forEach(k => delete drafts[k]);
  ['am-bp1','am-bp2','pm-bp1','pm-bp2','weight','bodyfat',
   'eating-out','snack-count','breakfast','lunch','dinner','food-note','exercise'].forEach(id => {
    $(id).value = '';
  });
  document.querySelector('input[name="cpap"][value=""]').checked = true;
  currentDate = todayLocal();
  $('date').value = currentDate;
}

// ── Settings modal ────────────────────────────────────────────────────────────
function openSettings() {
  $('s-token').value  = cfg.token;
  $('s-owner').value  = cfg.owner;
  $('s-repo').value   = cfg.repo;
  $('s-branch').value = cfg.branch;
  $('settings-modal').classList.remove('hidden');
}

function closeSettings() {
  $('settings-modal').classList.add('hidden');
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  currentDate = todayLocal();
  $('date').value = currentDate;

  $('submit-btn').addEventListener('click', submit);
  $('settings-btn').addEventListener('click', openSettings);
  $('save-settings-btn').addEventListener('click', () => {
    saveSettings();
    closeSettings();
    showMsg('設定を保存しました', 'success');
  });
  $('close-settings-btn').addEventListener('click', closeSettings);
  $('settings-modal').addEventListener('click', e => {
    if (e.target === $('settings-modal')) closeSettings();
  });

  if (!cfg.token) {
    openSettings();
  } else {
    loadForDate(currentDate);
  }

  $('date').addEventListener('change', e => {
    saveDraft(currentDate);
    currentDate = e.target.value;
    loadForDate(currentDate);
  });
});
