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

// ================== 公用 ==================
function escapeHtml(s){ return typeof s==="string"
  ? s.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;")
  : ""; }

function aiEscape(s){ return escapeHtml(s); }

function scoreToLabelAndAdvice(s){
  if (s >= 2.0)  return {label:"偏多",   advice:"可加碼或分批佈局"};
  if (s >= 0.8)  return {label:"偏正面", advice:"觀望或小倉位"};
  if (s > -0.8)  return {label:"中性",   advice:"保持觀望"};
  if (s > -2.0)  return {label:"偏負面", advice:"減碼、保守應對"};
  return               {label:"偏空",   advice:"嚴設停損、降低曝險"};
}

// ================== 新聞 / 公告 ==================
async function fetchEvents(){
  const qInput = document.getElementById("evQuery");
  const hoursSel = document.getElementById("evHours");
  const btn = document.getElementById("evBtn");
  const list = document.getElementById("evList");

  if (!list) return; // 頁面沒有新聞清單就略過新聞
  const q = qInput?.value.trim();
  const hours = hoursSel?.value || 48;
  if (!q) return alert("請輸入代碼或關鍵字");

  ensureListIsUL();
  list.innerHTML = `<li style="color:#94a3b8;">查詢中…</li>`;
  if (btn) btn.disabled = true;

  try{
    const res = await fetch(`/api/events?query=${encodeURIComponent(q)}&hours=${encodeURIComponent(hours)}&limit=50`, {
      credentials:"include", headers:{Accept:"application/json"}
    });

    if (res.status === 401){
      list.innerHTML = `<li style="color:#fca5a5;">⚠️ 請先登入後再查詢新聞/公告</li>`;
      return;
    }

    const ct = (res.headers.get("content-type")||"").toLowerCase();
    if (!ct.includes("application/json")){
      const text = await res.text();
      list.innerHTML = `<li style="color:#fca5a5;">⚠️ 伺服器回傳非 JSON，可能需要重新登入。</li>`;
      console.warn("[/api/events non-json]", text.slice(0,200));
      return;
    }

    const data = await res.json();
    if (data.debug) console.log("[/api/events debug]", data.debug);

    if (!data.success){
      list.innerHTML = `<li style="color:#ef4444;">${data.message || "查詢失敗"}</li>`;
      return;
    }
    if (!data.items || data.items.length===0){
      list.innerHTML = `<li style="color:#94a3b8;">查無近期新聞/公告</li>`;
      return;
    }
    renderEventsWithToggle(data.items, list);
  }catch(err){
    console.error("fetchEvents error", err);
    list.innerHTML = `<li style="color:#ef4444;">⚠️ 查詢錯誤：${String(err.message || err)}</li>`;
  }finally{
    if (btn) btn.disabled = false;
  }
}

function renderEventsWithToggle(items, container){
  const EXPAND_KEY = "__expanded";
  const expanded = container.dataset[EXPAND_KEY] === "1";
  container.innerHTML = "";

  const sliceEnd = expanded ? items.length : Math.min(5, items.length);
  items.slice(0, sliceEnd).forEach(it => container.appendChild(buildEventItem(it)));

  if (items.length > 5){
    const ctrl = document.createElement("li");
    ctrl.className = "ev-more-controls";
    ctrl.style.listStyle = "none";
    ctrl.style.marginTop = "8px";
    ctrl.innerHTML = `<button type="button" class="buy-btn" id="evToggleBtn">${expanded ? "收起" : "顯示更多"}</button>`;
    container.appendChild(ctrl);

    const toggleBtn = ctrl.querySelector("#evToggleBtn");
    toggleBtn.onclick = () => {
      container.dataset[EXPAND_KEY] = expanded ? "0" : "1";
      renderEventsWithToggle(items, container);
    };
  }
}

function buildEventItem(it){
  const li = document.createElement("li");
  li.style.marginBottom = "6px";
  const riskColor = it.risk === "negative" ? "#ef4444" : it.risk === "positive" ? "#22c55e" : "#cbd5e1";
  li.innerHTML = `
    <a href="${it.url}" target="_blank" style="text-decoration:none;">
      <strong>[${it.type === "announcement" ? "公告" : "新聞"}]</strong>
      <span style="color:${riskColor};">${escapeHtml(it.title)}</span>
      <span style="font-size:12px;color:#94a3b8;">(${escapeHtml(it.source)} ${escapeHtml(it.time)})</span>
    </a>`;
  return li;
}

function ensureListIsUL(){
  const list = document.getElementById("evList");
  if (!list) return;
  if (list.tagName !== "UL"){
    const ul = document.createElement("ul");
    ul.id = "evList";
    ul.className = list.className || "";
    ul.style.cssText = list.style.cssText || "";
    ul.innerHTML = list.innerHTML;
    list.replaceWith(ul);
  }
}

// ================== AI 洞察（合併 API 版，內建 顯示更多/收回 + 說明） ==================
const AI_LIST_PAGE = 5;
let aiListState = { expanded:false, items:[] };

function ensureAiStructure(){
  // 確保基本節點存在（沒有就動態建）
  const card = document.getElementById("aiInsightCard");
  if (!card) return null;

  let top = document.getElementById("insight-top");
  if (!top){ top = document.createElement("div"); top.id = "insight-top"; top.style.cssText = "margin-top:10px;display:grid;gap:8px;"; card.appendChild(top); }

  let list = document.getElementById("insight-list");
  if (!list){ list = document.createElement("ul"); list.id = "insight-list"; list.style.margin = "10px 0 0 18px"; card.appendChild(list); }

  let ctrl = document.getElementById("insight-controls");
  if (!ctrl){
    ctrl = document.createElement("div");
    ctrl.id = "insight-controls";
    ctrl.className = "ev-more-controls";
    ctrl.style.cssText = "display:none;gap:8px;margin-top:8px;";
    ctrl.innerHTML = `
      <button type="button" class="buy-btn" id="insight-more">顯示更多</button>
      <button type="button" class="sell-btn" id="insight-collapse">收回</button>`;
    card.appendChild(ctrl);
  }

  if (!document.getElementById("insight-help-toggle")){
    const helpBar = document.createElement("div");
    helpBar.style.marginTop = "10px";
    helpBar.innerHTML = `<button id="insight-help-toggle" class="buy-btn" type="button">ℹ️ 說明</button>`;
    card.appendChild(helpBar);

    const rules = document.createElement("div");
    rules.id = "insight-rules";
    rules.style.cssText = "display:none;margin-top:8px;padding:10px;border:1px dashed #334155;border-radius:10px;";
    rules.innerHTML = `
      <strong>影響指數</strong>：方向 × 強度 × 信心（-5 ~ +5）。
      <ul class="muted" style="margin:6px 0; padding-left:18px;">
        <li>≥ +2.0：偏多 → 可加碼或分批佈局</li>
        <li>+0.8 ~ +2.0：偏正面 → 觀望或小倉位</li>
        <li>-0.8 ~ +0.8：中性 → 保持觀望</li>
        <li>-2.0 ~ -0.8：偏負面 → 減碼、保守</li>
        <li>≤ -2.0：偏空 → 嚴設停損、降低曝險</li>
      </ul>`;
    card.appendChild(rules);
  }
  return card;
}

async function loadInsightAddon(query){
  const hours = document.getElementById("evHours")?.value || 48;
  const card = ensureAiStructure();
  if (!card) return;

  const topBox    = document.getElementById("insight-top");
  const note      = document.getElementById("insight-note"); // 若你有放建議區塊就會抓到
  const scoreVal  = document.getElementById("score-val");
  const scoreLbl  = document.getElementById("score-label");
  const scoreFill = document.getElementById("score-fill");
  const listEl    = document.getElementById("insight-list");
  const ctrlEl    = document.getElementById("insight-controls");

  // 載入狀態（不顯示 0.00 / 中性）
  card.style.display = "block";
  if (topBox) topBox.innerHTML = `<div class="top-item">分析中…</div>`;
  if (note) note.textContent = "";
  if (scoreVal) scoreVal.textContent = "—";
  if (scoreLbl) scoreLbl.textContent = "分析中…";
  if (scoreFill) scoreFill.style.width = "50%";
  if (listEl) listEl.innerHTML = "";
  if (ctrlEl) ctrlEl.style.display = "none";

  try{
    const url = `/api/news-ai-insight?query=${encodeURIComponent(query)}&hours=${encodeURIComponent(hours)}&limit=1000&offset=0`;
    const res = await fetch(url, { credentials:"include" });
    const data = await res.json();
    if (!data.success) throw new Error(data.message || "分析失敗");

    // 總分
    const s  = Number(data.stock_score || 0);
    const sa = scoreToLabelAndAdvice(s);
    if (scoreVal)  scoreVal.textContent  = (s>=0?"+":"") + s.toFixed(2);
    if (scoreLbl)  scoreLbl.textContent  = sa.label;
    if (scoreFill) scoreFill.style.width = Math.max(0, Math.min(100, 50 + (s/5)*50)) + "%";
    if (note)      note.textContent      = "建議：" + sa.advice;

    // Top 事件
    if (topBox){
      topBox.innerHTML = "";
      (data.top_items || []).forEach((it, i) => {
        const color = it.direction > 0 ? "#22c55e" : it.direction < 0 ? "#ef4444" : "#9ca3af";
        const el = document.createElement("div");
        el.className = "top-item";
        el.style.cssText = "padding:10px;border:1px solid #334155;border-radius:10px;";
        el.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div><strong>#${i+1}</strong>
              <span style="color:${color}">市場氛圍：${scoreToLabelAndAdvice(Number(it.event_score||0)).label}</span> ·
              <span>影響指數 ${(it.event_score>=0?"+":"")+(Number(it.event_score||0)).toFixed(2)}</span>
            </div>
            ${it.url ? `<a href="${it.url}" target="_blank" style="color:#93c5fd;text-decoration:none;">連結</a>` : ""}
          </div>
          <div style="margin-top:6px;">${aiEscape(it.title||"")}</div>
          <div class="small" style="margin-top:6px;">${aiEscape(it.source||"")} ${aiEscape(it.time||"")}</div>
          <div style="margin-top:6px;">🤖 ${aiEscape(it.why||"")}</div>`;
        topBox.appendChild(el);
      });
    }

    // 全部事件（顯示更多 / 收回）
    aiListState.items = data.items || [];
    aiListState.expanded = false;
    renderAiList();
    updateAiControls();
  }catch(err){
    console.error(err);
    if (topBox) topBox.innerHTML = `<div class="top-item">無法取得 AI 洞察</div>`;
    if (note) note.textContent = String(err.message || err);
  }
}

function renderAiList(){
  const listEl = document.getElementById("insight-list");
  if (!listEl) return;
  const { items, expanded } = aiListState;

  listEl.innerHTML = "";
  const showing = expanded ? items : items.slice(0, AI_LIST_PAGE);

  showing.forEach(it => {
    const riskColor = it.direction > 0 ? "#22c55e" : it.direction < 0 ? "#ef4444" : "#cbd5e1";
    const score = typeof it.event_score === "number" ? it.event_score : 0;
    const li = document.createElement("li");
    li.style.marginBottom = "8px";
    li.innerHTML = `
      <a href="${it.url || "#"}" ${it.url ? 'target="_blank"' : ""} style="text-decoration:none;">
        <strong>[${it.type === "announcement" ? "公告" : "新聞"}]</strong>
        <span style="color:${riskColor}">${aiEscape(it.title || "")}</span>
        <span class="small">(${aiEscape(it.source || "")} ${aiEscape(it.time || "")})</span>
      </a>
      <div class="small" style="margin-top:2px;">
        <span style="padding:1px 6px;border:1px solid #334155;border-radius:10px;margin-right:6px;">
          影響 ${(score>=0?"+":"")}${score.toFixed(2)}
        </span>
        ${it.why ? `🤖 ${aiEscape(it.why)}` : ""}
      </div>`;
    listEl.appendChild(li);
  });

  const moreBtn = document.getElementById("insight-more");
  const colBtn  = document.getElementById("insight-collapse");
  if (moreBtn){
    moreBtn.textContent = aiListState.expanded ? "已顯示全部" : "顯示更多";
    moreBtn.disabled = aiListState.expanded || aiListState.items.length <= AI_LIST_PAGE;
  }
  if (colBtn) colBtn.disabled = !aiListState.expanded;
}

function updateAiControls(){
  const ctrlEl = document.getElementById("insight-controls");
  if (!ctrlEl) return;
  const need = aiListState.items.length > AI_LIST_PAGE;
  ctrlEl.style.display = need ? "flex" : "none";

  const moreBtn = document.getElementById("insight-more");
  const colBtn  = document.getElementById("insight-collapse");
  if (moreBtn) moreBtn.onclick = () => { aiListState.expanded = true;  renderAiList(); };
  if (colBtn)  colBtn.onclick  = () => { aiListState.expanded = false; renderAiList(); window.scrollTo({top: ctrlEl.offsetTop - 160, behavior:"smooth"}); };

  // 說明按鈕（確保可用）
  const helpBtn = document.getElementById("insight-help-toggle");
  const rules   = document.getElementById("insight-rules");
  if (helpBtn && rules && !helpBtn.__bound){
    helpBtn.__bound = true;
    helpBtn.addEventListener("click", () => {
      const show = (rules.style.display === "none" || !rules.style.display);
      rules.style.display = show ? "block" : "none";
    });
  }
}

// ================== 綁定 ==================
window.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("evBtn");
  const qEl = document.getElementById("evQuery");
  const hoursSel = document.getElementById("evHours");

  if (qEl && !qEl.value) qEl.value = "2330";

  const trigger = () => {
    const q = qEl?.value?.trim();
    if (!q) return;
    // 新聞（若頁面有 evList 就會顯示，沒有就只做 AI）
    fetchEvents();
    // AI 洞察
    loadInsightAddon(q);
  };

  if (btn) btn.addEventListener("click", trigger);
  if (qEl)  qEl.addEventListener("keydown", e => { if (e.key === "Enter") trigger(); });
  if (hoursSel) hoursSel.addEventListener("change", trigger);
});
