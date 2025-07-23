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

# 載入 .env
load_dotenv()

# 初始化 Flask 應用程式
app = Flask(__name__)
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
    return "✅ Flask app is running on Railway!"

# Price history
@app.route("/history")
@login_required
def get_history():
    ticker = request.args.get("ticker", "").strip()
    if not ticker:
        return jsonify(success=False, message="缺少股票代碼")
    try:
        data = yf.Ticker(f"{ticker}.TW").history(period="1mo")

        # ✅ reset_index 先做，保留 Date 為欄位
        data = data.reset_index()[["Date", "Close"]].dropna()

        # ✅ 格式化日期
        data["Date"] = data["Date"].dt.strftime("%Y-%m-%d")

        result = data.to_dict(orient="records")
        return jsonify(success=True, data=result)
    except Exception as e:
        return jsonify(success=False, message=str(e))


# Real-time price
@app.route("/price")
@login_required
def get_price():
    ticker = request.args.get("ticker", "").strip()
    if not ticker.isdigit():
        return jsonify(success=False, message="股票代碼應為數字")
    try:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{ticker}.tw"
        res = requests.get(url)
        data = res.json()
        msg_array = data.get("msgArray", [])
        if msg_array and "z" in msg_array[0]:
            price = float(msg_array[0]["z"])
            return jsonify(success=True, price=price)
        else:
            return jsonify(success=False, message="查無價格資料")
    except Exception as e:
        return jsonify(success=False, message="查詢失敗，請稍後再試")

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
    trades = Trade.query.filter_by(user_id=current_user.id).all()
    balance = app.config["INITIAL_BALANCE"]
    portfolio = {}
    for t in trades:
        qty = t.quantity
        cost = qty * t.price
        if t.trade_type == "買入":
            balance -= cost
            if t.ticker not in portfolio:
                portfolio[t.ticker] = {"qty": 0, "cost": 0.0}
            portfolio[t.ticker]["qty"] += qty
            portfolio[t.ticker]["cost"] += cost
        elif t.trade_type == "賣出":
            balance += cost
            if t.ticker in portfolio:
                portfolio[t.ticker]["qty"] -= qty
    result = {
        "balance": round(balance, 2),
        "portfolio": [
            {
                "ticker": t,
                "quantity": data["qty"],
                "costAvg": round(data["cost"] / data["qty"], 2) if data["qty"] > 0 else 0
            }
            for t, data in portfolio.items() if data["qty"] > 0
        ]
    }
    return jsonify(result)

# Ranking
@app.route("/ranking")
@login_required
def ranking():
    users = User.query.all()
    ranking_data = []

    def get_live_price(ticker):
        try:
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{ticker}.tw"
            res = requests.get(url)
            data = res.json()
            msg_array = data.get("msgArray", [])
            if msg_array and "z" in msg_array[0]:
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


@app.route("/ai", methods=["GET", "POST"])
def home():
    return render_template("ai.html")

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    question = data.get('question', '')

    if not question:
        return jsonify({'answer': '請輸入問題'}), 400

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": question}]
        )
        answer = response['choices'][0]['message']['content'].strip()
        return jsonify({'answer': answer})
    except Exception as e:
        return jsonify({'answer': f'AI 錯誤：{str(e)}'}), 500

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    
    port = int(os.environ.get("PORT", 8000))  # Railway 會自動設定 PORT 環境變數
    app.run(host="0.0.0.0", port=port, debug=True)  # 允許外部訪問

