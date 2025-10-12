from flask import Flask, render_template, request, jsonify, redirect, url_for
import requests
import yfinance as yf
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Trade, Result
from flask_cors import CORS
import openai
from dotenv import load_dotenv
import os
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd
from collections import defaultdict, deque
from openai import OpenAI 
from FinMind.data import DataLoader
from flask import Response, stream_with_context
from datetime import datetime, timedelta
import math
import time
import html as py_html
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
from typing import Optional
from email.utils import parsedate_to_datetime





# 載入 .env 檔案
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
finmind_token = os.getenv("FINMIND_TOKEN")

client = OpenAI(api_key=api_key)

# 初始化 FinMind 客戶端
api = DataLoader()
api.login_by_token(api_token=finmind_token)

# 初始化 Flask 應用程式
app = Flask(
    __name__,
    static_folder="static",         # 明確指定 static 路徑
    template_folder="templates"     # 明確指定 HTML 模板資料夾
)
CORS(app)

# 設定環境變數
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key')

MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

# 設定 MySQL 連線
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['INITIAL_BALANCE'] = 10000000

# 初始化資料庫（使用 models.py 的 db 實例）
db.init_app(app)

# 初始化登入管理
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Homepage
@app.route("/")
@login_required
def index():
    return render_template("index.html")

def home():
    return render_template('ai.html')

# Price history
@app.route("/history")
@login_required
def get_history():
    
    ticker = request.args.get("ticker", "").strip()
    if not ticker:
        return jsonify(success=False, message="缺少股票代碼")

    try:
        # 試著用 .TW，若 404 就用 .TWO
        try:
            data = yf.Ticker(f"{ticker}.TW").history(period="1mo")
            if data.empty:
                raise Exception("empty")
        except:
            data = yf.Ticker(f"{ticker}.TWO").history(period="1mo")
            if data.empty:
                raise Exception("empty")

        data = data.reset_index()[["Date", "Close"]].dropna()
        data["Date"] = pd.to_datetime(data["Date"]).dt.strftime("%Y-%m-%d")

        result = data.to_dict(orient="records")
        return jsonify(success=True, data=result)

    except Exception as e:
        return jsonify(success=False, message=f"查詢歷史價格失敗：{str(e)}")




@app.route("/price")
@login_required
def get_price():
    ticker = request.args.get("ticker", "").strip()
    if not ticker.isdigit():
        return jsonify(success=False, message="股票代碼應為數字")

    # 嘗試從 TWSE 抓取
    try:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{ticker}.tw"
        res = requests.get(url)
        data = res.json()
        msg_array = data.get("msgArray", [])
        if msg_array and "z" in msg_array[0]:
            z = msg_array[0]["z"]
            if z and z != "-":
                price = float(z)
                return jsonify(success=True, price=price)
    except Exception as e:
        print(f"⚠️ TWSE 抓取失敗：{e}")

    # 改用 Yahoo 抓（順序先 TWO 再 TW）
    for suffix in [".TWO", ".TW"]:
        try:
            stock = yf.Ticker(ticker + suffix)
            hist = stock.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                return jsonify(success=True, price=price)
        except Exception as e:
            print(f"⚠️ Yahoo 抓 {ticker + suffix} 失敗：{e}")

    return jsonify(success=False, message="查無價格資料（TWSE & Yahoo）")




        
# Buy stock
@app.route("/buy", methods=["POST"])
@login_required
def buy():
    data = request.get_json()
    ticker = data.get("ticker")
    quantity = int(data.get("quantity", 0))  # 股數
    price = float(data.get("price", 0))
    mode = data.get("mode", "整股")  # 如果從 JS 傳來

    if not ticker or quantity <= 0 or price <= 0:
        return jsonify(success=False, message="資料錯誤")

    total_cost = quantity * price

    user = User.query.get(current_user.id)
    if user is None:
        return jsonify(success=False, message="找不到使用者")

    if total_cost > user.balance:
        return jsonify(success=False, message="餘額不足，無法完成交易")

    new_trade = Trade(
        user_id=user.id,
        ticker=ticker,
        quantity=quantity,
        price=price,
        trade_type="買入",
        mode=mode,
        created_at=datetime.utcnow()
    )

    user.balance -= total_cost
    db.session.add(new_trade)
    db.session.commit()

    return jsonify(success=True)

# Sell stock
@app.route("/sell", methods=["POST"])
@login_required
def sell():
    data = request.get_json()
    ticker = data.get("ticker")
    quantity = int(data.get("quantity", 0))
    price = float(data.get("price", 0))
    mode = data.get("mode", "整股")

    if not ticker or quantity <= 0 or price <= 0:
        return jsonify(success=False, message="資料錯誤")

    user = User.query.get(current_user.id)

    # 計算該股票總持有股數（整股 + 零股）
    all_trades = Trade.query.filter_by(user_id=user.id, ticker=ticker).all()
    total_qty = sum(t.quantity if t.trade_type == "買入" else -t.quantity for t in all_trades)

    if quantity > total_qty:
        return jsonify(success=False, message="❌ 持股不足，無法賣出")

    total_gain = quantity * price

    new_trade = Trade(
        user_id=user.id,
        ticker=ticker,
        quantity=quantity,
        price=price,
        trade_type="賣出",
        mode=mode,
        created_at=datetime.utcnow()
    )

    user.balance += total_gain

    db.session.add(new_trade)
    db.session.commit()

    return jsonify(success=True)


@app.route('/trade', methods=['POST'])
@login_required
def trade():
    data = request.form  # ✅ 正確的地方

    ticker = data.get('ticker')
    quantity = int(data.get('quantity', 0))
    price = float(data.get('price', 0))
    trade_type = data.get('trade_type')  # "買入" or "賣出"
    mode = data.get('mode', "零股")  # 預設為零股模式

    if not ticker or quantity <= 0 or price <= 0 or trade_type not in ["買入", "賣出"]:
        return jsonify({"success": False, "message": "參數錯誤"}), 400

    user = User.query.get(current_user.id)
    cost = quantity * price

    if trade_type == "買入":
        if user.balance < cost:
            return jsonify({"success": False, "message": "餘額不足"}), 400
        user.balance -= cost

    elif trade_type == "賣出":
        holdings = db.session.query(
            db.func.sum(Trade.quantity)
        ).filter_by(user_id=user.id, ticker=ticker).scalar() or 0
        if holdings < quantity:
            return jsonify({"success": False, "message": "持股不足"}), 400
        user.balance += cost

    new_trade = Trade(
        user_id=user.id,
        ticker=ticker,
        quantity=quantity,
        price=price,
        trade_type=trade_type,
        mode=mode,
        created_at=datetime.utcnow()
    )
    db.session.add(new_trade)
    db.session.commit()

    return jsonify({"success": True, "message": f"{mode}交易完成"})



# Portfolio API
@app.route("/api/portfolio")
@login_required
def api_portfolio():
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.created_at).all()
    balance = Decimal(app.config["INITIAL_BALANCE"])
    
    portfolio = defaultdict(lambda: {
        "lots": deque(),   # 每筆買入記錄 (quantity, price)
        "qty": Decimal("0"),
    })

    for t in trades:
        qty = Decimal(t.quantity)
        price = Decimal(str(t.price))  # 避免 float 精度問題
        cost = qty * price

        if t.trade_type == "買入":
            balance -= cost
            portfolio[t.ticker]["lots"].append((qty, price))
            portfolio[t.ticker]["qty"] += qty

        elif t.trade_type == "賣出":
            balance += cost
            remaining = qty
            lots = portfolio[t.ticker]["lots"]
            portfolio[t.ticker]["qty"] -= qty

            # FIFO: 先把最早買入的扣掉
            while remaining > 0 and lots:
                lot_qty, lot_price = lots[0]
                if lot_qty > remaining:
                    lots[0] = (lot_qty - remaining, lot_price)
                    remaining = Decimal("0")
                else:
                    remaining -= lot_qty
                    lots.popleft()

            # 若已全部賣光，清除資料
            if portfolio[t.ticker]["qty"] <= 0:
                portfolio[t.ticker]["qty"] = Decimal("0")
                portfolio[t.ticker]["lots"].clear()

    result = {
        "balance": float(balance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "portfolio": []
    }

    for ticker, data in portfolio.items():
        total_qty = data["qty"]
        if total_qty == 0:
            continue
        total_cost = sum(q * p for q, p in data["lots"])
        avg_cost = total_cost / total_qty
        result["portfolio"].append({
            "ticker": ticker,
            "quantity": float(total_qty),
            "costAvg": float(avg_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        })

    return jsonify(result)

@app.route("/update-total-assets", methods=["POST"])
@login_required
def update_total_assets():
    data = request.get_json()
    total_assets = data.get("totalAssets")

    if total_assets is None:
        return jsonify(success=False, message="缺少總資產")

    user = User.query.get(current_user.id)
    user.total_assets = total_assets
    db.session.commit()

    return jsonify(success=True)


def build_ranking_data():
    """
    回傳已排序的 [(username, total_asset), ...]（高→低）。
    直接沿用你 /ranking 內的計算邏輯。
    """
    import requests
    import yfinance as yf

    def get_stock_price(ticker):
        # 1) 先試 TWSE
        try:
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{ticker}.tw"
            res = requests.get(url, timeout=3)
            data = res.json()
            msg_array = data.get("msgArray", [])
            if msg_array:
                z = msg_array[0].get("z")
                if z and z != "-":
                    return float(z)
        except Exception as e:
            print(f"⚠️ TWSE 抓 {ticker} 價格失敗：{e}")

        # 2) 改用 Yahoo (TW / TWO)
        for suffix in [".TWO", ".TW"]:
            try:
                stock = yf.Ticker(ticker + suffix)
                hist = stock.history(period="5d")
                if not hist.empty:
                    close_prices = hist["Close"].dropna()
                    if not close_prices.empty:
                        return float(close_prices.iloc[-1])
            except Exception as e:
                print(f"⚠️ Yahoo 抓 {ticker + suffix} 失敗：{e}")

        print(f"❌ {ticker} 完全抓不到價格")
        return 0.0

    users = User.query.all()
    ranking_data = []

    for user in users:
        cash = user.balance
        trades = Trade.query.filter_by(user_id=user.id).all()

        holdings = {}
        for trade in trades:
            qty = trade.quantity if trade.trade_type in ["買入", "buy"] else -trade.quantity
            holdings[trade.ticker] = holdings.get(trade.ticker, 0) + qty

        total_stock_value = 0.0
        for ticker, qty in holdings.items():
            if qty > 0:
                price = get_stock_price(ticker)
                total_stock_value += price * qty

        total_asset = round(cash + total_stock_value, 2)
        ranking_data.append((user.username, total_asset))

    ranking_data.sort(key=lambda x: x[1], reverse=True)
    return ranking_data

# ✅ 保持你原有的 /ranking（改成呼叫共用函式）
@app.route("/ranking")
@login_required
def ranking():
    ranking_data = build_ranking_data()
    return render_template("ranking.html", ranking_data=ranking_data)

# ✅ 新增：首頁拿「目前使用者名次 / 總人數」的 API
@app.route("/api/user-rank")
@login_required
def api_user_rank():
    ranking_data = build_ranking_data()
    total = len(ranking_data)
    rank = next((i + 1 for i, (uname, _) in enumerate(ranking_data)
                 if uname == current_user.username), None)
    my_assets = next((assets for uname, assets in ranking_data
                      if uname == current_user.username), None)
    return jsonify(success=True, rank=rank, total=total, assets=my_assets)




# Quiz with database save
@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    if request.method == "POST":
        q1 = int(request.form.get("q1", 0))
        q2 = int(request.form.get("q2", 0))
        q3 = int(request.form.get("q3", 0))
        q4 = int(request.form.get("q4", 0))
        q5 = int(request.form.get("q5", 0))
        score = q1 + q2 + q3 + q4 + q5

        if score <= 3:
            style = "穩健型"
            suggestion = "建議分散投資於低風險資產，如債券或大型藍籌股。"
        elif score <= 7:
            style = "成長型"
            suggestion = "可考慮配置部分資金於成長型股票或ETF，追求資本增長。"
        else:
            style = "積極型"
            suggestion = "可承擔較高風險，建議配置新興市場或高波動性資產，但仍需注意風險控管。"

        # ✅ 寫入資料庫
        result = Result(
            user_id=current_user.id,
            score=score,
            style=style,
            suggestion=suggestion,
            created_at=datetime.utcnow()
        )
        db.session.add(result)
        db.session.commit()

        return render_template("result.html", style=style, advice=suggestion)

    return render_template("quiz.html")


@app.route("/results")
@login_required
def results():
    filter_style = request.args.get("style", "全部")
    if filter_style == "全部":
        filtered_results = Result.query.all()
    else:
        filtered_results = Result.query.filter_by(style=filter_style).all()

    style_counts = {
        "穩健型": Result.query.filter_by(style="穩健型").count(),
        "成長型": Result.query.filter_by(style="成長型").count(),
        "積極型": Result.query.filter_by(style="積極型").count()
    }
    total = Result.query.count()

    return render_template("results.html", total=total,
                           style_counts=style_counts,
                           results=filtered_results,
                           filter_style=filter_style)

# User Registration
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if User.query.filter_by(username=username).first():
            return '帳號已存在'
        new_user = User(
            username=username,
            password=generate_password_hash(password, method='pbkdf2:sha256')
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect("/login")
    return render_template("register.html")

# User Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect("/")
        return "登入失敗，請檢查帳號密碼"
    return render_template("login.html")

# Logout
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

@app.route("/trades")
@login_required
def trades():
    trade_records = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.created_at.desc()).all()
    return render_template("trades.html", trades=trade_records)

# trading view
@app.route("/api/market_type")
def get_market_type():
    ticker = request.args.get("ticker", "").strip()
    if not ticker.isdigit() or len(ticker) != 4:
        return jsonify(success=False, message="股票代碼格式錯誤")

    try:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{ticker}.tw|otc_{ticker}.tw"
        res = requests.get(url)
        data = res.json().get("msgArray", [])

        for stock in data:
            if stock["c"] == ticker:
                market = stock["ex"]  # 會是 'tse' 或 'otc'
                return jsonify(success=True, market=market.upper())
        return jsonify(success=False, message="查無此股票代碼")
    except Exception as e:
        return jsonify(success=False, message=f"查詢失敗：{str(e)}")

#ai
@app.route("/ai.html")
def ai_page():
    return render_template("ai.html")

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
finmind_token = os.getenv("FINMIND_TOKEN")

# 初始化 FinMind 並取得公司列表一次（可快取）
api = DataLoader()
api.login_by_token(api_token=finmind_token)
stock_info_df = api.taiwan_stock_info()

# 根據輸入找出股票代號與公司名稱
def find_ticker_by_company_name(user_input: str):
    for _, row in stock_info_df.iterrows():
        if row["stock_name"] in user_input or row["stock_id"] in user_input:
            return row["stock_id"], row["stock_name"]
    return None, None

# 初始化 FinMind 並取得公司列表一次（可快取）
api = DataLoader()
api.login_by_token(api_token=finmind_token)
stock_info_df = api.taiwan_stock_info()

# 根據輸入找出股票代號與公司名稱
def find_ticker_by_company_name(user_input: str):
    for _, row in stock_info_df.iterrows():
        if row["stock_name"] in user_input or row["stock_id"] in user_input:
            return row["stock_id"], row["stock_name"]
    return None, None

@app.route("/ask-ai", methods=["POST"])
def ask_ai():
    data = request.json
    user_input = data.get("question", "").strip()
    mode = data.get("type", "analysis")

    if not user_input:
        return Response("❗️請輸入問題", mimetype='text/plain')

    def generate(user_input, mode):
        yield "💬 回答：\n\n"

        model = "gpt-4"
        prompt = ""
        system_role = ""

        # 嘗試找公司資訊
        ticker, company_name = find_ticker_by_company_name(user_input)

        if mode == "analysis":
            system_role = "你是一位專業的台股投資分析師，請給出專業且實用的建議。"

            if ticker:
                try:
                    today = datetime.today()
                    start_date = (today - timedelta(days=14)).strftime("%Y-%m-%d")
                    end_date = today.strftime("%Y-%m-%d")
                    df = api.taiwan_stock_daily(stock_id=ticker, start_date=start_date, end_date=end_date)
                    df = df[df["close"].notna()].sort_values("date")

                    if len(df) >= 2:
                        start_price = df.iloc[-2]["close"]
                        end_price = df.iloc[-1]["close"]
                        pct = ((end_price - start_price) / start_price) * 100
                        stock_summary = f"資料摘要：{company_name}（{ticker}）近兩個交易日股價從 {start_price:.2f} 元變動至 {end_price:.2f} 元，漲跌幅為 {pct:.2f}%。"
                    else:
                        stock_summary = f"⚠️ 查無足夠的 {company_name}（{ticker}）股價資料。"
                except Exception as e:
                    stock_summary = f"⚠️ 無法取得股價資料：{str(e)}"
            else:
                stock_summary = "⚠️ 無法辨識公司名稱或股票代碼。"

            yield stock_summary + "\n\n"

            prompt = f"""{stock_summary}
使用者問題：「{user_input}」
請根據上述資料分析該公司近期表現，提供具體投資建議。"""

        else:  # mode == future
            system_role = "你是一位專業的台灣股票顧問，擅長分析產業趨勢與企業長期發展潛力，請用長期視角給出建議。"

            if ticker:
                company_intro = f"公司名稱：{company_name}（{ticker}）\n"
                user_input = f"{company_name}（{ticker}）的未來發展"
            else:
                company_intro = ""

            prompt = f"""{company_intro}使用者問題：「{user_input}」
請以長期（3～5 年）投資視角，根據該公司所處產業的未來趨勢、全球環境、技術創新與競爭力，提供完整、清晰的展望與策略建議。"""

        try:
            client = openai.OpenAI()
            stream = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_role},
                    {"role": "user", "content": prompt}
                ],
                stream=True
            )

            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        except Exception as e:
            yield f"\n❌ GPT 回覆失敗：{str(e)}"

    return Response(stream_with_context(generate(user_input, mode)), mimetype="text/plain")


NEGATIVE_KWS = ["停工","減產","虧損","調降評等","賣超","裁員","稅務","違規","罰款","火災","爆炸","停電","跳票","倒閉","減資","警示","處分","下修","解雇"]
POSITIVE_KWS = ["擴產","上修","買超","得標","合作","併購","創高","創新","獲利成長","認購","回購","增資","漲停","利多","展望正面"]

def _label_risk(text: str) -> str:
    t = (text or "").strip()
    if any(k in t for k in NEGATIVE_KWS): return "negative"
    if any(k in t for k in POSITIVE_KWS): return "positive"
    return "neutral"

def _maybe_get_name_by_code(q: str) -> Optional[str]:
    q = (q or "").strip()
    if q.isdigit() and len(q) in (4, 5):
        row = stock_info_df[stock_info_df["stock_id"] == q]
        if not row.empty:
            return str(row.iloc[0]["stock_name"])
    return None

# ======================= Google News RSS 備援 =======================
def _fetch_google_news_rss(keyword: str, hours: int = 48, limit: int = 50):
    """
    從 Google News RSS 抓關鍵字新聞（台灣／繁中）
    回傳 list[dict]: {type, title, source, time, url, risk}
    """
    base = "https://news.google.com/rss/search"
    url = f"{base}?q={quote_plus(keyword)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsFetcher/1.0; +https://example.com)"}
    try:
        resp = requests.get(url, timeout=10, headers=headers)
        if resp.status_code != 200 or not resp.text:
            return []
        root = ET.fromstring(resp.text)
        channel = root.find("channel")
        if channel is None:
            return []

        cutoff = datetime.now() - timedelta(hours=hours)
        out = []
        for item in channel.findall("item"):
            title_raw = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date_str = (item.findtext("{http://purl.org/dc/elements/1.1/}date")
                            or item.findtext("pubDate") or "").strip()

            # 時間解析 + 視窗過濾
            try:
                dt = parsedate_to_datetime(pub_date_str) if pub_date_str else None
                if dt and dt.tzinfo:
                    dt = dt.astimezone(tz=None).replace(tzinfo=None)
                if dt and dt < cutoff:
                    continue
            except Exception:
                pass

            # 拆出來源：「標題 - 來源」格式常見
            source = ""
            title = title_raw
            if " - " in title_raw:
                *tparts, src = title_raw.split(" - ")
                title = " - ".join(tparts).strip()
                source = src.strip()

            title = py_html.unescape(title)

            out.append({
                "type": "news",
                "title": title,
                "source": source or "Google News",
                "time": pub_date_str or datetime.now().strftime("%Y-%m-%d %H:%M"),
                "url": link,
                "risk": _label_risk(title),
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        print(f"[rss] fetch error: {e}")
        return []

# ======================= FinMind：新聞 / 公告 多路徑 =======================
def _try_fetch_news(code: Optional[str], keyword: Optional[str],
                    start_date: str, end_date: str, debug_log: list):
    import pandas as pd
    frames = []

    # 1) stock_id + start/end
    if code:
        try:
            df = api.taiwan_stock_news(stock_id=code, start_date=start_date, end_date=end_date)
            debug_log.append(f"news(stock_id,start/end): {len(df) if df is not None else 'None'}")
            if df is not None and not df.empty: frames.append(df)
        except Exception as e:
            debug_log.append(f"news(stock_id,start/end) error: {e}")

    # 2) keyword + start/end
    if keyword:
        try:
            df = api.taiwan_stock_news(keyword=keyword, start_date=start_date, end_date=end_date)
            debug_log.append(f"news(keyword,start/end): {len(df) if df is not None else 'None'}")
            if df is not None and not df.empty: frames.append(df)
        except Exception as e:
            debug_log.append(f"news(keyword,start/end) error: {e}")

    # 3) 近幾天逐日掃描
    try:
        days = 5
        for i in range(days):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            try:
                if code:
                    df = api.taiwan_stock_news(stock_id=code, date=d)
                    if df is not None and not df.empty: frames.append(df)
                if keyword:
                    dfk = api.taiwan_stock_news(keyword=keyword, date=d)
                    if dfk is not None and not dfk.empty: frames.append(dfk)
            except Exception:
                pass
        debug_log.append(f"news(daily sweep frames): {sum(len(f) for f in frames) if frames else 0}")
    except Exception as e:
        debug_log.append(f"news(daily sweep) error: {e}")

    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()

def _try_fetch_ann(code: Optional[str], keyword: Optional[str],
                   start_date: str, end_date: str, debug_log: list):
    import pandas as pd
    frames = []
    funcs = []
    for name in ["taiwan_stock_announcement", "taiwan_stock_announcements"]:
        f = getattr(api, name, None)
        if f: funcs.append(f)

    # 1) start/end
    for f in funcs:
        try:
            if code:
                df = f(stock_id=code, start_date=start_date, end_date=end_date)
                debug_log.append(f"{f.__name__}(stock_id,start/end): {len(df) if df is not None else 'None'}")
                if df is not None and not df.empty: frames.append(df)
            if keyword:
                df = f(keyword=keyword, start_date=start_date, end_date=end_date)
                debug_log.append(f"{f.__name__}(keyword,start/end): {len(df) if df is not None else 'None'}")
                if df is not None and not df.empty: frames.append(df)
        except Exception as e:
            debug_log.append(f"{f.__name__}(start/end) error: {e}")

    # 2) 近幾天逐日掃描
    for f in funcs:
        try:
            days = 5
            for i in range(days):
                d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                try:
                    if code:
                        df = f(stock_id=code, date=d)
                        if df is not None and not df.empty: frames.append(df)
                    if keyword:
                        dfk = f(keyword=keyword, date=d)
                        if dfk is not None and not dfk.empty: frames.append(dfk)
                except Exception:
                    pass
            debug_log.append(f"{f.__name__}(daily sweep frames): {sum(len(fm) for fm in frames) if frames else 0}")
        except Exception as e:
            debug_log.append(f"{f.__name__}(daily sweep) error: {e}")

    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()

# ======================= 新：核心抓取邏輯（無 login，純資料） =======================
def _fetch_events_core(q: str, hours: int = 48, limit: int = 50):
    debug_log = []
    is_code = q.isdigit()
    code = q if is_code else None
    keyword = _maybe_get_name_by_code(q) if is_code else q

    since_dt = datetime.now() - timedelta(hours=hours)
    start_date = since_dt.strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    items = []

    # ---- FinMind 新聞 ----
    try:
        df_news = _try_fetch_news(code, keyword, start_date, end_date, debug_log)
        if df_news is not None and not df_news.empty:
            for _, r in df_news.iterrows():
                title = str(r.get("title") or r.get("news_title") or "")
                src = str(r.get("source") or r.get("media") or "新聞")
                url = str(r.get("url") or r.get("link") or "")
                dt = str(r.get("date") or r.get("time") or end_date)
                if dt >= start_date and title:
                    items.append({
                        "type": "news",
                        "title": title,
                        "source": src,
                        "time": dt,
                        "url": url,
                        "risk": _label_risk(title),
                    })
        else:
            debug_log.append("FinMind news empty")
    except Exception as e:
        debug_log.append(f"news total error: {e}")

    # ---- FinMind 公告 ----
    try:
        df_ann = _try_fetch_ann(code, keyword, start_date, end_date, debug_log)
        if df_ann is not None and not df_ann.empty:
            for _, r in df_ann.iterrows():
                title = str(r.get("title") or r.get("subject") or "")
                url = str(r.get("url") or r.get("link") or "")
                dt = str(r.get("date") or r.get("time") or end_date)
                if dt >= start_date and title:
                    items.append({
                        "type": "announcement",
                        "title": title,
                        "source": "公開資訊觀測站",
                        "time": dt,
                        "url": url,
                        "risk": _label_risk(title),
                    })
        else:
            debug_log.append("FinMind announcements empty")
    except Exception as e:
        debug_log.append(f"ann total error: {e}")

    # ---- FinMind 完全抓不到 → RSS 備援 ----
    if not items:
        rss_kw = (keyword or q).strip()
        rss_items = _fetch_google_news_rss(rss_kw, hours=hours, limit=limit)
        debug_log.append(f"RSS items: {len(rss_items)}")
        items.extend(rss_items)

    # ---- 去重 + 排序 ----
    seen = set()
    dedup = []
    for it in items:
        key = (it.get("title","").strip().lower(), (it.get("source","") or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        dedup.append(it)

    # FinMind 多為 YYYY-MM-DD；RSS 可能含時間字串，這裡仍用字串降序即可
    dedup.sort(key=lambda x: x.get("time", ""), reverse=True)
    return dedup[:limit], debug_log

# ======================= /api/events（改用核心） =======================
@app.get("/api/events")
@login_required
def api_events():
    """
    /api/events?query=2330&hours=48&limit=50
    /api/events?query=台積電
    FinMind 抓不到 → 自動用 Google News RSS 備援
    """
    q = request.args.get("query", "").strip()
    hours = int(request.args.get("hours", "48"))
    limit = int(request.args.get("limit", "50"))
    if not q:
        return jsonify(success=False, message="請提供 query（股票代碼或關鍵字）"), 400

    items, debug_log = _fetch_events_core(q, hours=hours, limit=limit)
    return jsonify(
        success=True,
        query=q,
        items=items,
        window_hours=hours,
        debug=debug_log
    )

# ======================= 內部共用：不再繞 test_request_context =======================
def _get_events_raw(query: str, hours: int = 48, limit: int = 50):
    """
    回傳 (items, debug_log)
    直接走 _fetch_events_core，避免內部再呼叫帶有 @login_required 的 API。
    """
    items, debug = _fetch_events_core(query, hours=hours, limit=limit)
    return items, debug

# ======================= AI 小助手（沿用你原本設定） =======================
AI_PROMPT_MINI = (
    "你是金融事件分析助手。請針對輸入的一則中文新聞或公告，僅回傳 JSON：\n"
    "{\n"
    "  \"direction\": -1 | 0 | 1,\n"
    "  \"severity\": 1-5,\n"
    "  \"horizon\": \"短\"|\"中\"|\"長\",\n"
    "  \"confidence\": 0.0-1.0,\n"
    "  \"why\": \"50字內重點原因\"\n"
    "}\n"
    "若無法判斷，direction=0、severity=1、confidence<=0.3。"
)

def _ai_rule_eval_basic(title: str) -> dict:
    risk = _label_risk(title or "")
    if risk == "positive":
        return {"direction": 1, "severity": 3, "horizon": "短", "confidence": 0.55, "why": "偏多關鍵詞"}
    if risk == "negative":
        return {"direction": -1, "severity": 3, "horizon": "短", "confidence": 0.55, "why": "偏空關鍵詞"}
    return {"direction": 0, "severity": 1, "horizon": "短", "confidence": 0.3, "why": "資訊有限"}

def _ai_event_score(info: dict) -> float:
    d = int(info.get("direction", 0))
    sev = max(1, min(5, int(info.get("severity", 1))))
    conf = max(0.0, min(1.0, float(info.get("confidence", 0.0))))
    return d * sev * conf

def _ai_eval_one_event(text: str) -> dict:
    # 有 OPENAI_API_KEY 才走 LLM，否則走規則
    if not api_key:
        return _ai_rule_eval_basic(text)
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": AI_PROMPT_MINI},
                {"role": "user", "content": text[:1800]},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        msg = resp.choices[0].message
        parsed = getattr(msg, "parsed", None) or getattr(msg, "content", None)
        if isinstance(parsed, dict):
            return parsed
    except Exception as e:
        print(f"[AI] error fallback: {e}")
    return _ai_rule_eval_basic(text)

# ======================= AI enrich 與分數聚合 =======================
def _enrich_with_ai(items: list) -> tuple[list, float]:
    """
    回傳 (enriched_items, stock_score)；每則事件多：direction/severity/horizon/confidence/event_score
    stock_score 用 |event_score| 當權重做加權平均
    """
    enriched = []
    for ev in items:
        text = f"{ev.get('title','')}（來源:{ev.get('source','')} 時間:{ev.get('time','')}）"
        info = _ai_eval_one_event(text)
        ev_score = _ai_event_score(info)
        enriched.append({**ev, **info, "event_score": ev_score})

    if not enriched:
        return [], 0.0

    num = den = 0.0
    for x in enriched:
        w = max(0.1, abs(x["event_score"]))
        num += x["event_score"] * w
        den += w
    stock_score = num / den if den > 0 else 0.0

    return enriched, round(stock_score, 3)

# ======================= 單一路徑：新聞AI洞察 + 分頁 =======================
@app.get("/api/news-ai-insight")
@login_required
def api_news_ai_insight():
    """
    統一後端 API：新聞AI洞察
      /api/news-ai-insight?query=2330&hours=48&limit=5&offset=0
    回傳：
      - items：這一頁的事件（已含 AI 欄位）
      - total/offset/limit/has_more：分頁資訊
      - stock_score、top_items（取 |event_score| 最大的前 3）
    """
    q = request.args.get("query", "").strip()
    hours = int(request.args.get("hours", "48"))
    limit = max(1, int(request.args.get("limit", "5")))     # 預設每頁 5
    offset = max(0, int(request.args.get("offset", "0")))   # 起始偏移

    if not q:
        return jsonify(success=False, message="請提供 query（股票代碼或關鍵字）"), 400

    # 1) 取得全部事件
    all_items, debug_log = _get_events_raw(q, hours=hours, limit=max(50, limit*4))
    total = len(all_items)

    # 2) AI enrich 一次做完，再分頁切片（確保排序穩定）
    enriched_all, stock_score = _enrich_with_ai(all_items)

    # 3) Top 3 by |event_score|
    top_items = sorted(enriched_all, key=lambda z: abs(z.get("event_score", 0)), reverse=True)[:3]

    # 4) 分頁
    page_items = enriched_all[offset: offset + limit]
    has_more = (offset + limit) < total

    return jsonify(
        success=True,
        query=q,
        window_hours=hours,
        total=total,
        offset=offset,
        limit=limit,
        has_more=has_more,
        stock_score=stock_score,
        items=page_items,
        top_items=top_items,
        debug=debug_log
    )

# ======================= 相容路徑：/api/ai/insight =======================
@app.get("/api/ai/insight")
@login_required
def api_ai_insight_compat():
    """
    舊路徑相容：維持行為，但建議前端改用 /api/news-ai-insight 做分頁。
    """
    q = request.args.get("query", "").strip()
    hours = int(request.args.get("hours", "48"))
    limit = int(request.args.get("limit", "50"))
    if not q:
        return jsonify(success=False, message="請提供 query（股票代碼或關鍵字）"), 400

    all_items, debug_log = _get_events_raw(q, hours=hours, limit=limit)
    enriched_all, stock_score = _enrich_with_ai(all_items)
    top_items = sorted(enriched_all, key=lambda z: abs(z.get("event_score", 0)), reverse=True)[:3]

    return jsonify(
        success=True,
        query=q,
        stock_score=stock_score,
        items=enriched_all,
        top_items=top_items,
        debug=debug_log
    )






if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    
    port = int(os.environ.get("PORT", 8000))  # Railway 會自動設定 PORT 環境變數
    app.run(host="0.0.0.0", port=port, debug=True)  # 允許外部訪問

