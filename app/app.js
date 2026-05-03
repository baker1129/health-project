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

// ── File formatters ───────────────────────────────────────────────────────────

function appendWeight(src, date, weight, bodyfat) {
  if (!weight) return null;
  if (src.split('\n').some(l => l.startsWith(date + ','))) return null;
  return src.trimEnd() + '\n' + `${date},${weight},${bodyfat || ''}` + '\n';
}

function parseBP(text) {
  if (!text || !text.trim()) return null;
  const p = text.trim().split('/').map(s => Number(s.trim()));
  if (p.length !== 3 || p.some(isNaN)) return null;
  return p;
}

function appendBP(src, date, time, bp1text, bp2text, memo) {
  const bp1 = parseBP(bp1text);
  if (!bp1) return null;
  if (src.split('\n').some(l => l.startsWith(`${date},${time},`))) return null;
  const bp2 = parseBP(bp2text) || bp1;
  const row = [date, time, ...bp1, ...bp2, memo || ''].join(',');
  return src.trimEnd() + '\n' + row + '\n';
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

function appendMeals(src, date, { breakfast, lunch, dinner, note }) {
  if (src.includes(`## ${date}`)) return null;
  if (!breakfast && !lunch && !dinner && !note) return null;
  let s = `\n## ${date}\n`;
  if (breakfast) s += `\n### 朝\n${toList(breakfast)}`;
  if (lunch)     s += `\n### 昼\n${toList(lunch)}`;
  if (dinner)    s += `\n### 夜\n${toList(dinner)}`;
  if (note)      s += `\n### 気づき\n- ${note.trim()}\n`;
  return src.trimEnd() + '\n' + s;
}

function appendExercise(src, date, exercise) {
  if (!exercise || !exercise.trim()) return null;
  if (src.includes(`## ${date}`)) return null;
  return src.trimEnd() + '\n\n---\n\n' + `## ${date}\n- ${exercise.trim()}\n`;
}

// ── Submit ────────────────────────────────────────────────────────────────────
async function submit() {
  if (!cfg.token) {
    showMsg('⚙️ 設定から GitHub Token を入力してください', 'error');
    openSettings();
    return;
  }

  const date = $('date').value;
  if (!date) { showMsg('日付を入力してください', 'error'); return; }

  setLoading(true);
  showMsg('送信中...', 'info');

  const done = [], skipped = [], errors = [];

  // Generic file updater
  async function run(label, filePath, patcher) {
    try {
      const { content, sha } = await ghGet(filePath);
      const next = patcher(content);
      if (next === null) { skipped.push(label); return; }
      await ghPut(filePath, next, sha, `Add ${label} for ${date}`);
      done.push(label);
    } catch (e) {
      errors.push(`${label}: ${e.message}`);
    }
  }

  // Weight
  await run('体重', 'logs/daily/weight.csv', c =>
    appendWeight(c, date, $('weight').value, $('bodyfat').value));

  // Blood pressure (read once → apply both → write once, to avoid SHA conflict)
  const amBp1 = $('am-bp1').value;
  const amBp2 = $('am-bp2').value;
  const pmBp1 = $('pm-bp1').value;
  const pmBp2 = $('pm-bp2').value;
  const cpap  = document.querySelector('input[name="cpap"]:checked')?.value || '';
  const hasMorning = !!parseBP(amBp1);
  const hasNight   = !!parseBP(pmBp1);

  if (hasMorning || hasNight) {
    try {
      const { content, sha } = await ghGet('logs/daily/blood_pressure.csv');
      let cur = content;
      const bpDone = [], bpSkip = [];

      if (hasMorning) {
        const next = appendBP(cur, date, 'morning', amBp1, amBp2, cpap ? `cpap:${cpap}` : '');
        if (next) { cur = next; bpDone.push('朝'); }
        else bpSkip.push('朝');
      }
      if (hasNight) {
        const next = appendBP(cur, date, 'night', pmBp1, pmBp2, '');
        if (next) { cur = next; bpDone.push('夜'); }
        else bpSkip.push('夜');
      }

      if (cur !== content) {
        await ghPut('logs/daily/blood_pressure.csv', cur, sha, `Add BP for ${date}`);
        done.push(`血圧(${bpDone.join('・')})`);
      } else {
        skipped.push(`血圧(${bpSkip.join('・')})`);
      }
    } catch (e) {
      errors.push(`血圧: ${e.message}`);
    }
  }

  // Meals
  await run('食事', 'logs/lifestyle/meals.md', c =>
    appendMeals(c, date, {
      breakfast: $('breakfast').value,
      lunch:     $('lunch').value,
      dinner:    $('dinner').value,
      note:      $('food-note').value,
    }));

  // Exercise
  await run('運動', 'logs/lifestyle/exercise.md', c =>
    appendExercise(c, date, $('exercise').value));

  setLoading(false);

  if (errors.length > 0) {
    showMsg('❌ エラー:\n' + errors.join('\n'), 'error');
  } else {
    const parts = [];
    if (done.length)    parts.push('✅ 記録: '           + done.join('・'));
    if (skipped.length) parts.push('⏭ スキップ（既存）: ' + skipped.join('・'));
    showMsg(parts.join('\n') || '変更なし', 'success');
    clearForm();
  }
}

function clearForm() {
  ['am-bp1','am-bp2','pm-bp1','pm-bp2','weight','bodyfat',
   'breakfast','lunch','dinner','food-note','exercise'].forEach(id => {
    $(id).value = '';
  });
  document.querySelector('input[name="cpap"][value=""]').checked = true;
  $('date').value = todayLocal();
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
  $('date').value = todayLocal();

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

  if (!cfg.token) openSettings();
});
