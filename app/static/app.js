/* PharmaStock — фронтенд. Все расчёты выполняет Python-бэкенд (/api/model). */
const sum = a => a.reduce((x, y) => x + y, 0);
const nf = (n, d = 0) => Number(n).toLocaleString('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d });
const money = n => nf(Math.round(n)) + ' ₽';

let CFG = {};
let MODEL = [];

/* ---------- загрузка ---------- */
async function load() {
  const msl = document.getElementById('msl').value;
  const errBox = document.getElementById('error');
  try {
    const res = await fetch('/api/model?msl=' + encodeURIComponent(msl));
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);
    const data = await res.json();
    CFG = data.config;
    MODEL = data.drugs;
    document.getElementById('todayLabel').textContent = data.today;
    errBox.innerHTML = '';
    renderAll();
  } catch (e) {
    errBox.innerHTML = `<div class="error-box">Не удалось загрузить данные: ${e.message}</div>`;
  }
}

function renderAll() {
  const open = new Set([...document.querySelectorAll('.detail-row:not([hidden])')].map(r => r.id));
  renderKPIs();
  renderStock();
  renderPriority();
  renderLoss();
  renderPurchase();
  bindRowToggles();
  open.forEach(id => {                       // сохраняем раскрытые строки
    const det = document.getElementById(id);
    if (!det) return;
    det.hidden = false;
    document.querySelector(`.main-row[data-id="${id.replace('detail-', '')}"]`)?.classList.add('open');
  });
}

/* ---------- KPI ---------- */
function renderKPIs() {
  const totalValue = sum(MODEL.map(d => d.stockTotal * d.priceIn));
  const totalUnits = sum(MODEL.map(d => d.stockTotal));
  const riskValue  = sum(MODEL.map(d => d.lossMoney));
  const riskQty    = sum(MODEL.map(d => d.lossQty));
  const orderValue = sum(MODEL.map(d => d.orderValue));
  const orderCount = MODEL.filter(d => d.orderQty > 0).length;
  const deficitCnt = MODEL.filter(d => d.shortage > 0).length;

  document.getElementById('kpis').innerHTML = `
    <div class="kpi">
      <div class="kpi-label">Стоимость запасов</div>
      <div class="kpi-val">${money(totalValue)}</div>
      <div class="kpi-sub">${MODEL.length} позиций · ${nf(totalUnits)} упаковок</div>
    </div>
    <div class="kpi danger">
      <div class="kpi-label">Под риском списания</div>
      <div class="kpi-val">${money(riskValue)}</div>
      <div class="kpi-sub">${nf(riskQty)} уп за ${CFG.lossHorizonDays} дней</div>
    </div>
    <div class="kpi accent">
      <div class="kpi-label">Рекомендовано закупить</div>
      <div class="kpi-val">${money(orderValue)}</div>
      <div class="kpi-sub">${orderCount} позиций требуют заказа</div>
    </div>
    <div class="kpi ${deficitCnt ? 'danger' : ''}">
      <div class="kpi-label">Позиции в дефиците</div>
      <div class="kpi-val">${deficitCnt}</div>
      <div class="kpi-sub">не покроют спрос до следующей поставки</div>
    </div>`;
}

/* ---------- спарклайн ---------- */
function sparkline(values, color) {
  const w = 300, h = 64, pad = 4;
  const max = Math.max(...values, 1);
  const step = (w - pad * 2) / (values.length - 1);
  const pts = values.map((v, i) =>
    `${(pad + i * step).toFixed(1)},${(h - pad - (v / max) * (h - pad * 2)).toFixed(1)}`
  ).join(' ');
  const area = `${pad},${h - pad} ${pts} ${w - pad},${h - pad}`;
  return `<svg viewBox="0 0 ${w} ${h}" class="spark" preserveAspectRatio="none">
    <polygon points="${area}" fill="${color}" opacity="0.10"/>
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.8"
              stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}

/* ---------- ВКЛАДКА: СКЛАД ---------- */
function renderStock() {
  const rows = MODEL.map(d => {
    const st = d.status;
    const dos = d.daysOfSupply > 999 ? '>999' : nf(d.daysOfSupply);
    const lossCell = d.lossQty > 0
      ? `<span class="text-danger">${nf(d.lossQty)} уп</span><br><span class="muted">${money(d.lossMoney)}</span>`
      : '<span class="muted">—</span>';

    const batchRows = d.batches.map(b => {
      const leftTxt = b.lastDay > 0
        ? `<b>${b.lastDay}</b> дн.`
        : `<span class="text-danger">не продаётся</span>`;
      return `<tr>
        <td>${b.code}</td>
        <td class="num">${nf(b.qty)}</td>
        <td>${b.expiryDate}</td>
        <td class="num">${leftTxt}</td>
        <td class="num">${nf(b.sold)}</td>
        <td class="num ${b.lost > 0 ? 'text-danger' : ''}">${b.lost > 0 ? nf(b.lost) : '—'}</td>
        <td class="num ${b.lost > 0 ? 'text-danger' : ''}">${b.lost > 0 ? money(b.lost * d.priceIn) : '—'}</td>
      </tr>`;
    }).join('');

    return `
    <tr class="main-row" data-id="${d.id}">
      <td>
        <span class="caret">▶</span><span class="drug-name">${d.name}</span>
        <div class="drug-form" style="padding-left:16px">${d.form}</div>
      </td>
      <td class="num">${nf(d.stockTotal)}</td>
      <td class="num">${nf(d.stockSellable)}</td>
      <td class="num">${nf(d.forecast, 1)}</td>
      <td class="num">${dos}</td>
      <td class="num">${lossCell}</td>
      <td><span class="badge ${st.cls}">${st.text}</span></td>
    </tr>
    <tr class="detail-row" id="detail-${d.id}" hidden>
      <td colspan="7">
        <div class="detail-inner">
          <div>
            <div class="detail-title">История продаж, 90 дней</div>
            ${sparkline(d.sales.slice(-90), '#2563eb')}
            <div class="spark-meta"><span>90 дней назад</span><span>сегодня</span></div>
            <div style="margin-top:14px;font-size:13px;line-height:1.9">
              <div>Средние продажи за 14 дней: <b>${nf(d.avg14, 1)}</b> уп/день</div>
              <div>Средние продажи за 28 дней: <b>${nf(d.avg28, 1)}</b> уп/день</div>
              <div>Прогноз спроса: <b style="color:#2563eb">${nf(d.forecast, 1)}</b> уп/день</div>
              <div>Срок поставки: <b>${d.leadTime}</b> дн. · кратность ${d.packSize} уп</div>
              <div>Закупочная цена: <b>${money(d.priceIn)}</b> / уп</div>
            </div>
          </div>
          <div>
            <div class="detail-title">Партии (FEFO — первыми уходят с наименьшим сроком)</div>
            <table class="subtable">
              <thead><tr>
                <th>Партия</th><th class="num">Кол-во</th><th>Годен до</th>
                <th class="num">Дней до блокировки</th><th class="num">Продастся*</th>
                <th class="num">Списание*</th><th class="num">Потеря, ₽</th>
              </tr></thead>
              <tbody>${batchRows}</tbody>
            </table>
            <div class="muted" style="font-size:11.5px;margin-top:8px">
              * прогноз на ${CFG.lossHorizonDays} дней при текущем спросе.
              «Дней до блокировки» = срок годности − ${CFG.minShelfLifeDays} дн. (минимальный остаточный срок).
            </div>
          </div>
        </div>
      </td>
    </tr>`;
  }).join('');

  document.getElementById('view-stock').innerHTML = `
    <div class="card">
      <div class="card-head">
        <div>
          <h2>Остатки и сроки годности</h2>
          <p>Нажмите на строку, чтобы увидеть партии и историю продаж</p>
        </div>
        <div class="muted" style="font-size:12.5px">Минимальный остаточный срок годности: <b>${CFG.minShelfLifeDays} дн.</b></div>
      </div>
      <table>
        <thead><tr>
          <th>Препарат</th>
          <th class="num">Остаток, уп</th>
          <th class="num">Продаваемый остаток</th>
          <th class="num">Прогноз, уп/день</th>
          <th class="num">Запас, дней</th>
          <th class="num">Риск списания</th>
          <th>Статус</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

/* ---------- ВКЛАДКА: ПРИОРИТЕТНЫЕ ПАРТИИ ---------- */
function renderPriority() {
  const list = [];
  MODEL.forEach(d => {
    d.batches.forEach(b => {
      if (b.lastDay <= 0) return;
      list.push({ drug: d, batch: b, sold: b.sold, lost: b.lost, lostMoney: b.lost * d.priceIn });
    });
  });

  list.sort((a, b) => {
    if ((a.lost > 0) !== (b.lost > 0)) return a.lost > 0 ? -1 : 1;
    if (b.lostMoney !== a.lostMoney) return b.lostMoney - a.lostMoney;
    return a.batch.lastDay - b.batch.lastDay;
  });

  document.getElementById('cntPrio').textContent = list.filter(x => x.lost > 0).length;

  const rows = list.map((x, idx) => {
    const d = x.drug, b = x.batch;
    const risky = x.lost > 0;
    const rankCls = x.lostMoney > 15000 ? 'hot' : (risky ? 'warm' : '');
    const st = risky
      ? `<span class="badge b-danger">Списать ${nf(x.lost)} уп</span>`
      : `<span class="badge b-ok">Успеет продаться</span>`;

    const reason = risky
      ? `Партия перестанет продаваться через <b>${b.lastDay} дн.</b>
         Прогноз <b>${nf(d.forecast, 1)} уп/день</b> → до этой даты успеете продать лишь
         <b>${nf(x.sold)} уп</b> из <b>${nf(b.qty)} уп</b>.
         Ожидаемое списание — <b>${nf(x.lost)} уп</b> (${money(x.lostMoney)}).`
      : `Партия перестанет продаваться через <b>${b.lastDay} дн.</b>, но при прогнозе
         <b>${nf(d.forecast, 1)} уп/день</b> весь остаток (<b>${nf(b.qty)} уп</b>) будет распродан.
         Партия идёт в плановом FEFO-порядке.`;

    return `<tr>
      <td><span class="rank ${rankCls}">${idx + 1}</span></td>
      <td><div class="drug-name">${d.name}</div><div class="drug-form">${d.form}</div></td>
      <td>${b.code}</td>
      <td class="num">${nf(b.qty)}</td>
      <td>${b.expiryDate}</td>
      <td class="num"><b>${b.lastDay}</b></td>
      <td class="num ${risky ? 'text-danger' : ''}">${risky ? money(x.lostMoney) : '—'}</td>
      <td>${st}</td>
      <td><div class="prio-reason">${reason}</div></td>
    </tr>`;
  }).join('');

  document.getElementById('view-priority').innerHTML = `
    <div class="card">
      <div class="card-head">
        <div>
          <h2>Партии, которые нужно продавать в первую очередь</h2>
          <p>Сортировка: сначала партии с риском списания (по сумме потерь), затем — плановый FEFO-порядок</p>
        </div>
      </div>
      <table>
        <thead><tr>
          <th>#</th><th>Препарат</th><th>Партия</th><th class="num">Остаток</th>
          <th>Годен до</th><th class="num">Дней до блокировки</th>
          <th class="num">Риск потери</th><th>Вердикт</th><th>Обоснование</th>
        </tr></thead>
        <tbody>${rows || '<tr><td colspan="9" class="empty">Нет партий</td></tr>'}</tbody>
      </table>
    </div>`;
}

/* ---------- ВКЛАДКА: ПРОГНОЗ ПОТЕРЬ ---------- */
function renderLoss() {
  const risky = MODEL.filter(d => d.lossQty > 0.5).sort((a, b) => b.lossMoney - a.lossMoney);
  document.getElementById('cntLoss').textContent = risky.length;

  const totalQty = sum(risky.map(d => d.lossQty));
  const totalMoney = sum(risky.map(d => d.lossMoney));

  const rows = risky.map(d => {
    const worst = d.batches.filter(b => b.lost > 0.5).sort((a, b) => b.lost - a.lost)[0];
    const cause = worst
      ? `Партия <b>${worst.code}</b> (${nf(worst.qty)} уп) — окно продажи закрывается через
         <b>${worst.lastDay} дн.</b>, а спрос всего <b>${nf(d.forecast, 1)} уп/день</b>.`
      : '—';
    return `<tr>
      <td><div class="drug-name">${d.name}</div><div class="drug-form">${d.form}</div></td>
      <td class="num">${nf(d.stockTotal)}</td>
      <td class="num">${nf(d.forecast, 1)}</td>
      <td class="num">${d.daysOfSupply > 999 ? '>999' : nf(d.daysOfSupply)}</td>
      <td class="num text-danger">${nf(d.lossQty)} уп</td>
      <td class="num text-danger">${money(d.lossMoney)}</td>
      <td><div class="prio-reason">${cause}</div></td>
    </tr>`;
  }).join('');

  document.getElementById('view-loss').innerHTML = `
    <div class="card">
      <div class="card-head">
        <div>
          <h2>Прогноз непроданных остатков</h2>
          <p>Симуляция FEFO на ${CFG.lossHorizonDays} дней при текущем прогнозе спроса</p>
        </div>
        <div style="text-align:right">
          <div class="muted" style="font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;font-weight:700">Итого риск</div>
          <div style="font-size:19px;font-weight:750;color:var(--danger)">${money(totalMoney)}</div>
          <div class="muted" style="font-size:12px">${nf(totalQty)} упаковок</div>
        </div>
      </div>
      <table>
        <thead><tr>
          <th>Препарат</th><th class="num">Остаток</th><th class="num">Прогноз, уп/день</th>
          <th class="num">Запас, дней</th><th class="num">Списание, уп</th>
          <th class="num">Потеря, ₽</th><th>Основная причина</th>
        </tr></thead>
        <tbody>${rows || '<tr><td colspan="7" class="empty">Списаний не прогнозируется 👍</td></tr>'}</tbody>
      </table>
    </div>`;
}

/* ---------- ВКЛАДКА: ЗАКУПКИ ---------- */
function renderPurchase() {
  const sorted = [...MODEL].sort((a, b) => {
    if ((a.orderQty > 0) !== (b.orderQty > 0)) return a.orderQty > 0 ? -1 : 1;
    return b.orderValue - a.orderValue;
  });

  document.getElementById('cntBuy').textContent = MODEL.filter(d => d.orderQty > 0).length;

  const cards = sorted.map(d => {
    const need = d.orderQty > 0;
    const deficitUnits = Math.max(0, d.demand - d.usable);

    const calcRows = `
      <div class="row"><span>Прогноз спроса</span><span>${nf(d.forecast, 1)} уп/день</span></div>
      <div class="row"><span>Срок поставки</span><span>${d.leadTime} дн.</span></div>
      <div class="row"><span>Период планирования</span><span>${CFG.planningDays} дн.</span></div>
      <div class="row"><span>Потребность (× ${String(CFG.safetyFactor).replace('.', ',')})</span><span>${nf(d.demand)} уп</span></div>
      <div class="row"><span>Продастся из текущего запаса</span><span>${nf(d.usable)} уп</span></div>
      <div class="row"><span>Дефицит</span><span>${nf(deficitUnits)} уп</span></div>
      <div class="row"><span>Кратность упаковки</span><span>${d.packSize} уп</span></div>
      <div class="row total"><span>Рекомендуемый заказ</span>
        <span style="color:${need ? 'var(--accent)' : 'var(--warn)'}">${nf(d.orderQty)} уп</span></div>`;

    let reason;
    if (need) {
      reason = `<span class="lbl">Почему такая рекомендация</span>
        Прогноз спроса — <b>${nf(d.forecast, 1)} уп/день</b>. На горизонте
        «поставка ${d.leadTime} дн. + ${CFG.planningDays} дн. планирования» потребуется
        <b>${nf(d.demand)} уп</b>. Из текущего остатка (${nf(d.stockTotal)} уп) реально удастся
        продать только <b>${nf(d.usable)} уп</b>${d.lossQty > 0.5
          ? ` — остальные <b>${nf(d.lossQty)} уп</b> уйдут в списание по сроку годности` : ''}.
        Образуется дефицит <b>${nf(deficitUnits)} уп</b>, поэтому заказ округлён вверх
        до кратного ${d.packSize} уп.`;
    } else if (d.overstock) {
      reason = `<span class="lbl">Почему заказ не нужен</span>
        Физический остаток — <b>${nf(d.stockTotal)} уп</b>, а потребность на горизонте
        ${d.horizon} дн. — всего <b>${nf(d.demand)} уп</b>. Запас превышает потребность более
        чем в 1,5 раза${d.lossQty > 0.5
          ? `, и при этом <b>${nf(d.lossQty)} уп</b> (${money(d.lossMoney)}) рискуют уйти в списание` : ''}.
        Закупка не требуется — нужна ускоренная распродажа или возврат поставщику.`;
    } else {
      reason = `<span class="lbl">Почему заказ не нужен</span>
        Прогноз спроса <b>${nf(d.forecast, 1)} уп/день</b>, текущего продаваемого остатка
        (<b>${nf(d.stockSellable)} уп</b>) достаточно для покрытия потребности
        <b>${nf(d.demand)} уп</b> на горизонте ${d.horizon} дн.`;
    }

    return `
    <div class="pcard ${need ? 'need' : 'over'}">
      <div class="phead">
        <div>
          <div class="nm">${d.name}</div>
          <div class="fm">${d.form} · поставка ${d.leadTime} дн.</div>
        </div>
        <div class="pqty">
          <div class="v ${need ? '' : 'zero'}">${need ? '+' + nf(d.orderQty) + ' уп' : '0 уп'}</div>
          <div class="s">${need ? money(d.orderValue) : 'заказ не требуется'}</div>
        </div>
      </div>
      <div class="pcalc">${calcRows}</div>
      <div class="preason">${reason}</div>
    </div>`;
  }).join('');

  document.getElementById('view-purchase').innerHTML = `
    <div class="card-head" style="background:#fff;border-radius:14px;border:1px solid var(--line);margin-bottom:16px;box-shadow:0 1px 2px rgba(16,24,40,.04)">
      <div>
        <h2>Рекомендации по закупке</h2>
        <p>Расчёт учитывает прогноз спроса, срок поставки и объём, который будет списан по сроку годности</p>
      </div>
    </div>
    <div class="pcards">${cards}</div>`;
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

/* ---------- переключатели ---------- */
document.querySelectorAll('#tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#tabs button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.hidden = true);
    document.getElementById('view-' + btn.dataset.view).hidden = false;
  });
});

document.getElementById('msl').addEventListener('change', load);
load();
