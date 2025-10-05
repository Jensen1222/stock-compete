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

// ======== 新聞 / 公告 ========
async function fetchEvents() {
  const qInput = document.getElementById("evQuery");
  const hoursSel = document.getElementById("evHours");
  const btn = document.getElementById("evBtn");
  const list = document.getElementById("evList");

  const q = qInput?.value.trim();
  const hours = hoursSel?.value || 48;

  if (!q) return alert("請輸入代碼或關鍵字");

  list.innerHTML = `<li style="color:#94a3b8;">查詢中…</li>`;
  btn && (btn.disabled = true);

  try {
    const res = await fetch(`/api/events?query=${encodeURIComponent(q)}&hours=${encodeURIComponent(hours)}&limit=50`);
    const data = await res.json();

    // debug 輸出（若後端有回傳）
    if (data.debug) console.log("[/api/events debug]", data.debug);

    if (!data.success) {
      list.innerHTML = `<li style="color:#ef4444;">${data.message || "查詢失敗"}</li>`;
      return;
    }

    // 沒資料時顯示提示
    if (!data.items || data.items.length === 0) {
      list.innerHTML = `<li style="color:#94a3b8;">查無近期新聞/公告</li>`;
      return;
    }

    // ✨ 一次取回全部，但初次只顯示 5 筆
    renderEventsOnceThenAll(data.items, list);
  } catch (err) {
    console.error("fetchEvents error", err);
    list.innerHTML = `<li style="color:#ef4444;">⚠️ 查詢錯誤</li>`;
  } finally {
    btn && (btn.disabled = false);
  }
}

// 初次渲染 5 筆，其餘在按鈕點擊後一次展開
function renderEventsOnceThenAll(items, container) {
  container.innerHTML = "";

  // 先顯示前 5 筆
  const first = items.slice(0, 5);
  first.forEach(it => container.appendChild(buildEventItem(it)));

  // 如果超過 5 筆，補一顆「顯示全部」按鈕
  if (items.length > 5) {
    const btn = document.createElement("button");
    btn.textContent = "顯示全部";
    btn.className = "buy-btn";
    btn.style.marginTop = "8px";

    btn.onclick = () => {
      items.slice(5).forEach(it => container.appendChild(buildEventItem(it)));
      btn.remove(); // 展開後隱藏按鈕
    };

    // 用 <li> 包一層，和清單結構一致（若你用 <ul>/<ol>）
    const wrap = document.createElement("li");
    wrap.style.listStyle = "none";
    wrap.appendChild(btn);
    container.appendChild(wrap);
  }
}

// 建立單一列表項目
function buildEventItem(it) {
  const li = document.createElement("li");
  li.style.marginBottom = "6px";
  li.innerHTML = `
    <a href="${it.url}" target="_blank" style="text-decoration:none;">
      <strong>[${it.type === "announcement" ? "公告" : "新聞"}]</strong>
      <span style="color:${it.risk === "negative" ? "red" : it.risk === "positive" ? "green" : "inherit"};">
        ${escapeHtml(it.title)}
      </span>
      <span style="font-size:12px;color:#94a3b8;">(${escapeHtml(it.source)} ${escapeHtml(it.time)})</span>
    </a>
  `;
  return li;
}

// 簡單的 XSS 防護（避免 title/source/time 含特殊字元）
function escapeHtml(s) {
  if (typeof s !== "string") return "";
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// 綁定按鈕與 Enter 鍵
window.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("evBtn");
  const q = document.getElementById("evQuery");
  if (btn) btn.addEventListener("click", fetchEvents);
  if (q) {
    if (!q.value) q.value = "2330"; // 預設台積電
    q.addEventListener("keydown", (e) => {
      if (e.key === "Enter") fetchEvents();
    });
  }
});

/* =======================
   🧠 AI Insight Frontend (Full)
   - Streaming (SSE) + Fallback
   - Score -> Label + Advice
   - Top events rendering
   ======================= */

// 安全轉義
function aiEscape(s){
  if (typeof s !== 'string') return '';
  return s.replaceAll('&','&amp;')
          .replaceAll('<','&lt;')
          .replaceAll('>','&gt;')
          .replaceAll('"','&quot;')
          .replaceAll("'",'&#39;');
}

// Score -> 標籤 & 建議（文字）
function scoreToLabelAndAdvice(s){
  if (s >= 2.0)  return {label:'偏多',     advice:'可加碼或分批佈局'};
  if (s >= 0.8)  return {label:'偏正面',   advice:'觀望或小倉位'};
  if (s > -0.8)  return {label:'中性',     advice:'保持觀望'};
  if (s > -2.0)  return {label:'偏負面',   advice:'減碼、保守應對'};
  return                {label:'偏空',     advice:'嚴設停損、降低曝險'};
}

// 行動門檻（更務實：分數不足或不確定性高 → 觀望）
function actionAdvice(score, uncertainty){
  if (Math.abs(score) < 1.8 || (uncertainty ?? 1) > 0.4) {
    return '觀望（訊號不足或不確定性偏高）';
  }
  return score > 0
    ? '偏多：可小部位試單或逢回加碼'
    : '偏空：降低曝險、逢反彈減碼';
}

// 渲染 Top 列表
function renderTopList(container, items){
  container.innerHTML = '';
  (items || []).forEach((it, i) => {
    const color = it.direction > 0 ? '#22c55e' : (it.direction < 0 ? '#ef4444' : '#9ca3af');
    const evSa = scoreToLabelAndAdvice(Number(it.event_score||0));
    const el = document.createElement('div');
    el.className = 'top-item';
    el.style.cssText = 'padding:10px;border:1px solid #334155;border-radius:10px;';
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
      <div style="margin-top:6px;color:#cbd5e1;">🤖 ${aiEscape(it.why||'')}</div>
    `;
    container.appendChild(el);
  });
}

// 非串流（完整算完再顯示）
async function loadInsightAddon(query){
  const hoursSel = document.getElementById('evHours');
  const hours = hoursSel?.value || 48;

  const card = document.getElementById('aiInsightCard');
  const topBox = document.getElementById('insight-top');
  const note = document.getElementById('insight-note');
  const scoreVal = document.getElementById('score-val');
  const scoreLabel = document.getElementById('score-label');
  const scoreFill = document.getElementById('score-fill');

  if (!card) return;
  card.style.display = 'block';
  topBox.innerHTML = `
    <div class="top-item" style="text-align:center;color:#94a3b8;">
      <div class="loader" style="border:3px solid #1f2937;border-top:3px solid #93c5fd;border-radius:50%;
        width:24px;height:24px;margin:8px auto;animation:spin .8s linear infinite;"></div>
      <p>AI 分析中…</p>
    </div>`;
  note.textContent = '';

  try {
    const res = await fetch(`/api/ai/insight?query=${encodeURIComponent(query)}&hours=${encodeURIComponent(hours)}`);
    const data = await res.json();
    if (!data.success) throw new Error(data.message || '分析失敗');

    const s = Number(data.stock_score ?? 0);
    const riskTemp = Number(data.risk_temp ?? 0);
    const uncertainty = Number(data.uncertainty ?? 1);
    const nEvents = Number(data.n_events ?? (data.items?.length ?? 0));

    // 分數 & 氛圍
    const sa = scoreToLabelAndAdvice(s);
    scoreVal.textContent = (s >= 0 ? '+' : '') + s.toFixed(2);
    scoreLabel.textContent = sa.label;
    const pct = Math.max(0, Math.min(100, 50 + (s / 5) * 50));
    scoreFill.style.width = pct + '%';

    // 建議 + 指標
    const act = actionAdvice(s, uncertainty);
    note.textContent = `建議：${act} · 風險溫度 ${riskTemp.toFixed(2)} · 不確定性 ${uncertainty.toFixed(2)} · 取樣 ${nEvents}`;

    // Top 列表
    renderTopList(topBox, data.top_items || []);
  } catch (e) {
    topBox.innerHTML = '<div class="top-item">無法取得 AI 洞察</div>';
    note.textContent = String(e.message || e);
  }
}

// 串流（SSE，陸續跑出來）
function loadInsightStream(query){
  const hoursSel = document.getElementById('evHours');
  const hours = hoursSel?.value || 48;

  const card = document.getElementById('aiInsightCard');
  const topBox = document.getElementById('insight-top');
  const note = document.getElementById('insight-note');
  const scoreVal = document.getElementById('score-val');
  const scoreLabel = document.getElementById('score-label');
  const scoreFill = document.getElementById('score-fill');

  if (!card) return;
  card.style.display = 'block';
  topBox.innerHTML = `
    <div class="top-item" style="text-align:center;color:#94a3b8;">
      <div class="loader" style="border:3px solid #1f2937;border-top:3px solid #93c5fd;border-radius:50%;
        width:24px;height:24px;margin:8px auto;animation:spin .8s linear infinite;"></div>
      <p>AI 分析中，資料將陸續顯示…</p>
    </div>`;
  note.textContent = '';
  scoreVal.textContent = '+0.00'; scoreLabel.textContent = '中性'; scoreFill.style.width = '50%';

  // 不支援 SSE 時，退回非串流
  if (!('EventSource' in window)){
    loadInsightAddon(query);
    return;
  }

  const es = new EventSource(`/api/ai/insight/stream?query=${encodeURIComponent(query)}&hours=${encodeURIComponent(hours)}`);

  const enriched = [];
  es.addEventListener('events', (e) => {
    // 可用來顯示共幾則：JSON.parse(e.data).count
  });

  es.addEventListener('list', (e) => {
    try {
      const data = JSON.parse(e.data);
      const starters = (data.items || []).map(x => ({...x, direction:0, severity:1, confidence:0.2, why:'載入中', event_score:0}));
      renderTopList(topBox, starters);
    } catch {}
  });

  es.addEventListener('item', (e) => {
    const data = JSON.parse(e.data);
    enriched.push(data.item);

    // 即時估算總分（暫時），真正最終值以 summary 為準
    const s = enriched.reduce((a,b)=>a+Number(b.event_score||0),0)/enriched.length;
    const sa = scoreToLabelAndAdvice(s);
    scoreVal.textContent = (s>=0?'+':'') + s.toFixed(2);
    scoreLabel.textContent = sa.label;
    const pct = Math.max(0, Math.min(100, 50 + (s/5)*50));
    scoreFill.style.width = pct + '%';

    // 先顯示已完成的前幾筆
    renderTopList(topBox, enriched.slice(0,3));
  });

  es.addEventListener('summary', (e) => {
    const data = JSON.parse(e.data);
    const s = Number(data.stock_score || 0);
    const sa = scoreToLabelAndAdvice(s);
    scoreVal.textContent = (s>=0?'+':'') + s.toFixed(2);
    scoreLabel.textContent = sa.label;
    const pct = Math.max(0, Math.min(100, 50 + (s/5)*50));
    scoreFill.style.width = pct + '%';

    const act = actionAdvice(s, Number(data.uncertainty||0));
    const riskTemp = Number(data.risk_temp||0);
    note.textContent = `建議：${act} · 風險溫度 ${riskTemp.toFixed(2)} · 不確定性 ${(data.uncertainty||0).toFixed(2)} · 取樣 ${data.n_events||enriched.length}`;

    // 最終 Top 列表
    renderTopList(topBox, data.top_items || []);
  });

  es.addEventListener('done', () => es.close());

  es.onerror = () => {
    es.close();
    // 串流失敗 → 退回非串流
    loadInsightAddon(query);
  };
}

// 綁定「查詢新聞」按鈕，同時觸發 AI 洞察（優先用串流）
window.addEventListener('DOMContentLoaded', () => {
  // 轉圈動畫 keyframes
  const styleSpin = document.createElement('style');
  styleSpin.textContent = '@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}';
  document.head.appendChild(styleSpin);

  const btn = document.getElementById('evBtn');
  const qEl = document.getElementById('evQuery');
  if (btn && qEl) {
    btn.addEventListener('click', () => {
      const q = qEl.value?.trim();
      if (!q) return;
      // 若你還沒上 /api/ai/insight/stream，可以改成 loadInsightAddon(q)
      loadInsightStream(q);
    });
  }

  // ℹ️ 說明開關
  const toggleBtn = document.getElementById('insight-help-toggle');
  const ruleBox = document.getElementById('insight-rules');
  if (toggleBtn && ruleBox){
    toggleBtn.addEventListener('click', () => {
      ruleBox.style.display = (ruleBox.style.display === 'none' || !ruleBox.style.display) ? 'block' : 'none';
    });
  }
});

