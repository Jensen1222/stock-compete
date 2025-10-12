let balance = 0;
let portfolio = {};
let priceData = {};
let historyChart; // 用來畫歷史價格趨勢圖表

// 格式化貨幣
function formatCurrency(v) {
  return '$' + Number(v).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}


// 即時價格取得
function getRealTimePrice(ticker, callback) {
  fetch(`/price?ticker=${ticker}`)
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        const price = parseFloat(data.price);
        priceData[ticker] = priceData[ticker] || [];
        priceData[ticker].push(price);
        if (priceData[ticker].length > 30) priceData[ticker].shift();
        callback(price);
      } else {
        alert("查無資料：" + data.message);
      }
    })
    .catch(err => {
      console.error("取得價格失敗", err);
      alert("取得價格失敗");
    });
}

// 整股買入
function buyStock() {
  const ticker = document.getElementById('ticker').value.trim();
  const quantity = Number(document.getElementById('quantity').value);
  if (!ticker || quantity <= 0) return alert('請輸入完整資料');

  const totalShares = quantity * 1000;

  getRealTimePrice(ticker, (price) => {
    fetch('/buy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, quantity: totalShares, price })
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          alert("✅ 買入成功");
          loadPortfolio();
        } else {
          alert("❌ " + data.message);
        }
      })
      .catch(err => {
        console.error("❌ 請求失敗", err);
        alert("⚠️ 請求失敗，請稍後再試");
      });
  });
}

// 整股賣出
function sellStock() {
  const ticker = document.getElementById('ticker').value.trim();
  const quantity = Number(document.getElementById('quantity').value);
  if (!ticker || quantity <= 0) return alert('請輸入完整資料');

  const totalShares = quantity * 1000;

  getRealTimePrice(ticker, (price) => {
    fetch('/sell', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, quantity: totalShares, price })
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          alert("✅ 賣出成功");
          loadPortfolio();
        } else {
          alert("❌ " + data.message);
        }
      })
      .catch(err => {
        console.error("❌ 請求失敗", err);
        alert("⚠️ 請求失敗，請稍後再試");
      });
  });
}

// 零股交易（買入或賣出）
function tradeLot(type) {
  const ticker = document.getElementById('ticker-lot').value.trim();
  const quantity = Number(document.getElementById('quantity-lot').value);
  if (!ticker || quantity <= 0) return alert('請輸入正確資料');

  getRealTimePrice(ticker, (price) => {
    fetch('/trade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        ticker,
        quantity,
        price,
        trade_type: type,
        mode: '零股'
      })
    })
      .then(res => res.redirected ? window.location.href = res.url : res.json())
      .then(data => {
        if (data?.success === false) {
          alert("❌ " + data.message);
        } else {
          alert(`✅ ${type}成功`);
          loadPortfolio();
        }
      })
      .catch(err => {
        console.error("❌ 零股交易失敗", err);
        alert("⚠️ 零股交易請求失敗");
      });
  });
}

// 取得並更新投資組合資料
function loadPortfolio() {
  fetch('/api/portfolio')
    .then(res => res.json())
    .then(data => {
      balance = data.balance;
      portfolio = {};
      const tickers = [];

      data.portfolio.forEach(p => {
        portfolio[p.ticker] = { qty: p.quantity, costAvg: p.costAvg };
        tickers.push(p.ticker);
      });

      return Promise.all(tickers.map(ticker => {
        return fetch(`/price?ticker=${ticker}`)
          .then(res => res.json())
          .then(data => {
            if (data.success) {
              priceData[ticker] = priceData[ticker] || [];
              priceData[ticker].push(parseFloat(data.price));
              if (priceData[ticker].length > 30) priceData[ticker].shift();
            }
          });
      }));
    })
    .then(() => renderAll())
    .catch(err => {
      console.error("載入投資組合失敗", err);
    });
}

// 渲染投資組合表格
function renderPortfolio() {
  const tbody = document.querySelector('#portfolio-table tbody');
  tbody.innerHTML = '';

  for (const ticker in portfolio) {
    const pos = portfolio[ticker];
    const price = priceData[ticker]?.slice(-1)[0] || pos.costAvg;
    const costTotal = pos.costAvg * pos.qty;
    const marketValue = price * pos.qty;
    const profit = marketValue - costTotal;
    const profitPct = pos.costAvg > 0 ? (profit / costTotal) * 100 : 0;

    // 決定文字顏色
    const profitColor = profit >= 0 ? 'style="color: green;"' : 'style="color: red;"';
    const profitSign = profit >= 0 ? '+' : '-';
    const profitText = `${profitSign} $${Math.abs(profit).toFixed(2)} (${profitSign}${Math.abs(profitPct).toFixed(2)}%)`;

    const tr = document.createElement('tr');
     tr.innerHTML = `
       <td>${ticker}</td>
       <td>${Math.floor(pos.qty / 1000)} 張 ${pos.qty % 1000} 股</td>
       <td>${formatCurrency(pos.costAvg)}</td>
       <td>${formatCurrency(price)}</td>
       <td>${formatCurrency(marketValue)}</td>
       <td class="profit-cell" style="color: ${profit >= 0 ? 'green' : 'red'};">
         ${profit >= 0 ? '+' : '-'} $${Math.abs(profit).toFixed(2)} (${profitPct >= 0 ? '+' : '-'}${Math.abs(profitPct).toFixed(2)}%)
       </td>


   `;

    tbody.appendChild(tr);
  }
}





// 更新總資產與表格
function renderAll() {
  document.getElementById('balance').innerText = formatCurrency(balance);

  let totalAssets = balance;
  for (const t in portfolio) {
    const pos = portfolio[t];
    const price = priceData[t]?.slice(-1)[0] || pos.costAvg;
    totalAssets += price * pos.qty;
  }
  document.getElementById('total-assets').innerText = formatCurrency(totalAssets);

  renderPortfolio();
}

// 歷史走勢查詢與圖表更新
function queryTaiwanStock() {
  const ticker = document.getElementById("queryTicker").value.trim();
  if (!ticker) return alert("請輸入股票代碼");

  // 即時價格
  fetch(`/price?ticker=${ticker}`)
    .then(res => res.json())
    .then(data => {
      document.getElementById("currentPrice").textContent =
        data.success
          ? `${ticker} 當前價格為：$${data.price}`
          : `查無即時價格：${data.message}`;
    });

  // 歷史走勢
  fetch(`/history?ticker=${ticker}`)
    .then(res => res.json())
    .then(data => {
      if (!data.success) return alert("查詢歷史價格失敗：" + data.message);

      const ctx = document.getElementById("chart").getContext("2d");
      const labels = data.data.map(entry => entry.Date);
      const prices = data.data.map(entry => entry.Close);

      if (historyChart) {
        historyChart.data.labels = labels;
        historyChart.data.datasets[0].data = prices;
        historyChart.data.datasets[0].label = `${ticker} 過去30天`;
        historyChart.update();
      } else {
        historyChart = new Chart(ctx, {
          type: "line",
          data: {
            labels,
            datasets: [{
              label: `${ticker} 過去30天`,
              data: prices,
              borderColor: "#00c853",
              fill: false
            }]
          },
          options: {
            responsive: true,
            scales: {
              x: {
                title: { display: true, text: '日期' }
              },
              y: {
                title: { display: true, text: '收盤價' }
              }
            }
          }
        });
      }
    });
}



// 初始化與按鈕綁定
window.addEventListener('DOMContentLoaded', () => {
  loadPortfolio();
  loadUserRank(); // 排名
  document.getElementById('buy-lot-btn')?.addEventListener('click', () => tradeLot('買入'));
  document.getElementById('sell-lot-btn')?.addEventListener('click', () => tradeLot('賣出'));
});

// 排名
function loadUserRank() {
  fetch('/api/user-rank')
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        document.getElementById('user-rank').textContent = data.rank ?? '--';
        document.getElementById('user-count').textContent = data.total ?? '--';
      }
    })
    .catch(err => console.error('載入排名失敗', err));
}

// ======== 新聞AI洞察（合併：新聞 / 公告 + AI） ========

// 簡單 XSS 防護
function escapeHtml(s) {
  if (typeof s !== "string") return "";
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
function aiEscape(s){ return escapeHtml(s); }

// 由分數推導標籤與建議（與你原本一致）
function scoreToLabelAndAdvice(s){
  if (s >= 2.0)  return {label:'偏多',     advice:'可加碼或分批佈局'};
  if (s >= 0.8)  return {label:'偏正面',   advice:'觀望或小倉位'};
  if (s > -0.8)  return {label:'中性',     advice:'保持觀望'};
  if (s > -2.0)  return {label:'偏負面',   advice:'減碼、保守應對'};
  return                {label:'偏空',     advice:'嚴設停損、降低曝險'};
}

// direction 轉中文
function dirLabel(d){
  if (d > 0) return '偏多';
  if (d < 0) return '偏空';
  return '中性';
}

// 事件列表項目（已合併 AI 欄位）
function buildEventItem(it) {
  const li = document.createElement("li");
  li.style.marginBottom = "8px";
  li.style.listStyle = "none";
  const riskColor = it.direction > 0 ? '#22c55e' : (it.direction < 0 ? '#ef4444' : '#cbd5e1');
  const tag = it.type === "announcement" ? "公告" : "新聞";
  const why = it.why ? `🤖 ${aiEscape(it.why)}` : '';
  const evScore = typeof it.event_score === 'number' ? (it.event_score >= 0 ? '+' : '') + it.event_score.toFixed(2) : '';
  li.innerHTML = `
    <div style="padding:10px;border:1px solid #334155;border-radius:10px;background:#0b1220;">
      <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;">
        <div>
          <strong>[${tag}]</strong>
          <a href="${it.url || '#'}" target="_blank" style="text-decoration:none;color:#93c5fd;">
            ${escapeHtml(it.title || '')}
          </a>
          <div style="font-size:12px;color:#94a3b8;margin-top:2px;">
            ${escapeHtml(it.source || '')} · ${escapeHtml(it.time || '')}
          </div>
        </div>
        <div style="text-align:right;min-width:120px;">
          <div style="color:${riskColor};font-weight:600;">${dirLabel(Number(it.direction||0))}</div>
          <div style="font-size:12px;color:#94a3b8;">影響 ${(evScore || '0.00')}</div>
          <div style="font-size:12px;color:#94a3b8;">區間 ${escapeHtml(it.horizon || '短')}</div>
          <div style="font-size:12px;color:#94a3b8;">置信 ${(Number(it.confidence||0)).toFixed(2)}</div>
        </div>
      </div>
      ${why ? `<div style="margin-top:6px;color:#cbd5e1;">${why}</div>` : ''}
    </div>
  `;
  return li;
}

// ===== 分頁狀態（顯示更多 / 收起） =====
const evState = {
  query: '',
  hours: 48,
  limit: 5,     // 初次顯示 5 筆
  offset: 0,
  total: 0,
  has_more: false,
  // 暫存目前已渲染（可選）：需要時再加
};

// 呼叫統一路徑：/api/news-ai-insight
async function fetchNewsAI(isLoadMore = false) {
  const qInput  = document.getElementById("evQuery");
  const hoursSel= document.getElementById("evHours");
  const btn     = document.getElementById("evBtn");
  const list    = document.getElementById("evList");

  const q = (qInput?.value || '').trim();
  const hours = hoursSel?.value || 48;
  if (!q) return alert("請輸入代碼或關鍵字");

  if (!isLoadMore) {
    // 新查詢：重置狀態
    evState.query = q;
    evState.hours = hours;
    evState.offset = 0;
  }

  // Loading UI
  if (!isLoadMore) list.innerHTML = `<li style="color:#94a3b8;list-style:none;">查詢中…</li>`;
  btn && (btn.disabled = true);

  try {
    const url = `/api/news-ai-insight?query=${encodeURIComponent(evState.query)}&hours=${encodeURIComponent(evState.hours)}&limit=${encodeURIComponent(evState.limit)}&offset=${encodeURIComponent(evState.offset)}`;
    const res = await fetch(url);
    const data = await res.json();

    if (data.debug) console.log("[/api/news-ai-insight debug]", data.debug);
    if (!data.success) {
      list.innerHTML = `<li style="color:#ef4444;list-style:none;">${data.message || "查詢失敗"}</li>`;
      return;
    }

    // 更新 AI 卡片（同一次回應）
    updateInsightCardFromResponse(data);

    // 沒資料
    if (!data.items || data.items.length === 0) {
      if (!isLoadMore) list.innerHTML = `<li style="color:#94a3b8;list-style:none;">查無近期新聞/公告</li>`;
      return;
    }

    // 渲染列表（支援追加）
    if (!isLoadMore) list.innerHTML = "";
    data.items.forEach(it => list.appendChild(buildEventItem(it)));

    // 分頁狀態
    evState.total   = Number(data.total || 0);
    evState.has_more= Boolean(data.has_more);
    evState.offset  = Number(data.offset || 0) + Number(data.limit || evState.limit);

    // 重新渲染「顯示更多 / 收起」控制列
    renderMoreControls(list);

  } catch (err) {
    console.error("fetchNewsAI error", err);
    list.innerHTML = `<li style="color:#ef4444;list-style:none;">⚠️ 查詢錯誤</li>`;
  } finally {
    btn && (btn.disabled = false);
  }
}

// 控制列（顯示更多 / 收起）
function renderMoreControls(container){
  // 先移除舊控制列
  const old = container.querySelector('li[data-more-controls]');
  if (old) old.remove();

  // 新控制列
  const liCtrl = document.createElement('li');
  liCtrl.setAttribute('data-more-controls', '1');
  liCtrl.style.listStyle = 'none';
  liCtrl.style.marginTop = '8px';

  const wrap = document.createElement('div');
  wrap.style.display = 'flex';
  wrap.style.gap = '8px';

  if (evState.has_more) {
    const moreBtn = document.createElement('button');
    moreBtn.textContent = '顯示更多';
    moreBtn.className = 'buy-btn';
    moreBtn.onclick = () => fetchNewsAI(true);
    wrap.appendChild(moreBtn);
  }

  // 只要不是「完全沒資料」，就給收起
  if (evState.offset > evState.limit) {
    const collapseBtn = document.createElement('button');
    collapseBtn.textContent = '收起';
    collapseBtn.className = 'sell-btn';
    collapseBtn.onclick = () => {
      // 重新查一次 offset=0 的第一頁
      evState.offset = 0;
      fetchNewsAI(false);
    };
    wrap.appendChild(collapseBtn);
  }

  // 右側顯示統計
  const meta = document.createElement('div');
  meta.style.marginLeft = 'auto';
  meta.style.color = '#94a3b8';
  meta.style.fontSize = '12px';
  meta.textContent = `${Math.min(evState.offset, evState.total)}/${evState.total}`;

  liCtrl.appendChild(wrap);
  liCtrl.appendChild(meta);
  container.appendChild(liCtrl);
}

// ===== AI Insight 卡片（用同一個 API 回應更新） =====
function updateInsightCardFromResponse(data){
  const card       = document.getElementById('aiInsightCard');
  const topBox     = document.getElementById('insight-top');
  const note       = document.getElementById('insight-note');
  const scoreVal   = document.getElementById('score-val');
  const scoreLabel = document.getElementById('score-label');
  const scoreFill  = document.getElementById('score-fill');

  if (!card) return;
  card.style.display = 'block';

  const s = Number(data.stock_score || 0);
  const sa = scoreToLabelAndAdvice(s);

  if (scoreVal)   scoreVal.textContent   = (s >= 0 ? '+' : '') + s.toFixed(2);
  if (scoreLabel) scoreLabel.textContent = sa.label;
  if (note)       note.textContent       = '建議：' + sa.advice;

  if (scoreFill) {
    const pct = Math.max(0, Math.min(100, 50 + (s / 5) * 50)); // -5~+5 → 0~100%
    scoreFill.style.width = pct + '%';
  }

  if (topBox) {
    topBox.innerHTML = '';
    (data.top_items || []).forEach((it, i) => {
      const color = it.direction > 0 ? '#22c55e' : (it.direction < 0 ? '#ef4444' : '#9ca3af');
      const el = document.createElement('div');
      el.className = 'top-item';
      el.style.cssText = 'padding:10px;border:1px solid #334155;border-radius:10px;background:#0b1220;';
      const evSa = scoreToLabelAndAdvice(Number(it.event_score||0));
      el.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div><strong>#${i+1}</strong>
            <span style="color:${color}">市場氛圍：${evSa.label}</span> ·
            <span>影響指數 ${(it.event_score>=0?'+':'')+(Number(it.event_score||0)).toFixed(2)}</span>
          </div>
          ${it.url ? `<a href="${it.url}" target="_blank" style="color:#93c5fd;text-decoration:none;">連結</a>` : ''}
        </div>
        <div style="margin-top:6px;">${aiEscape(it.title||'')}</div>
        <div style="margin-top:6px;font-size:12px;color:#94a3b8;">${aiEscape(it.source||'')} ${aiEscape(it.time||'')}</div>
        ${it.why ? `<div style="margin-top:6px;color:#cbd5e1;">🤖 ${aiEscape(it.why)}</div>` : ''}
      `;
      topBox.appendChild(el);
    });
  }
}

// ===== 綁定查詢按鈕 & Enter =====
window.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("evBtn");
  const q   = document.getElementById("evQuery");
  const hoursSel = document.getElementById("evHours");

  if (q && !q.value) q.value = "2330"; // 預設台積電

  if (btn) btn.addEventListener("click", () => fetchNewsAI(false));
  if (q)   q.addEventListener("keydown", (e) => { if (e.key === "Enter") fetchNewsAI(false); });
  if (hoursSel) hoursSel.addEventListener("change", () => fetchNewsAI(false));
});
