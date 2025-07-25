from app import app
from models import db, Trade

with app.app_context():
    user_id = 2  # 你要查的帳號 ID
    ticker = "2330"
    trades = Trade.query.filter_by(user_id=user_id, trade_type="買入", ticker=ticker).all()

    print(f"📊 查詢帳號 ID={user_id}，股票代號 {ticker} 的買入紀錄：\n")
    for t in trades:
        print(f"🧾 買入股數: {t.quantity} | 單價: {t.price} | 成本: {t.quantity * t.price}")
