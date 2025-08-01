from flask import Flask, render_template, request, jsonify, redirect, url_for
import requests
from datetime import datetime
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
from datetime import timedelta

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



# Ranking
@app.route("/ranking")
@login_required
def ranking():
    users = User.query.all()
    ranking_data = []

    def get_live_price(ticker):
        try:
            for market in ['tse', 'otc']:
                url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={market}_{ticker}.tw"
                res = requests.get(url)
                data = res.json()
                msg_array = data.get("msgArray", [])
                if msg_array and "z" in msg_array[0] and msg_array[0]["z"] != "-":
                    return float(msg_array[0]["z"])
        except:
            pass
        return None

    for user in users:
        trades = Trade.query.filter_by(user_id=user.id).all()
        balance = app.config["INITIAL_BALANCE"]
        portfolio = {}
        for t in trades:
            qty = t.quantity
            cost = qty * t.price
            if t.trade_type == "買入":
                balance -= cost
                if t.ticker not in portfolio:
                    portfolio[t.ticker] = {"qty": 0}
                portfolio[t.ticker]["qty"] += qty
            elif t.trade_type == "賣出":
                balance += cost
                if t.ticker in portfolio:
                    portfolio[t.ticker]["qty"] -= qty
        total_value = balance
        for t, pos in portfolio.items():
            if pos["qty"] > 0:
                live_price = get_live_price(t)
                if live_price:
                    total_value += pos["qty"] * live_price
        ranking_data.append({
            "username": user.username,
            "total_value": round(total_value, 2)
        })

    # ⚠️ 確保最後這一行一定要有：
    ranking_data.sort(key=lambda x: x["total_value"], reverse=True)
    return render_template("ranking.html", ranking_data=ranking_data)


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

def find_ticker_by_company_name(user_input: str):
    for _, row in stock_info_df.iterrows():
        if row["stock_name"] in user_input:
            return row["stock_id"], row["stock_name"]
    return None, None

@app.route("/ask-ai", methods=["POST"])
def ask_ai():
    user_input = request.json.get("question", "").strip()
    if not user_input:
        return jsonify({"success": False, "message": "❗️請輸入問題"})

    # 嘗試比對公司名稱 → 股票代碼
    ticker, company_name = find_ticker_by_company_name(user_input)
    stock_summary = ""

    if ticker:
        today = datetime.today()
        start_date = (today - timedelta(days=14)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        try:
            df = api.taiwan_stock_daily(stock_id=ticker, start_date=start_date, end_date=end_date)

            # 只保留有收盤價的資料（排除停牌）
            df = df[df["close"].notna()]
            df = df.sort_values("date")

            if len(df) >= 2:
                start_price = df.iloc[-2]["close"]
                end_price = df.iloc[-1]["close"]
                pct = ((end_price - start_price) / start_price) * 100
                stock_summary = f"{company_name}（{ticker}）近兩個交易日股價從 {start_price:.2f} 元變動至 {end_price:.2f} 元，漲跌幅為 {pct:.2f}%。"
            else:
                stock_summary = f"查無足夠的 {company_name}（{ticker}）股價資料。"
        except Exception as e:
            stock_summary = f"⚠️ 無法取得股價資料：{str(e)}"

    else:
        stock_summary = "⚠️ 未能辨識輸入中的公司名稱。"

    # 將提示送給 GPT
    prompt = f"""{stock_summary}
使用者問題：「{user_input}」
請根據上述資料分析公司近期表現，提供具體投資建議。"""

    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一位專業的台股投資分析師，請根據資料做出清楚、有條理的回覆。"},
                {"role": "user", "content": prompt}
            ]
        )
        answer = response.choices[0].message.content
        return jsonify({"success": True, "answer": answer})
    except Exception as e:
        return jsonify({"success": False, "message": f"❌ GPT 回覆失敗：{str(e)}"})




if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    
    port = int(os.environ.get("PORT", 8000))  # Railway 會自動設定 PORT 環境變數
    app.run(host="0.0.0.0", port=port, debug=True)  # 允許外部訪問

