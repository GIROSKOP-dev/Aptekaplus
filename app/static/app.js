/* АптекаПлюс — фронт. Все расчёты на бэкенде (/api/model). */
const nf = (n, d = 0) => Number(n).toLocaleString('ru-RU',
  { minimumFractionDigits: d, maximumFractionDigits: d });
const money = n => nf(Math.round(n)) + ' ₽';
const sum = a => a.reduce((x, y) => x + y, 0);

const BLOCK_LABELS = {
  expired: { label:'❌ Просрочен', cls:'b-danger' },
  recall:  { label:'🚫 Отзыв',     cls:'b-danger' },
  storage: { label:'🌡️ Хранение', cls:'b-warn' },
  box:     { label:'📦 Коробка',   cls:'b-warn' },
  expiry:  { label:'⏳ Срок ≤60%', cls:'b-danger' },
};
const SEASON_NAMES    = { winter:'Зима', spring:'Весна', summer:'Лето', autumn:'Осень' };
const SEASON_NAMES_IN = { winter:'зимой', spring:'весной', summer:'летом', autumn:'осенью' };

let CFG = {}, MODEL = [], TODAY = null;
let sortKey = null, sortDir = 'asc';
let purchaseFilter = 'all';          // all | need | season | urgent

/* ---------- загрузка ---------- */
async function load() {
  const preset = document.getElementById('periodPreset').value;
  const rangeEl = document.getElementById('customRange');
  const errBox = document.getElementById('error');

  let url = '/api/model?';
  if (preset === 'custom') {
    rangeEl.hidden = false;
    const f = document.getElementById('dateFrom').value;
    const t = document.getElementById('dateTo').value;
    if (!f || !t) return;
    url += `date_from=${f}&date_to=${t}&days=365`;
  } else {
    rangeEl.hidden = true;
    url += `days=${preset}`;
  }

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    CFG = data.config; MODEL = data.drugs; TODAY = data.today;
    document.getElementById('todayLabel').textContent = data.today;
    errBox.innerHTML = '';
    renderAll();
  } catch (e) {
    errBox.innerHTML = `<div class="error-box">Ошибка: ${e.message}</div>`;
    console.error(e);
  }
}



function renderAll() {
  const open = new Set([...document.querySelectorAll('.detail-row:not([hidden])')].map(r => r.id));
  renderKPIs(); renderDashboard(); renderStock();
  renderPriority(); renderLoss(); renderPurchase();
  open.forEach(id => {
    const det = document.getElementById(id); if (!det) return;
    det.hidden = false;
    document.querySelector(`.main-row[data-id="${id.replace('detail-','')}"]`)?.classList.add('open');
  });
}

/* ---------- KPI + клики ---------- */
function renderKPIs() {
  const totalValue  = sum(MODEL.map(d => d.stockTotal * d.priceIn));
  const totalUnits  = sum(MODEL.map(d => d.stockTotal));
  const riskValue   = sum(MODEL.map(d => d.lossMoney));
  const riskQty     = sum(MODEL.map(d => d.lossQty));
  const orderValue  = sum(MODEL.map(d => d.orderValue));
  const orderCount  = MODEL.filter(d => d.orderQty > 0).length;
  const deficitCnt  = MODEL.filter(d => d.shortage > 1).length;
  const seasonCnt   = MODEL.filter(d => d.isSeasonal && d.seasonalOrderQty > 0).length;
  const seasonValue = sum(MODEL.map(d => d.seasonalOrderValue || 0));
  const blockedCnt  = MODEL.reduce((a, d) => a + d.batches.filter(b => b.blockReason).length, 0);
  const urgentCnt   = MODEL.filter(d => d.urgency?.level === 'urgent' &&
                                         (d.orderQty > 0 || d.seasonalOrderQty > 0)).length;

  document.getElementById('kpis').innerHTML = `
    <div class="kpi clickable" data-kpi="stock">
      <div class="kpi-label">Стоимость запасов</div>
      <div class="kpi-val">${money(totalValue)}</div>
      <div class="kpi-sub">${MODEL.length} позиций · ${nf(totalUnits)} уп</div></div>

    <div class="kpi clickable danger" data-kpi="blocked">
      <div class="kpi-label">Брак (срок ≤60%)</div>
      <div class="kpi-val">${blockedCnt}</div>
      <div class="kpi-sub">партий к утилизации</div></div>

    <div class="kpi clickable danger" data-kpi="loss">
      <div class="kpi-label">Под риском списания</div>
      <div class="kpi-val">${money(riskValue)}</div>
      <div class="kpi-sub">${nf(riskQty)} уп</div></div>

    <div class="kpi clickable accent" data-kpi="orders">
      <div class="kpi-label">Рекомендовано закупить</div>
      <div class="kpi-val">${money(orderValue)}</div>
      <div class="kpi-sub">${orderCount} позиций</div></div>

    <div class="kpi clickable ${urgentCnt ? 'danger' : ''}" data-kpi="urgent">
      <div class="kpi-label">🔴 Срочных заказов</div>
      <div class="kpi-val">${urgentCnt}</div>
      <div class="kpi-sub">поставка не успевает</div></div>

    <div class="kpi clickable ${seasonCnt ? 'accent' : ''}" data-kpi="season">
      <div class="kpi-label">🌨 Сезонный заказ</div>
      <div class="kpi-val">${seasonCnt}</div>
      <div class="kpi-sub">${money(seasonValue)} к пику</div></div>

    <div class="kpi clickable ${deficitCnt ? 'danger' : ''}" data-kpi="deficit">
      <div class="kpi-label">Позиции в дефиците</div>
      <div class="kpi-val">${deficitCnt}</div>
      <div class="kpi-sub">не покроют спрос</div></div>`;

  document.querySelectorAll('.kpi.clickable').forEach(el => {
    el.onclick = () => handleKpiClick(el.dataset.kpi);
  });
}

function switchView(v) {
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  document.querySelectorAll('.view').forEach(x => x.hidden = true);
  const el = document.getElementById('view-' + v);
  if (el) el.hidden = false;
}

function handleKpiClick(kpi) {
  switch (kpi) {
    case 'stock':
      switchView('stock'); break;
    case 'blocked':
      switchView('priority'); break;
    case 'loss':
      switchView('loss'); break;
    case 'orders':
      purchaseFilter = 'all';    switchView('purchase'); renderPurchase(); break;
    case 'urgent':
      purchaseFilter = 'urgent'; switchView('purchase'); renderPurchase(); break;
    case 'season':
      purchaseFilter = 'season'; switchView('purchase'); renderPurchase(); break;
    case 'deficit':
      purchaseFilter = 'need';   switchView('purchase'); renderPurchase(); break;
  }
}

/* ---------- Дашборд ---------- */
function renderDashboard() {
  const ranges = [
    { label:'Брак (≤60%)', min:-9999, max:0,     color:'#7f1d1d', onlyBlocked:true },
    { label:'0–30 дн',     min:0,     max:30,    color:'#dc2626' },
    { label:'30–60 дн',    min:30,    max:60,    color:'#ea580c' },
    { label:'60–90 дн',    min:60,    max:90,    color:'#d97706' },
    { label:'90–180 дн',   min:90,    max:180,   color:'#ca8a04' },
    { label:'>180 дн',     min:180,   max:99999, color:'#16a34a' },
  ];
  const buckets = ranges.map(r => {
    let qty = 0;
    MODEL.forEach(d => d.batches.forEach(b => {
      if (r.onlyBlocked) { if (b.blockReason) qty += b.qty; return; }
      if (b.blockReason) return;
      if (b.daysToBlock > r.min && b.daysToBlock <= r.max) qty += b.qty;
    }));
    return { ...r, qty };
  });
  const maxQty = Math.max(...buckets.map(b => b.qty), 1);
  const barsHtml = buckets.map(b => `
    <div class="bar-row">
      <div class="bar-label">${b.label}</div>
      <div class="bar-track"><div class="bar-fill"
        style="width:${(b.qty/maxQty*100).toFixed(1)}%;background:${b.color}"></div></div>
      <div class="bar-val" style="color:${b.qty>0?b.color:'var(--muted)'}">${b.qty>0?nf(b.qty)+' уп':'—'}</div>
    </div>`).join('');

  const catMap = {};
  MODEL.forEach(d => d.batches.forEach(b => {
    if (b.blockReason || b.lost > 0.5) {
      const m = (b.blockReason ? b.qty : b.lost) * d.priceIn;
      if (m > 0.5) catMap[d.category] = (catMap[d.category] || 0) + m;
    }
  }));
  const catList = Object.entries(catMap).sort((a,b) => b[1]-a[1]);
  const totalCat = sum(catList.map(c => c[1]));
  const palette = ['#dc2626','#ea580c','#d97706','#2563eb','#7c3aed','#0891b2','#16a34a'];
  let acc = 0;
  const cx = 65, cy = 65, rO = 58, rI = 38;
  const arcs = catList.map((c,i) => {
    const frac = c[1] / totalCat;
    const a1 = acc * Math.PI * 2 - Math.PI / 2;
    const a2 = (acc + frac) * Math.PI * 2 - Math.PI / 2;
    acc += frac;
    const lg = frac > 0.5 ? 1 : 0;
    const x1o=cx+rO*Math.cos(a1), y1o=cy+rO*Math.sin(a1);
    const x2o=cx+rO*Math.cos(a2), y2o=cy+rO*Math.sin(a2);
    const x1i=cx+rI*Math.cos(a2), y1i=cy+rI*Math.sin(a2);
    const x2i=cx+rI*Math.cos(a1), y2i=cy+rI*Math.sin(a1);
    return `<path d="M ${x1o} ${y1o} A ${rO} ${rO} 0 ${lg} 1 ${x2o} ${y2o} L ${x1i} ${y1i} A ${rI} ${rI} 0 ${lg} 0 ${x2i} ${y2i} Z" fill="${palette[i%palette.length]}"/>`;
  }).join('');
  const donut = totalCat > 0
    ? `<svg viewBox="0 0 130 130" class="donut">${arcs}</svg>`
    : `<div style="width:130px;height:130px;border-radius:50%;background:#e6e9f0;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:11px;text-align:center">Нет потерь</div>`;
  const legend = catList.length
    ? catList.map((c,i) => `
      <div class="legend-item">
        <span class="legend-dot" style="background:${palette[i%palette.length]}"></span>
        <span class="legend-name">${c[0]}</span>
        <span class="legend-val">${money(c[1])}</span>
      </div>`).join('')
    : '<div class="muted" style="font-size:12px">Всё в норме 👍</div>';

  const watch = [];
  MODEL.forEach(d => d.batches.forEach(b => {
    const m = (b.blockReason ? b.qty : b.lost) * d.priceIn;
    if (m > 0.5) watch.push({ drug: d, batch: b, money: m, blocked: !!b.blockReason });
  }));
  watch.sort((a,b) => b.money - a.money);
  const watchHtml = watch.slice(0,5).map(w => `
    <div class="watch-item ${w.blocked ? '' : 'warn'}">
      <div><div class="watch-name">${w.drug.name}</div>
        <div class="watch-form">${w.batch.code} · ${w.blocked
          ? BLOCK_LABELS[w.batch.blockReason].label
          : `${w.batch.daysToBlock} дн. до порога`}</div></div>
      <div class="watch-money">${money(w.money)}</div>
    </div>`).join('') || '<div class="muted" style="font-size:12px;padding:8px 0">Проблемных партий нет 🎉</div>';

  document.getElementById('dashboard').innerHTML = `
    <div class="dash-card">
      <div class="dash-title">Партии по дням до порога 60% <span>упаковки</span></div>
      <div class="bars">${barsHtml}</div></div>
    <div class="dash-card"><div class="dash-title">Потери по категориям</div>
      <div class="donut-wrap">${donut}<div class="donut-legend">${legend}</div></div></div>
    <div class="dash-card"><div class="dash-title">🔥 Требуют внимания <span>топ-5</span></div>
      <div class="watch-list">${watchHtml}</div></div>`;
}

/* ---------- спарклайн ---------- */
function sparkline(values, color) {
  if (!values.length) return '';
  const w = 300, h = 64, pad = 4;
  const max = Math.max(...values, 1);
  const step = (w - pad*2) / Math.max(1, values.length - 1);
  const pts = values.map((v,i) =>
    `${(pad + i*step).toFixed(1)},${(h - pad - (v/max)*(h - pad*2)).toFixed(1)}`).join(' ');
  const area = `${pad},${h-pad} ${pts} ${w-pad},${h-pad}`;
  return `<svg viewBox="0 0 ${w} ${h}" class="spark" preserveAspectRatio="none">
    <polygon points="${area}" fill="${color}" opacity="0.10"/>
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.8"
      stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

/* ---------- сортировка главной ---------- */
function sortModel(model) {
  if (!sortKey) return model;
  const m = sortDir === 'asc' ? 1 : -1;
  return [...model].sort((a,b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (typeof av === 'string') return av.localeCompare(bv) * m;
    return (av - bv) * m;
  });
}
function bindSort() {
  document.querySelectorAll('th[data-sort]').forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      const k = th.dataset.sort;
      if (sortKey === k) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      else { sortKey = k; sortDir = 'asc'; }
      document.querySelectorAll('th[data-sort]').forEach(t => t.classList.remove('sort-asc','sort-desc'));
      th.classList.add(sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
      renderStock();
    });
  });
}

/* ---------- Склад ---------- */
function renderStock() {
  const model = sortModel(MODEL);
  const rows = model.map(d => {
    const st = d.status;
    const dos = d.daysOfSupply > 999 ? '>999' : nf(d.daysOfSupply);
    const lossCell = d.lossQty > 0.5
      ? `<span class="text-danger">${nf(d.lossQty)} уп</span><br><span class="muted">${money(d.lossMoney)}</span>`
      : '<span class="muted">—</span>';

    const batchRows = d.batches.map(b => {
      const blocked = b.blockReason;
      const leftTxt = blocked
        ? `<span class="text-danger">${BLOCK_LABELS[blocked].label}</span>`
        : `<b>${b.daysToBlock}</b> дн. до порога`;
      return `<tr>
        <td>${b.code}${blocked ? ` <span class="badge b-danger" style="font-size:10px">брак</span>` : ''}</td>
        <td class="num">${nf(b.qty)}</td>
        <td>${b.expiryDate}</td>
        <td class="num">${b.percentLeft.toFixed(0)}%</td>
        <td class="num">${leftTxt}</td>
        <td class="num">${b.coverage > 9000 ? '∞' : b.coverage}</td>
        <td class="num">${nf(b.sold)}</td>
        <td class="num ${b.lost > 0.5 ? 'text-danger' : ''}">${b.lost > 0.5 ? nf(b.lost) : '—'}</td>
        <td class="num ${b.lost > 0.5 ? 'text-danger' : ''}">${b.lost > 0.5 ? money(b.lost * d.priceIn) : '—'}</td>
      </tr>`;
    }).join('');

    const seasonBadge = d.isSeasonal
      ? `<div class="season-badge">🌨 пик: ${SEASON_NAMES[d.peakSeason]} ×${d.peakMult.toFixed(1)}</div>` : '';

    return `
    <tr class="main-row" data-id="${d.id}">
      <td><span class="caret">▶</span><span class="drug-name">${d.name}</span>
        <div class="drug-form" style="padding-left:16px">${d.form} · ${d.category}</div>
        ${seasonBadge}</td>
      <td class="num">${nf(d.stockTotal)}</td>
      <td class="num">${nf(d.stockSellable)}</td>
      <td class="num">${nf(d.forecast, 1)}</td>
      <td class="num">${dos}</td>
      <td class="num">${lossCell}</td>
      <td><span class="badge ${st.cls}">${st.text}</span></td>
    </tr>
    <tr class="detail-row" id="detail-${d.id}" hidden>
      <td colspan="7"><div class="detail-inner">
        <div><div class="detail-title">История продаж, 180 дней</div>
          ${sparkline(d.sales.slice(-180), '#2563eb')}
          <div class="spark-meta"><span>180 дн. назад</span><span>сегодня</span></div>
          <div style="margin-top:14px;font-size:13px;line-height:1.9">
            <div>Средние продажи за 14 дней: <b>${nf(d.avg14,1)}</b> уп/день</div>
            <div>Средние продажи за 28 дней: <b>${nf(d.avg28,1)}</b> уп/день</div>
            <div>Прогноз спроса: <b style="color:#2563eb">${nf(d.forecast,1)}</b> уп/день</div>
            ${d.isSeasonal ? `<div>Пиковый сезон: <b style="color:#7c3aed">${SEASON_NAMES[d.peakSeason]} ×${d.peakMult.toFixed(1)}</b> (${nf(d.peakAvg,1)} уп/день)</div>` : ''}
            <div>Срок поставки: <b>${d.leadTime}</b> дн. · упаковка ${d.packSize} уп</div>
            <div>Закупочная цена: <b>${money(d.priceIn)}</b> / уп</div>
            <div>Полный срок годности: <b>${d.shelfLifeMonths} мес.</b> · порог брака <b>${(d.shelfLifeMonths*30*0.6).toFixed(0)} дн.</b></div>
          </div></div>
        <div><div class="detail-title">Партии и их состояние</div>
          <div class="table-scroll">
            <table class="subtable"><thead><tr>
              <th>Партия</th><th class="num">Кол-во</th><th>Годен до</th>
              <th class="num">% срока</th><th class="num">Дн. до порога</th>
              <th class="num">Покрытие</th><th class="num">Продастся</th>
              <th class="num">Списание</th><th class="num">Потеря</th></tr></thead>
              <tbody>${batchRows}</tbody></table>
          </div>
          <div class="muted" style="font-size:11.5px;margin-top:8px">
            Покрытие = сколько дней продаж хватит остатка. Если покрытие &gt; дн. до порога — часть сгорит.</div>
        </div></div></td>
    </tr>`;
  }).join('');

  document.getElementById('view-stock').innerHTML = `
    <div class="card">
      <div class="card-head"><div>
        <h2>Остатки и сроки годности</h2>
        <p>Брак = срок ≤60%. Статус — сравнение покрытия с днями до порога. Клик по строке — детали</p>
      </div></div>
      <div class="table-scroll">
        <table><thead><tr>
          <th data-sort="name">Препарат</th>
          <th class="num" data-sort="stockTotal">Остаток, уп</th>
          <th class="num" data-sort="stockSellable">Продаваемый</th>
          <th class="num" data-sort="forecast">Прогноз, уп/д</th>
          <th class="num" data-sort="daysOfSupply">Запас, дн</th>
          <th class="num" data-sort="lossMoney">Риск списания</th>
          <th data-sort="status">Статус</th>
        </tr></thead><tbody>${rows}</tbody></table>
      </div>
    </div>`;
  bindSort();
  bindRowToggles();    
}

/* ---------- Приоритетные партии ---------- */
function renderPriority() {
  const list = [];
  MODEL.forEach(d => d.batches.forEach(b => {
    if (b.blockReason) list.push({ drug:d, batch:b, lost:b.qty, lostMoney:b.qty*d.priceIn, blocked:true });
    else if (b.lost > 0.5) list.push({ drug:d, batch:b, lost:b.lost, lostMoney:b.lost*d.priceIn, blocked:false });
    else if (b.status.key === 'warn' || b.status.key === 'soon')
      list.push({ drug:d, batch:b, lost:b.lost, lostMoney:b.lost*d.priceIn, blocked:false });
  }));

  list.sort((a,b) => {
    if (a.blocked !== b.blocked) return a.blocked ? -1 : 1;
    if (b.lostMoney !== a.lostMoney) return b.lostMoney - a.lostMoney;
    return a.batch.daysToBlock - b.batch.daysToBlock;
  });

  document.getElementById('cntPrio').textContent = list.filter(x => x.lost > 0.5 || x.blocked).length;

  const rows = list.slice(0, 50).map((x, idx) => {
    const d = x.drug, b = x.batch;
    const risky = x.lost > 0.5;
    const rankCls = x.lostMoney > 15000 ? 'hot' : (risky ? 'warm' : '');
    let st;
    if (x.blocked) st = `<span class="badge b-danger">${BLOCK_LABELS[b.blockReason].label}</span>`;
    else if (risky) st = `<span class="badge b-danger">Списать ${nf(x.lost)} уп</span>`;
    else st = `<span class="badge b-ok">Успеет продаться</span>`;

    // срочность
    const u = b.urgency;
    const urgCell = x.blocked || !u || u.level === 'blocked'
      ? '<span class="muted">—</span>'
      : `<span class="badge ${u.cls}">${u.label}</span>`;

    let reason;
    if (x.blocked) reason = `<b>Партия заблокирована.</b> Остаток <b>${nf(b.qty)} уп</b> (${money(b.qty*d.priceIn)}).`;
    else if (risky) reason = `Покрытие <b>${b.coverage} дн.</b>, до порога 60% — <b>${b.daysToBlock} дн.</b>
        Прогноз <b>${nf(d.forecast,1)} уп/день</b>. Списание — <b>${nf(x.lost)} уп</b> (${money(x.lostMoney)}).`;
    else reason = `<b>${d.urgency?.reason || ''}</b> Покрытие <b>${b.coverage} дн.</b>, до порога <b>${b.daysToBlock} дн.</b>`;

    return `<tr>
      <td><span class="rank ${rankCls}">${idx+1}</span></td>
      <td><div class="drug-name">${d.name}</div><div class="drug-form">${d.form}</div></td>
      <td>${b.code}</td>
      <td class="num">${nf(b.qty)}</td>
      <td>${b.expiryDate}</td>
      <td class="num">${b.percentLeft.toFixed(0)}%</td>
      <td class="num">${x.blocked ? '—' : b.daysToBlock}</td>
      <td>${urgCell}</td>
      <td class="num">${x.blocked ? '—' : b.coverage}</td>
      <td class="num ${risky ? 'text-danger' : ''}">${risky ? money(x.lostMoney) : '—'}</td>
      <td>${st}</td>
      <td><div class="prio-reason">${reason}</div></td>
    </tr>`;
  }).join('');

  document.getElementById('view-priority').innerHTML = `
    <div class="card"><div class="card-head"><div>
      <h2>Партии к первоочередной продаже</h2>
      <p>Сортировка: брак → потери → дни до порога. Срочность — сравнение дней до порога 60% со сроком поставки</p>
    </div></div>
    <div class="table-scroll">
      <table><thead><tr>
        <th>#</th><th>Препарат</th><th>Партия</th><th class="num">Остаток</th>
        <th>Годен до</th><th class="num">%</th><th class="num">Дн. порог</th>
        <th>Срочность</th>
        <th class="num">Покрытие</th><th class="num">Риск</th><th>Вердикт</th><th>Обоснование</th>
      </tr></thead><tbody>${rows || '<tr><td colspan="12" class="empty">Нет партий</td></tr>'}</tbody></table>
    </div></div>`;
}

/* ---------- Прогноз потерь ---------- */
function renderLoss() {
  const risky = MODEL.filter(d => d.lossQty > 0.5).sort((a,b) => b.lossMoney - a.lossMoney);
  document.getElementById('cntLoss').textContent = risky.length;
  const tq = sum(risky.map(d => d.lossQty));
  const tm = sum(risky.map(d => d.lossMoney));

  const rows = risky.map(d => {
    const worst = d.batches.filter(b => b.lost > 0.5).sort((a,b) => b.lost - a.lost)[0];
    const cause = worst
      ? `Партия <b>${worst.code}</b> (${nf(worst.qty)} уп) — покрытие <b>${worst.coverage} дн.</b>, до порога <b>${worst.daysToBlock} дн.</b> Спрос ${nf(d.forecast,1)}/день.`
      : '—';
    return `<tr>
      <td><div class="drug-name">${d.name}</div><div class="drug-form">${d.form}</div></td>
      <td class="num">${nf(d.stockTotal)}</td>
      <td class="num">${nf(d.forecast,1)}</td>
      <td class="num">${d.daysOfSupply > 999 ? '>999' : nf(d.daysOfSupply)}</td>
      <td class="num text-danger">${nf(d.lossQty)} уп</td>
      <td class="num text-danger">${money(d.lossMoney)}</td>
      <td><div class="prio-reason">${cause}</div></td>
    </tr>`;
  }).join('');

  document.getElementById('view-loss').innerHTML = `
    <div class="card"><div class="card-head"><div>
      <h2>Прогноз непроданных остатков</h2>
      <p>Партии, где покрытие превышает дни до порога 60%</p>
      </div><div style="text-align:right">
        <div class="muted" style="font-size:11.5px;text-transform:uppercase;font-weight:700">Итого риск</div>
        <div style="font-size:19px;font-weight:750;color:var(--danger)">${money(tm)}</div>
        <div class="muted" style="font-size:12px">${nf(tq)} упаковок</div>
      </div></div>
      <div class="table-scroll">
        <table><thead><tr>
          <th>Препарат</th><th class="num">Остаток</th><th class="num">Прогноз</th>
          <th class="num">Запас, дн</th><th class="num">Списание</th>
          <th class="num">Потеря</th><th>Причина</th>
        </tr></thead><tbody>${rows || '<tr><td colspan="7" class="empty">Списаний не прогнозируется 👍</td></tr>'}</tbody></table>
      </div>
    </div>`;
}

/* ---------- Закупки (с фильтрами и urgency) ---------- */
function renderPurchase() {
  const sorted = [...MODEL].sort((a,b) => {
    const aN = a.orderQty > 0 || a.seasonalOrderQty > 0;
    const bN = b.orderQty > 0 || b.seasonalOrderQty > 0;
    if (aN !== bN) return aN ? -1 : 1;
    const aU = a.urgency?.rank ?? 9;
    const bU = b.urgency?.rank ?? 9;
    if (aU !== bU) return aU - bU;
    return (b.orderValue + b.seasonalOrderValue) - (a.orderValue + a.seasonalOrderValue);
  });

  let filtered = sorted;
  if (purchaseFilter === 'need')   filtered = sorted.filter(d => d.orderQty > 0);
  if (purchaseFilter === 'season') filtered = sorted.filter(d => d.isSeasonal && d.seasonalOrderQty > 0 && d.orderQty === 0);
  if (purchaseFilter === 'urgent') filtered = sorted.filter(d =>
    (d.orderQty > 0 || d.seasonalOrderQty > 0) && d.urgency && d.urgency.level === 'urgent');

  document.getElementById('cntBuy').textContent =
    MODEL.filter(d => d.orderQty > 0 || d.seasonalOrderQty > 0).length;

  const cards = filtered.map(d => {
    const need = d.orderQty > 0;
    const seasonal = d.isSeasonal && d.seasonalOrderQty > 0 && !need;
    const qty = need ? d.orderQty : (seasonal ? d.seasonalOrderQty : 0);
    const val = need ? d.orderValue : (seasonal ? d.seasonalOrderValue : 0);
    const cls = need ? 'need' : (seasonal ? 'season' : 'over');
    const isUrgent = d.urgency && d.urgency.level === 'urgent' && (need || seasonal);

    const calcRows = `
      <div class="row"><span>Прогноз спроса</span><span>${nf(d.forecast,1)} уп/день</span></div>
      <div class="row"><span>Срок поставки</span><span>${d.leadTime} дн.</span></div>
      <div class="row"><span>Период планирования</span><span>${CFG.planningDays} дн.</span></div>
      <div class="row"><span>Потребность</span><span>${nf(d.demand)} уп</span></div>
      <div class="row"><span>Продастся из остатка</span><span>${nf(d.usable)} уп</span></div>
      <div class="row"><span>Кратность</span><span>${d.packSize} уп</span></div>
      <div class="row total"><span>Рекомендуемый заказ</span>
        <span style="color:${need?'var(--accent)':'var(--muted)'}">${nf(d.orderQty)} уп</span></div>`;

    let reason;
    if (need) reason = `<span class="lbl">Почему заказ</span>
        Прогноз <b>${nf(d.forecast,1)} уп/день</b>, на ${d.horizon} дн. нужно <b>${nf(d.demand)} уп</b>.
        Из остатка продастся <b>${nf(d.usable)} уп</b>${d.lossQty > 0.5 ? ` — ещё <b>${nf(d.lossQty)} уп</b> уйдёт в списание` : ''}.
        Дефицит → заказ кратно ${d.packSize}.`;
    else if (seasonal) reason = `<span class="lbl">🌨 Сезонный заказ</span>
        Сейчас ОК, но <b>${SEASON_NAMES_IN[d.peakSeason]}</b> спрос вырастет в <b>${d.peakMult.toFixed(1)}×</b>
        до <b>${nf(d.peakAvg,1)} уп/день</b>. Заказать заранее: <b>${nf(d.seasonalOrderQty)} уп</b>.`;
    else if (d.overstock) reason = `<span class="lbl">Почему не нужен</span>
        Запас <b>${nf(d.stockTotal)} уп</b>, потребность <b>${nf(d.demand)} уп</b>. Избыток >1,5×${d.lossQty>0.5?`, и <b>${nf(d.lossQty)} уп</b> рискуют сгореть`:''}.`;
    else reason = `<span class="lbl">Почему не нужен</span>
        Запаса хватает: продаваемый остаток <b>${nf(d.stockSellable)} уп</b> против потребности <b>${nf(d.demand)} уп</b>.`;

    const u = d.urgency;
    const urgLine = u
      ? `<div class="purgency">
           <span class="badge ${u.cls}">${u.label}</span>
           <span class="muted" style="font-size:12px">${u.reason}</span>
         </div>` : '';

    return `<div class="pcard ${cls} ${isUrgent ? 'urgent' : ''}">
      <div class="phead"><div>
        <div class="nm">${d.name}</div>
        <div class="fm">${d.form} · поставка ${d.leadTime} дн.${d.isSeasonal?` · 🌨 пик: ${SEASON_NAMES[d.peakSeason]}`:''}</div>
      </div><div class="pqty">
        <div class="v ${qty>0?'':'zero'}">${qty>0?'+'+nf(qty)+' уп':'0 уп'}</div>
        <div class="s">${need?money(val):(seasonal?money(val)+' · к сезону':'не требуется')}</div>
      </div></div>
      ${urgLine}
      <div class="pcalc">${calcRows}</div>
      <div class="preason">${reason}</div>
    </div>`;
  }).join('');

  document.getElementById('view-purchase').innerHTML = `
    <div class="card-head" style="background:#fff;border-radius:14px;border:1px solid var(--line);margin-bottom:16px;box-shadow:var(--shadow)">
      <div><h2>Рекомендации по закупке</h2><p>Учитываем спрос, поставку, списания и сезонность</p></div>
      <div class="filter-bar">
        <button class="filter-btn ${purchaseFilter==='all'?'active':''}"    data-filter="all">Все</button>
        <button class="filter-btn ${purchaseFilter==='need'?'active':''}"   data-filter="need">⚠️ Дефицит</button>
        <button class="filter-btn ${purchaseFilter==='season'?'active':''}" data-filter="season">🌨 Сезон</button>
        <button class="filter-btn ${purchaseFilter==='urgent'?'active':''}" data-filter="urgent">🔴 Срочные</button>
      </div>
    </div>
    <div class="pcards">${cards || '<div class="empty">Нет заказов по фильтру</div>'}</div>`;

  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.onclick = () => {
      purchaseFilter = btn.dataset.filter;
      renderPurchase();
    };
  });
}

/* ---------- раскрытие строк ---------- */
function bindRowToggles() {
  document.querySelectorAll('.main-row').forEach(row => {
    row.addEventListener('click', () => {
      const det = document.getElementById('detail-' + row.dataset.id);
      if (!det) return;
      det.hidden = !det.hidden;
      row.classList.toggle('open', !det.hidden);
    });
  });
}

/* ---------- поиск с автокомплитом ---------- */
function bindSearch() {
  const input = document.getElementById('searchInput');
  const box   = document.getElementById('searchResults');
  if (!input || !box) return;

  function close() { box.classList.remove('show'); }

  input.addEventListener('input', e => {
    const q = e.target.value.trim().toLowerCase();
    if (!q) { close(); return; }
    const res = MODEL.filter(d => d.name.toLowerCase().includes(q)).slice(0, 10);
    if (!res.length) {
      box.innerHTML = '<div class="search-empty">Ничего не найдено</div>';
    } else {
      box.innerHTML = res.map(d => `
        <div class="search-result" data-id="${d.id}">
          <span class="sr-name">${d.name}</span>
          <span class="sr-meta">${d.form} · ${d.batches.length} парт. · ${d.category}</span>
        </div>`).join('');
    }
    box.classList.add('show');

    box.querySelectorAll('.search-result').forEach(el => {
      el.onclick = () => {
        const id = +el.dataset.id;
        switchView('stock');
        // закрыть все раскрытые, раскрыть только целевой
        document.querySelectorAll('.detail-row').forEach(r => r.hidden = true);
        document.querySelectorAll('.main-row').forEach(r => r.classList.remove('open'));
        const det = document.getElementById('detail-' + id);
        const row = document.querySelector(`.main-row[data-id="${id}"]`);
        if (det && row) {
          det.hidden = false;
          row.classList.add('open');
          row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        input.value = '';
        close();
      };
    });
  });

  input.addEventListener('focus', () => {
    if (input.value.trim()) box.classList.add('show');
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('.search-wrap')) close();
  });
}

/* ---------- переключатели ---------- */
document.querySelectorAll('#tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#tabs button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.hidden = true);
    document.getElementById('view-' + btn.dataset.view).hidden = false;
  });
});

document.getElementById('periodPreset').addEventListener('change', load);

// дефолтные даты для custom
(function () {
  const f = document.getElementById('dateFrom');
  const t = document.getElementById('dateTo');
  if (!f || !t) return;
  const today = new Date();
  const past = new Date(); past.setDate(past.getDate() - 365);
  const iso = d => d.toISOString().slice(0, 10);
  f.value = iso(past); t.value = iso(today);
  f.addEventListener('change', load);
  t.addEventListener('change', load);
  document.getElementById('dateReset')?.addEventListener('click', () => {
    f.value = iso(past); t.value = iso(today); load();
  });
})();

bindSearch();

/* ---------- Загрузка CSV и шаблон ---------- */
function downloadTemplate() {
  const csv = `# АптекаПлюс — шаблон базы данных
# Секция [DRUGS] — препараты, [BATCHES] — партии.
# id связывает партию с препаратом. Флаги: 1 = проблема, 0 или пусто = норма.

[DRUGS]
id,name,form,category,packSize,priceIn,leadTime,shelfLifeMonths
n1,Анальгин 500 мг,таб. №10,Анальгетики,10,45,7,24
n2,Бисопролол 5 мг,таб. №30,Кардио,30,120,12,24
n3,Амлодипин 5 мг,таб. №30,Кардио,30,95,11,36
n4,Магний B6,таб. №50,Витамины,50,220,9,24
n5,Линекс,капс. №16,ЖКТ,16,340,10,24
n6,Энтеросгель,паста 225 г,ЖКТ,1,380,8,36

[BATCHES]
drugId,code,qty,expiry,boxOpened,storageViolation,recalled
n1,ANG-2601,150,2027-06-15,0,0,0
n1,ANG-2602,220,2028-03-01,0,0,0
n2,BSP-2601,90,2027-01-20,0,0,0
n2,BSP-2602,180,2027-10-10,0,0,0
n2,BSP-2603,120,2028-08-01,0,0,0
n3,AML-2601,200,2027-05-12,0,0,0
n3,AML-2602,160,2028-06-30,0,0,0
n4,MG-2601,140,2027-09-15,0,0,0
n4,MG-2602,100,2028-04-01,0,0,0
n5,LNX-2601,75,2027-03-22,0,0,0
n5,LNX-2602,110,2027-12-01,0,0,0
n6,ENT-2601,60,2028-02-15,0,0,0
n6,ENT-2602,45,2029-01-10,0,0,1
`;
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "aptekaplus-template.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function bindUpload() {
  const btn      = document.getElementById("uploadBtn");
  const tplBtn   = document.getElementById("templateBtn");
  const input    = document.getElementById("uploadInput");
  if (!btn || !input) return;

  btn.addEventListener("click", () => input.click());
  tplBtn?.addEventListener("click", downloadTemplate);

  input.addEventListener("change", async () => {
    const file = input.files?.[0];
    if (!file) return;

    const ok = confirm(
  `Загрузить «${file.name}»?\n\n` +
  `Новые препараты и партии добавятся к существующим.\n` +
  `Совпадения по имени препарата и коду партии будут пропущены.`
);
    if (!ok) { input.value = ""; return; }

    const fd = new FormData();
    fd.append("file", file);

    const prev = btn.textContent;
    btn.disabled = true;
    btn.textContent = "⏳ Загрузка…";

    try {
      const res  = await fetch("/api/upload", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string"
          ? data.detail
          : (data.detail?.message || JSON.stringify(data.detail) || `HTTP ${res.status}`);
        throw new Error(msg);
      }

      let msg = `Добавлено препаратов: ${data.inserted.drugs_added}`;
      if (data.inserted.drugs_reused > 0) {
        msg += ` (${data.inserted.drugs_reused} уже были, переиспользованы)`;
      }
      msg += `\nДобавлено партий: ${data.inserted.batches_added}`;
      if (data.inserted.batches_skipped > 0) {
        msg += `\nПропущено партий: ${data.inserted.batches_skipped}`;
      }
      if (data.errors?.length) {
        msg += `\n\nОшибок в строках: ${data.errors.length}`;
        msg += "\n" + data.errors.slice(0, 5).join("\n");
        if (data.errors.length > 5) msg += `\n… и ещё ${data.errors.length - 5}`;
      }
      alert(msg);
      await load();
    } catch (e) {
      alert("Ошибка загрузки: " + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = prev;
      input.value = "";
    }
  });
}

bindUpload();
/* ---------- Модалка помощи ---------- */
(function () {
  const modal = document.getElementById('helpModal');
  const btn   = document.getElementById('helpBtn');
  if (!modal || !btn) return;

  function openModal()  { modal.hidden = false; document.body.style.overflow = 'hidden'; }
  function closeModal() { modal.hidden = true;  document.body.style.overflow = ''; }

  btn.addEventListener('click', openModal);

  modal.querySelectorAll('[data-close]').forEach(el =>
    el.addEventListener('click', closeModal)
  );

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !modal.hidden) closeModal();
  });

  modal.querySelectorAll('.modal-nav a').forEach(a => {
    a.addEventListener('click', e => {
      e.preventDefault();
      const target = modal.querySelector(a.getAttribute('href'));
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
})();
load();