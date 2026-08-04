(() => {
  const OWNER = 'baker1129';
  const REPO = 'health-project';
  const BRANCH = 'main';
  const WEIGHT_CSV_URL = `https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH}/logs/daily/weight.csv`;

  const HEIGHT_CM = 168; // docs/goal.md, docs/baseline.md の実測値

  // Mirrors scripts/goals.py's GOALS list (the single source of truth for
  // phase thresholds). Keep these two lists in sync if the plan changes.
  const GOALS = [
    { kg: 88.9, name: '第1目標' },
    { kg: 82.9, name: '第2目標' },
    { kg: 79.9, name: '第3目標' },
    { kg: 69.9, name: '第4目標' },
    { kg: 62.1, name: '最終目標' },
  ];

  const $ = id => document.getElementById(id);
  const isNum = v => typeof v === 'number' && !isNaN(v);

  function setStatus(text, isError) {
    const el = $('statusline');
    el.textContent = text;
    el.classList.toggle('error', !!isError);
  }

  // ── Data loading ────────────────────────────────────────────────────────
  // bodyfat is an optional column (docs/data_spec.md) — a blank cell parses
  // to NaN and is treated as "no reading" throughout, never as 0.
  function parseWeightCSV(text) {
    return text.trim().split('\n').slice(1) // drop the header row
      .filter(Boolean)
      .map(line => {
        const [date, w, bf] = line.split(',');
        return { date: (date || '').trim(), w: parseFloat(w), bf: parseFloat(bf) };
      })
      .filter(r => r.date && isNum(r.w))
      .sort((a, b) => a.date.localeCompare(b.date));
  }

  async function loadWeightRows() {
    const res = await fetch(WEIGHT_CSV_URL, { cache: 'no-store' });
    if (!res.ok) throw new Error(`weight.csv の取得に失敗 (HTTP ${res.status})`);
    const rows = parseWeightCSV(await res.text());
    if (rows.length === 0) throw new Error('weight.csv にデータがありません');
    return rows;
  }

  loadWeightRows()
    .then(init)
    .catch(err => {
      console.error(err);
      setStatus(`データの取得に失敗しました（${err.message}）。しばらくしてから再読み込みしてください。`, true);
    });

  // ── Shared helpers ──────────────────────────────────────────────────────
  // Trailing 7-value average over whichever entries in the window are valid.
  // Carries the last valid average forward through a run of missing values
  // (relevant to bodyfat only — weight is always present) instead of
  // producing a hole that would misalign the raw/average series pair.
  function rolling7(rows, key) {
    let lastValid = null;
    return rows.map((_, i) => {
      const slice = rows.slice(Math.max(0, i - 6), i + 1).map(r => r[key]).filter(isNum);
      if (slice.length) lastValid = slice.reduce((a, b) => a + b, 0) / slice.length;
      return lastValid;
    });
  }

  function fmtDate(d) {
    const [, m, day] = d.split('-');
    return `${parseInt(m, 10)}/${parseInt(day, 10)}`;
  }

  function renderSparkline(el, rows, key, w, h) {
    const W = w, H = h, padY = 4;
    const vals = rows.map(r => r[key]);
    const min = Math.min(...vals), max = Math.max(...vals);
    const range = (max - min) || 1;
    const x = i => (rows.length <= 1) ? W / 2 : (W * i) / (rows.length - 1);
    const y = v => padY + (H - 2 * padY) - ((v - min) / range) * (H - 2 * padY);
    const pts = rows.map((r, i) => `${x(i)},${y(r[key])}`).join(' ');
    const last = rows[rows.length - 1];
    el.innerHTML = `
      <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" preserveAspectRatio="none" role="img" aria-label="直近30日の推移スパークライン">
        <polygon points="0,${H} ${pts} ${W},${H}" fill="var(--accent)" opacity="0.14"/>
        <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
        <circle cx="${x(rows.length - 1)}" cy="${y(last[key])}" r="3.5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2"/>
      </svg>`;
  }

  // ── Generic line chart renderer ─────────────────────────────────────────
  // Series data points may have y:null (no reading that day, e.g. optional
  // bodyfat) — those render as a gap: no dot, no line/area segment across
  // them — rather than being dropped, which would misalign the raw/average
  // series and the shared date axis.
  function renderChart(svgEl, tooltipEl, boxEl, series, opts) {
    const W = 1000, H = 360, padL = 54, padR = 14, padT = 16, padB = 34;
    const plotW = W - padL - padR, plotH = H - padT - padB;

    const allVals = series.flatMap(s => s.data.map(d => d.y)).filter(isNum);
    let yMin = Math.min(...allVals, ...(opts.refLines || []).map(r => r.y));
    let yMax = Math.max(...allVals, ...(opts.refLines || []).map(r => r.y));
    const pad = (yMax - yMin) * 0.14 || 1;
    yMin -= pad; yMax += pad;

    const n = series[0].data.length;
    const x = i => padL + (n <= 1 ? plotW / 2 : (plotW * i) / (n - 1));
    const y = v => padT + plotH - ((v - yMin) / (yMax - yMin)) * plotH;

    function buildPath(data) {
      const segments = [];
      let current = [];
      data.forEach((d, i) => {
        if (isNum(d.y)) {
          current.push(`${x(i)},${y(d.y)}`);
        } else if (current.length) {
          segments.push(current);
          current = [];
        }
      });
      if (current.length) segments.push(current);
      return segments.map(seg => 'M ' + seg.join(' L ')).join(' ');
    }

    let svg = '';

    const steps = 4;
    for (let s = 0; s <= steps; s++) {
      const v = yMin + ((yMax - yMin) * s) / steps;
      const yy = y(v);
      svg += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="var(--grid)" stroke-width="1"/>`;
      svg += `<text x="${padL - 10}" y="${yy + 4}" text-anchor="end" font-size="12" fill="var(--ink-muted)" class="mono">${v.toFixed(opts.yDecimals ?? 0)}</text>`;
    }

    (opts.refLines || []).forEach(r => {
      const yy = y(r.y);
      svg += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="${r.color}" stroke-width="1.4" stroke-dasharray="4,5" opacity="0.6"/>`;
      svg += `<text x="${W - padR}" y="${yy - 5}" text-anchor="end" font-size="11.5" fill="${r.color}" opacity="0.9">${r.label}</text>`;
    });

    const labelEvery = Math.max(1, Math.ceil(n / 8));
    for (let i = 0; i < n; i += labelEvery) {
      svg += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" font-size="12" fill="var(--ink-muted)" class="mono">${fmtDate(series[0].data[i].date)}</text>`;
    }

    const emphasis = series.find(s => s.area);
    if (emphasis) {
      const areaPts = emphasis.data.map((d, i) => (isNum(d.y) ? `${x(i)},${y(d.y)}` : null)).filter(Boolean).join(' L ');
      if (areaPts) {
        svg += `<path d="M ${padL},${padT + plotH} L ${areaPts} L ${x(n - 1)},${padT + plotH} Z" fill="${emphasis.color}" opacity="0.08"/>`;
      }
    }

    series.forEach(s => {
      svg += `<path d="${buildPath(s.data)}" fill="none" stroke="${s.color}" stroke-width="${s.width}" stroke-linejoin="round" stroke-linecap="round" opacity="${s.opacity ?? 1}"/>`;
      if (s.dots) {
        s.data.forEach((d, i) => {
          if (!isNum(d.y)) return;
          svg += `<circle cx="${x(i)}" cy="${y(d.y)}" r="3.6" fill="${s.color}" stroke="var(--chart-surface)" stroke-width="2" opacity="${s.opacity ?? 1}"/>`;
        });
      }
    });

    svg += `<line id="${svgEl.id}-crosshair" x1="0" y1="${padT}" x2="0" y2="${padT + plotH}" stroke="var(--ink-muted)" stroke-width="1" opacity="0" />`;
    svg += `<rect x="${padL}" y="${padT}" width="${plotW}" height="${plotH}" fill="transparent" id="${svgEl.id}-hit" style="cursor:crosshair" />`;

    svgEl.innerHTML = svg;

    const crosshair = svgEl.querySelector(`#${svgEl.id}-crosshair`);
    const hit = svgEl.querySelector(`#${svgEl.id}-hit`);

    function showTooltip(evt) {
      const rect = svgEl.getBoundingClientRect();
      const px = (evt.clientX - rect.left) / rect.width * W;
      let idx = Math.round(((px - padL) / plotW) * (n - 1));
      idx = Math.max(0, Math.min(n - 1, idx));
      const xx = x(idx);
      crosshair.setAttribute('x1', xx);
      crosshair.setAttribute('x2', xx);
      crosshair.setAttribute('opacity', '1');

      const boxRect = boxEl.getBoundingClientRect();
      const svgRect = svgEl.getBoundingClientRect();
      const leftPx = svgRect.left - boxRect.left + (xx / W) * svgRect.width;
      const anchorY = isNum(series[0].data[idx].y) ? y(series[0].data[idx].y) : padT;
      const topPx = svgRect.top - boxRect.top + (anchorY / H) * svgRect.height;

      let html = `<div class="t-date">${series[0].data[idx].date}</div>`;
      series.forEach(s => {
        const v = s.data[idx].y;
        const valText = isNum(v) ? `${v.toFixed(opts.yDecimals ?? 0)}${opts.unit || ''}` : '—';
        html += `<div class="t-row"><span class="t-key" style="background:${s.color}"></span>${s.name}<span class="t-val mono">${valText}</span></div>`;
      });
      tooltipEl.innerHTML = html;
      tooltipEl.style.left = leftPx + 'px';
      tooltipEl.style.top = (topPx - 10) + 'px';
      tooltipEl.classList.add('show');
    }

    function hideTooltip() {
      crosshair.setAttribute('opacity', '0');
      tooltipEl.classList.remove('show');
    }

    hit.addEventListener('pointermove', showTooltip);
    hit.addEventListener('pointerleave', hideTooltip);
    hit.addEventListener('pointerdown', showTooltip);
  }

  // ── Day-grid table (one month at a time) ────────────────────────────────
  function renderDayTable(weightRows) {
    const months = [...new Set(weightRows.map(r => r.date.slice(0, 7)))];
    let monthIndex = months.length - 1; // start at the latest month

    const table = $('day-table');
    const label = $('month-label');
    const prevBtn = $('month-prev');
    const nextBtn = $('month-next');

    function draw() {
      const key = months[monthIndex];
      const [y, m] = key.split('-').map(Number);
      const daysInMonth = new Date(y, m, 0).getDate();
      const byDay = new Map(
        weightRows.filter(r => r.date.startsWith(key)).map(r => [parseInt(r.date.slice(8, 10), 10), r])
      );

      let colgroup = '<colgroup><col style="width:84px">';
      for (let d = 1; d <= daysInMonth; d++) colgroup += '<col>';
      colgroup += '</colgroup>';

      let thead = '<tr><th>日</th>';
      for (let d = 1; d <= daysInMonth; d++) thead += `<th>${d}</th>`;
      thead += '</tr>';

      let wRow = '<tr><th scope="row">体重(kg)</th>';
      let bfRow = '<tr><th scope="row">体脂肪率(%)</th>';
      for (let d = 1; d <= daysInMonth; d++) {
        const r = byDay.get(d);
        wRow += r ? `<td>${r.w.toFixed(1)}</td>` : '<td class="empty">—</td>';
        bfRow += (r && isNum(r.bf)) ? `<td>${r.bf.toFixed(1)}</td>` : '<td class="empty">—</td>';
      }
      wRow += '</tr>';
      bfRow += '</tr>';

      table.innerHTML = `${colgroup}<thead>${thead}</thead><tbody>${wRow}${bfRow}</tbody>`;
      label.textContent = `${y}年${m}月`;
      prevBtn.disabled = monthIndex === 0;
      nextBtn.disabled = monthIndex === months.length - 1;
    }

    prevBtn.addEventListener('click', () => { if (monthIndex > 0) { monthIndex--; draw(); } });
    nextBtn.addEventListener('click', () => { if (monthIndex < months.length - 1) { monthIndex++; draw(); } });

    draw();
  }

  // ── Monthly summary table (year-navigable) ──────────────────────────────
  function renderMonthlyTable(weightRows) {
    const avg = arr => arr.reduce((a, b) => a + b, 0) / arr.length;

    const allMonths = [...new Set(weightRows.map(r => r.date.slice(0, 7)))];
    const byMonth = new Map(allMonths.map(key => [key, weightRows.filter(r => r.date.startsWith(key))]));
    const monthEndWeight = key => {
      const entries = byMonth.get(key);
      return entries[entries.length - 1].w;
    };

    const years = [...new Set(allMonths.map(key => key.slice(0, 4)))];
    let yearIndex = years.length - 1;

    const tbody = $('month-table-body');
    const yearLabel = $('year-label');
    const yearPrev = $('year-prev');
    const yearNext = $('year-next');

    function draw() {
      const year = years[yearIndex];
      const monthsThisYear = allMonths.filter(key => key.startsWith(year));
      tbody.innerHTML = '';

      monthsThisYear.forEach(key => {
        const entries = byMonth.get(key);
        const idxInAll = allMonths.indexOf(key);
        const prevKey = idxInAll > 0 ? allMonths[idxInAll - 1] : null;
        const wAvg = avg(entries.map(e => e.w));
        const wEnd = entries[entries.length - 1].w;
        const bfVals = entries.map(e => e.bf).filter(isNum);
        const bfAvgM = bfVals.length ? avg(bfVals) : null;
        const bfEnd = entries[entries.length - 1].bf;
        const delta = prevKey ? wEnd - monthEndWeight(prevKey) : null;

        const tr = document.createElement('tr');
        const deltaHtml = delta == null
          ? '<span class="delta muted">—</span>'
          : `<span class="delta ${delta <= 0 ? 'good' : ''}">${delta > 0 ? '+' : ''}${delta.toFixed(1)}<span class="unit">kg</span></span>`;

        tr.innerHTML = `
          <td>${parseInt(key.slice(5, 7), 10)}月</td>
          <td>${entries.length}<span class="unit">日</span></td>
          <td>${wAvg.toFixed(1)}<span class="unit">kg</span></td>
          <td>${wEnd.toFixed(1)}<span class="unit">kg</span></td>
          <td>${deltaHtml}</td>
          <td>${bfAvgM != null ? bfAvgM.toFixed(1) + '<span class="unit">%</span>' : '—'}</td>
          <td>${isNum(bfEnd) ? bfEnd.toFixed(1) + '<span class="unit">%</span>' : '—'}</td>
        `;
        tbody.appendChild(tr);
      });

      yearLabel.textContent = `${year}年`;
      yearPrev.disabled = yearIndex === 0;
      yearNext.disabled = yearIndex === years.length - 1;
    }

    yearPrev.addEventListener('click', () => { if (yearIndex > 0) { yearIndex--; draw(); } });
    yearNext.addEventListener('click', () => { if (yearIndex < years.length - 1) { yearIndex++; draw(); } });

    draw();
  }

  function wireMonthlySummaryToggle() {
    const toggle = $('month-summary-toggle');
    const body = $('month-summary-body');
    toggle.addEventListener('click', () => {
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!expanded));
      body.hidden = expanded;
    });
  }

  // First not-yet-achieved goal (weight still above its threshold), or -1
  // once every goal has been reached.
  function nextGoalIndex(CURRENT) {
    return GOALS.findIndex(g => CURRENT > g.kg);
  }

  // ── Phase / journey progress card ───────────────────────────────────────
  function renderPhaseCard(weightRows, CURRENT) {
    const START = weightRows[0].w;
    const FINAL = GOALS[GOALS.length - 1].kg;

    const nextIdx = nextGoalIndex(CURRENT);
    const allAchieved = nextIdx === -1;
    const nextGoal = allAchieved ? null : GOALS[nextIdx];
    const lastAchieved = allAchieved ? GOALS[GOALS.length - 1] : (nextIdx > 0 ? GOALS[nextIdx - 1] : null);

    if (allAchieved) {
      $('phase-title').textContent = `${GOALS[GOALS.length - 1].name} 達成 🎉`;
      $('phase-note').innerHTML = `7日平均 ${CURRENT.toFixed(1)}kg`;
      $('phase-next-label').textContent = '';
      $('phase-next-value').textContent = '';
    } else {
      $('phase-title').innerHTML = `${nextGoal.name} <span class="muted">— ${nextGoal.kg}kg以下</span>`;
      const achievedNote = lastAchieved ? `${lastAchieved.name} 達成 <span class="good">✓</span>　` : '';
      $('phase-note').innerHTML = `${achievedNote}7日平均 ${CURRENT.toFixed(1)}kg`;
      $('phase-next-label').textContent = `${nextGoal.name}まで`;
      $('phase-next-value').innerHTML = `${(CURRENT - nextGoal.kg).toFixed(1)}<span class="unit">kg</span>`;
    }

    const posOf = kg => ((START - kg) / (START - FINAL)) * 100;
    const track = $('meter-track');
    const fillEl = $('meter-fill');
    track.querySelectorAll('.meter-dot').forEach(d => d.remove());
    fillEl.style.width = Math.max(0, Math.min(100, posOf(CURRENT))) + '%';

    const caption = $('milestone-caption');
    caption.innerHTML = '';
    let nextAssigned = false;
    GOALS.forEach((m, i) => {
      const p = Math.max(0, Math.min(100, posOf(m.kg)));
      const achieved = CURRENT <= m.kg;
      const isNext = !achieved && !nextAssigned;
      if (isNext) nextAssigned = true;
      const state = achieved ? 'done' : (isNext ? 'next' : '');

      const dot = document.createElement('div');
      dot.className = 'meter-dot' + (state ? ' ' + state : '');
      dot.style.left = p + '%';
      dot.title = `${m.name} ${m.kg}kg${achieved ? '・達成' : ''}`;
      track.appendChild(dot);

      if (i > 0) {
        const arrow = document.createElement('span');
        arrow.className = 'ms-arrow';
        arrow.textContent = '→';
        caption.appendChild(arrow);
      }
      const span = document.createElement('span');
      span.className = 'ms' + (state ? ' ' + state : '');
      span.textContent = (achieved ? '✓ ' : '') + m.kg;
      caption.appendChild(span);
    });
  }

  // ── Single big chart, toggled between weight and body fat ──────────────
  function wireMainChart(weightRows, weightAvg, bfAvg, CURRENT) {
    // Reference lines track whichever two goals are actually next, so they
    // keep advancing (第3目標→第4目標→…) as the weight trend clears each one,
    // rather than staying pinned to a fixed pair.
    const nextIdx = nextGoalIndex(CURRENT);
    const upcomingGoals = nextIdx === -1 ? [] : GOALS.slice(nextIdx, nextIdx + 2);

    const metricInfo = {
      w: {
        title: '体重推移', unit: 'kg', yDecimals: 1, seriesName: '体重',
        color: 'var(--series-weight)', avgColor: 'var(--series-weight-avg)',
        refLines: upcomingGoals.map((g, i) => ({
          y: g.kg, label: `${g.name} ${g.kg}kg`, color: i === 0 ? 'var(--accent)' : 'var(--ink-muted)',
        })),
      },
      bf: {
        title: '体脂肪率推移', unit: '%', yDecimals: 1, seriesName: '体脂肪率',
        color: 'var(--series-bf)', avgColor: 'var(--series-bf-avg)',
        refLines: [],
      },
    };
    let currentMetric = 'w';
    let periodDays = 0; // 0 = all

    function sliceByPeriod(rows) {
      return periodDays ? rows.slice(-periodDays) : rows;
    }

    function drawMain() {
      const info = metricInfo[currentMetric];
      const avgArr = currentMetric === 'w' ? weightAvg : bfAvg;
      const rows = sliceByPeriod(weightRows.map(r => ({ date: r.date, y: isNum(r[currentMetric]) ? r[currentMetric] : null })));
      const avgRows = sliceByPeriod(weightRows.map((r, i) => ({ date: r.date, y: avgArr[i] })));

      $('chart-title').textContent = info.title;
      $('chart-legend').innerHTML = `
        <span class="legend-item"><span class="legend-swatch" style="background:${info.color}"></span>${info.seriesName}</span>
        <span class="legend-item"><span class="legend-swatch thick" style="background:${info.avgColor}"></span>7日平均</span>
      `;

      renderChart(
        $('main-svg'), $('main-tooltip'), $('main-chart-box'),
        [
          { name: info.seriesName, data: rows, color: info.color, width: 2, opacity: 0.5, dots: true },
          { name: '7日平均', data: avgRows, color: info.avgColor, width: 3.2, area: true },
        ],
        { yDecimals: info.yDecimals, unit: info.unit, refLines: info.refLines }
      );
    }

    document.querySelectorAll('.metric-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.metric-btn').forEach(b => b.setAttribute('aria-pressed', 'false'));
        btn.setAttribute('aria-pressed', 'true');
        currentMetric = btn.dataset.metric;
        drawMain();
      });
    });

    document.querySelectorAll('.period-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.period-btn').forEach(b => b.setAttribute('aria-pressed', 'false'));
        btn.setAttribute('aria-pressed', 'true');
        periodDays = parseInt(btn.dataset.days, 10) || 0;
        drawMain();
      });
    });

    drawMain();
  }

  // ── Init ─────────────────────────────────────────────────────────────────
  function init(weightRows) {
    const weightAvg = rolling7(weightRows, 'w');
    const bfAvg = rolling7(weightRows, 'bf');

    const first = weightRows[0];
    const latest = weightRows[weightRows.length - 1];
    const latestAvgW = weightAvg[weightAvg.length - 1];
    const latestAvgBf = bfAvg[bfAvg.length - 1];

    setStatus(`最終記録: ${latest.date} ・ データはGitHubから直接取得`, false);

    const startDate = new Date(first.date + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const daysSinceStart = Math.round((today - startDate) / 86400000) + 1;
    $('since-line').innerHTML = `<b>${first.date}</b> 開始 ・ <b>${daysSinceStart}</b>日目`;

    $('hero-value').textContent = latest.w.toFixed(1);
    const wDelta = latest.w - first.w;
    const wDeltaHtml = wDelta <= 0 ? `<span class="good">${wDelta.toFixed(1)}kg</span>` : `+${wDelta.toFixed(1)}kg`;
    $('hero-delta').innerHTML = `開始比 ${wDeltaHtml}　7日平均 ${latestAvgW.toFixed(1)}kg`;

    if (isNum(latest.bf)) {
      $('side-value').textContent = latest.bf.toFixed(1);
      const bfAvgText = isNum(latestAvgBf) ? `${latestAvgBf.toFixed(1)}%` : '—';
      if (isNum(first.bf)) {
        const bfDelta = latest.bf - first.bf;
        const bfDeltaHtml = bfDelta <= 0 ? `<span class="good">${bfDelta.toFixed(1)}pt</span>` : `+${bfDelta.toFixed(1)}pt`;
        $('side-delta').innerHTML = `開始比 ${bfDeltaHtml}　7日平均 ${bfAvgText}`;
      } else {
        $('side-delta').textContent = `7日平均 ${bfAvgText}`;
      }
      const bfRecent = weightRows.slice(-30).filter(r => isNum(r.bf));
      if (bfRecent.length >= 2) renderSparkline($('bf-spark'), bfRecent, 'bf', 96, 30);
    } else {
      $('side-value').textContent = '—';
      $('side-delta').textContent = '記録なし';
    }

    const bmi = latest.w / ((HEIGHT_CM / 100) ** 2);
    const bmiStart = first.w / ((HEIGHT_CM / 100) ** 2);
    $('stat-weight-avg').innerHTML = `${latestAvgW.toFixed(1)}<span class="unit">kg</span>`;
    $('stat-bmi').textContent = bmi.toFixed(1);
    $('stat-bmi-start').textContent = bmiStart.toFixed(1);

    renderSparkline($('hero-spark'), weightRows.slice(-30), 'w', 128, 46);

    renderPhaseCard(weightRows, latestAvgW);
    renderDayTable(weightRows);
    renderMonthlyTable(weightRows);
    wireMonthlySummaryToggle();
    wireMainChart(weightRows, weightAvg, bfAvg, latestAvgW);
  }
})();
