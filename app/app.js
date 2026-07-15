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

function getRadio(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || '';
}

function setRadio(name, value) {
  const el = document.querySelector(`input[name="${name}"][value="${value}"]`);
  document.querySelectorAll(`input[name="${name}"]`).forEach(r => (r.checked = false));
  if (el) el.checked = true;
}

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
  const draft = {
    weight:     $('weight').value,
    bodyfat:    $('bodyfat').value,
    amBp1:      $('am-bp1').value,
    amBp2:      $('am-bp2').value,
    cpap:       getRadio('cpap'),
    pmBp1:      $('pm-bp1').value,
    pmBp2:      $('pm-bp2').value,
    eatingOut:  $('eating-out').value,
    nightSnack: getRadio('night-snack'),
    snack:      getRadio('snack'),
    breakfast:  $('breakfast').value,
    lunch:      $('lunch').value,
    dinner:     $('dinner').value,
    foodNote:   $('food-note').value,
    exercise:   $('exercise').value,
  };
  const hasData = !!(
    draft.weight || draft.bodyfat ||
    draft.amBp1 || draft.amBp2 || draft.cpap ||
    draft.pmBp1 || draft.pmBp2 ||
    draft.eatingOut !== '' || draft.nightSnack || draft.snack ||
    draft.breakfast || draft.lunch || draft.dinner ||
    draft.foodNote || draft.exercise
  );
  if (hasData) {
    drafts[date] = draft;
  } else {
    delete drafts[date];
  }
  persistDrafts();
}

// リロードや誤タブクローズで未送信の入力が消えないよう、下書きをlocalStorageにも保存する
function persistDrafts() {
  localStorage.setItem('health_drafts', JSON.stringify(drafts));
}

function restoreDrafts() {
  try {
    const saved = JSON.parse(localStorage.getItem('health_drafts') || '{}');
    Object.assign(drafts, saved);
  } catch (e) {
    console.error('draft restore error:', e);
  }
}

function applyDraft(draft) {
  $('weight').value      = draft.weight;
  $('bodyfat').value     = draft.bodyfat;
  $('am-bp1').value      = draft.amBp1;
  $('am-bp2').value      = draft.amBp2;
  setRadio('cpap', draft.cpap);
  $('pm-bp1').value      = draft.pmBp1;
  $('pm-bp2').value      = draft.pmBp2;
  $('eating-out').value  = draft.eatingOut;
  setRadio('night-snack', draft.nightSnack);
  setRadio('snack', draft.snack);
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
  // 血圧未計測でもCPAPだけは記録できるよう、血圧欄は空のまま行を作る
  if (!bp1 && !memo) return null;
  const bp2 = bp1 ? (parseBP(bp2text) || bp1) : null;
  const bpFields = bp1 ? [...bp1, ...bp2] : ['', '', '', '', '', ''];
  const newRow = [date, time, ...bpFields, memo || ''].join(',');
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

function buildMealsSection(date, { breakfast, lunch, dinner, note, eatingOut, nightSnack, snack }) {
  const hasEatingOut = eatingOut !== '' && eatingOut != null;
  if (!breakfast && !lunch && !dinner && !note && !hasEatingOut && !nightSnack && !snack) return null;
  let s = `## ${date}\n`;
  if (hasEatingOut) s += `外食: ${eatingOut}回\n`;
  if (nightSnack)   s += `夜食: ${nightSnack}\n`;
  if (snack)        s += `間食: ${snack}\n`;
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
  const hasBp1 = s1 !== '' && d1 !== '' && p1 !== '';
  const hasBp2 = s2 !== '' && d2 !== '' && p2 !== '';
  const bp1 = hasBp1 ? `${s1}/${d1}/${p1}` : '';
  const bp2 = hasBp2 ? `${s2}/${d2}/${p2}` : '';
  const memo = memoParts.join(',');
  const cpap = memo.includes('cpap:on') ? 'on' : memo.includes('cpap:off') ? 'off' : '';
  return { bp1, bp2: bp1 && bp1 === bp2 ? '' : bp2, cpap };
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

function extractYesNo(section, key) {
  const m = section.match(new RegExp('^' + key + ': (あり|なし)', 'm'));
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
  // 既存データの取得が終わるまでは送信をブロックする（未取得のフィールドが
  // 空のまま送信され、記録済みの内容を上書き消去してしまうのを防ぐ）
  $('submit-btn').disabled = true;

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
    setRadio('cpap', am?.cpap || '');

    const pm = parseBPRow(bpFile.content, date, 'night');
    $('pm-bp1').value = pm?.bp1 || '';
    $('pm-bp2').value = pm?.bp2 || '';

    const mealsSection = parseDateSection(mealsFile.content, date);
    $('eating-out').value  = mealsSection ? extractCount(mealsSection, '外食') : '';
    setRadio('night-snack', mealsSection ? extractYesNo(mealsSection, '夜食') : '');
    setRadio('snack',       mealsSection ? extractYesNo(mealsSection, '間食') : '');
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
    const is401 = e.message && e.message.includes(': 401');
    if (is401) {
      showMsg('⚙️ GitHub Tokenが無効または期限切れです。設定を確認してください', 'error');
      openSettings();
    } else {
      showMsg(`読み込みエラー: ${e.message}`, 'error');
    }
  }

  setLoadIndicator(false);
  $('submit-btn').disabled = false;
}

// ── Submit ────────────────────────────────────────────────────────────────────
// 4ファイルはそれぞれ独立しているため、並列に読み書きして登録を高速化する。
// 各submitXxxはghGet/ghPutの結果を{label, status: 'updated'|'unchanged'|'error', message?}に正規化して返す。

async function submitWeight(datesToSubmit, dateLabel) {
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
      return { label: '体重', status: 'updated' };
    }
    return { label: '体重', status: 'unchanged' };
  } catch (e) {
    return { label: '体重', status: 'error', message: e.message };
  }
}

async function submitBP(datesToSubmit, dateLabel) {
  try {
    const { content, sha } = await ghGet('logs/daily/blood_pressure.csv');
    let cur = content, changed = false;
    for (const date of datesToSubmit) {
      const d = drafts[date];
      if (parseBP(d.amBp1) || d.cpap) {
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
      return { label: '血圧', status: 'updated' };
    }
    return { label: '血圧', status: 'unchanged' };
  } catch (e) {
    return { label: '血圧', status: 'error', message: e.message };
  }
}

async function submitMeals(datesToSubmit, dateLabel) {
  try {
    const { content, sha } = await ghGet('logs/lifestyle/meals.md');
    let cur = content, changed = false;
    for (const date of datesToSubmit) {
      const d = drafts[date];
      const next = upsertMdSection(cur, date, buildMealsSection(date, {
        breakfast: d.breakfast, lunch: d.lunch, dinner: d.dinner,
        note: d.foodNote, eatingOut: d.eatingOut,
        nightSnack: d.nightSnack, snack: d.snack,
      }));
      if (next) { cur = next; changed = true; }
    }
    if (changed) {
      await ghPut('logs/lifestyle/meals.md', cur, sha, `Update 食事 for ${dateLabel}`);
      return { label: '食事', status: 'updated' };
    }
    return { label: '食事', status: 'unchanged' };
  } catch (e) {
    return { label: '食事', status: 'error', message: e.message };
  }
}

async function submitExercise(datesToSubmit, dateLabel) {
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
      return { label: '運動', status: 'updated' };
    }
    return { label: '運動', status: 'unchanged' };
  } catch (e) {
    return { label: '運動', status: 'error', message: e.message };
  }
}

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

  const dateLabel = datesToSubmit.length > 1
    ? `${datesToSubmit[0]} 他${datesToSubmit.length - 1}日`
    : datesToSubmit[0];

  const results = await Promise.all([
    submitWeight(datesToSubmit, dateLabel),
    submitBP(datesToSubmit, dateLabel),
    submitMeals(datesToSubmit, dateLabel),
    submitExercise(datesToSubmit, dateLabel),
  ]);

  const updated = [], unchanged = [], errors = [];
  for (const r of results) {
    if (r.status === 'updated') updated.push(r.label);
    else if (r.status === 'unchanged') unchanged.push(r.label);
    else errors.push(`${r.label}: ${r.message}`);
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
  persistDrafts();
  chartRawData = null;
  ['am-bp1','am-bp2','pm-bp1','pm-bp2','weight','bodyfat',
   'eating-out','breakfast','lunch','dinner','food-note','exercise'].forEach(id => {
    $(id).value = '';
  });
  setRadio('cpap', '');
  setRadio('night-snack', '');
  setRadio('snack', '');
  currentDate = todayLocal();
  $('date').value = currentDate;
  loadForDate(currentDate);
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

// ── Charts ────────────────────────────────────────────────────────────────────
let weightChart = null;
let bpChart = null;
let chartRawData = null;
let chartPeriodDays = 14;

function rolling7(arr) {
  return arr.map((_, i) => {
    const slice = arr.slice(Math.max(0, i - 6), i + 1).filter(v => v != null);
    return slice.length ? slice.reduce((a, b) => a + b, 0) / slice.length : null;
  });
}

function filterDays(entries, days) {
  if (!days) return entries;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days + 1);
  return entries.filter(e => new Date(e.date) >= cutoff);
}

function fmtDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function parseWeightRows(content) {
  return content.split('\n').slice(1)
    .filter(Boolean)
    .map(line => {
      const [date, weight] = line.split(',');
      return { date: date.trim(), weight: parseFloat(weight) };
    })
    .filter(r => r.date && !isNaN(r.weight))
    .sort((a, b) => a.date.localeCompare(b.date));
}

function parseBPRows(content) {
  return content.split('\n').slice(1)
    .filter(Boolean)
    .map(line => {
      const parts = line.split(',');
      const [date, time, s1, d1, , s2, d2] = parts;
      const sys = (parseFloat(s1) + parseFloat(s2)) / 2;
      const dia = (parseFloat(d1) + parseFloat(d2)) / 2;
      return { date: date.trim(), time: time.trim(), sys, dia };
    })
    .filter(r => r.date && !isNaN(r.sys))
    .sort((a, b) => a.date.localeCompare(b.date));
}

function drawWeightChart(rows, days) {
  const filtered = filterDays(rows, days);
  const labels  = filtered.map(r => fmtDate(r.date));
  const weights = filtered.map(r => r.weight);
  const avg     = rolling7(weights);

  const ctx = $('weight-canvas').getContext('2d');
  if (weightChart) weightChart.destroy();

  weightChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '体重',
          data: weights,
          borderColor: 'rgba(0,122,255,0.45)',
          borderWidth: 1.5,
          pointRadius: 3,
          pointBackgroundColor: 'rgba(0,122,255,0.7)',
          tension: 0.3,
          fill: false,
        },
        {
          label: '7日平均',
          data: avg,
          borderColor: 'rgba(0,60,180,1)',
          borderWidth: 2.5,
          pointRadius: 0,
          tension: 0.4,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { boxWidth: 12, font: { size: 12 }, padding: 10 } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} kg`,
          },
        },
      },
      scales: {
        x: { ticks: { font: { size: 11 }, maxTicksLimit: 8 } },
        y: {
          ticks: { font: { size: 11 }, callback: v => v.toFixed(1) },
          title: { display: true, text: 'kg', font: { size: 11 } },
        },
      },
    },
  });
}

function drawBPChart(rows, days) {
  const morning  = rows.filter(r => r.time === 'morning');
  const filtered = filterDays(morning, days);
  const labels   = filtered.map(r => fmtDate(r.date));
  const sys      = filtered.map(r => r.sys);
  const dia      = filtered.map(r => r.dia);
  const sysAvg   = rolling7(sys);
  const diaAvg   = rolling7(dia);

  const ctx = $('bp-canvas').getContext('2d');
  if (bpChart) bpChart.destroy();

  const refLine = (label, val, color) => ({
    label, _ref: true,
    data: Array(labels.length).fill(val),
    borderColor: color,
    borderWidth: 1,
    borderDash: [4, 4],
    pointRadius: 0,
    fill: false,
  });

  bpChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '収縮期',
          data: sys,
          borderColor: 'rgba(255,59,48,0.4)',
          borderWidth: 1.5,
          pointRadius: 3,
          pointBackgroundColor: 'rgba(255,59,48,0.65)',
          tension: 0.3,
          fill: false,
        },
        {
          label: '収縮期 7日平均',
          data: sysAvg,
          borderColor: 'rgba(190,20,10,1)',
          borderWidth: 2.5,
          pointRadius: 0,
          tension: 0.4,
          fill: false,
        },
        {
          label: '拡張期',
          data: dia,
          borderColor: 'rgba(255,149,0,0.4)',
          borderWidth: 1.5,
          pointRadius: 3,
          pointBackgroundColor: 'rgba(255,149,0,0.65)',
          tension: 0.3,
          fill: false,
        },
        {
          label: '拡張期 7日平均',
          data: diaAvg,
          borderColor: 'rgba(180,80,0,1)',
          borderWidth: 2.5,
          pointRadius: 0,
          tension: 0.4,
          fill: false,
        },
        refLine('140', 140, 'rgba(255,59,48,0.55)'),
        refLine('130', 130, 'rgba(255,149,0,0.55)'),
        refLine('90',   90, 'rgba(255,59,48,0.3)'),
        refLine('85',   85, 'rgba(255,149,0,0.3)'),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: {
            boxWidth: 12,
            font: { size: 11 },
            padding: 8,
            filter: (item, data) => !data.datasets[item.datasetIndex]._ref,
          },
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              if (ctx.dataset._ref) return null;
              return `${ctx.dataset.label}: ${Math.round(ctx.parsed.y)} mmHg`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { font: { size: 11 }, maxTicksLimit: 8 } },
        y: {
          min: 60,
          max: 170,
          ticks: { font: { size: 11 } },
          title: { display: true, text: 'mmHg', font: { size: 11 } },
        },
      },
    },
  });
}

async function loadAndRenderCharts(forceRefresh = false) {
  const loadEl = $('chart-loading');

  if (forceRefresh) chartRawData = null;

  if (!cfg.token) {
    loadEl.textContent = '⚙️ 設定からGitHub Tokenを入力してください';
    loadEl.classList.remove('hidden');
    return;
  }

  if (!chartRawData) {
    loadEl.textContent = '読み込み中...';
    loadEl.classList.remove('hidden');
    try {
      const [wFile, bpFile] = await Promise.all([
        ghGet('logs/daily/weight.csv'),
        ghGet('logs/daily/blood_pressure.csv'),
      ]);
      chartRawData = {
        weight: parseWeightRows(wFile.content),
        bp:     parseBPRows(bpFile.content),
      };
    } catch (e) {
      loadEl.textContent = `読み込みエラー: ${e.message}`;
      return;
    }
    loadEl.classList.add('hidden');
  }

  drawWeightChart(chartRawData.weight, chartPeriodDays);
  drawBPChart(chartRawData.bp, chartPeriodDays);
}

// ── Tab switching ─────────────────────────────────────────────────────────────
function switchTab(tab) {
  const inputView = $('input-view');
  const chartView = $('chart-view');
  const tabInput  = $('tab-input');
  const tabChart  = $('tab-chart');

  if (tab === 'chart') {
    inputView.classList.add('hidden');
    chartView.classList.remove('hidden');
    tabInput.classList.remove('tab-active');
    tabChart.classList.add('tab-active');
    loadAndRenderCharts();
  } else {
    chartView.classList.add('hidden');
    inputView.classList.remove('hidden');
    tabChart.classList.remove('tab-active');
    tabInput.classList.add('tab-active');
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  restoreDrafts();
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

  $('tab-input').addEventListener('click', () => switchTab('input'));
  $('tab-chart').addEventListener('click', () => switchTab('chart'));

  document.querySelectorAll('.period-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('period-active'));
      btn.classList.add('period-active');
      chartPeriodDays = parseInt(btn.dataset.days) || 0;
      if (chartRawData) {
        drawWeightChart(chartRawData.weight, chartPeriodDays);
        drawBPChart(chartRawData.bp, chartPeriodDays);
      }
    });
  });

  $('chart-refresh-btn').addEventListener('click', () => loadAndRenderCharts(true));

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
