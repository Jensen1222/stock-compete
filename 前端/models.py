from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

# 初始化 SQLAlchemy 實例（僅此一處）
db = SQLAlchemy()

# 使用者資料表
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    balance = db.Column(db.Float, default=10000000, nullable=False)  # 💰 初始資金一千萬

    # 關聯交易紀錄與測驗結果
    trades = db.relationship('Trade', backref='user', lazy=True)
    results = db.relationship('Result', backref='user', lazy=True)

# 交易紀錄資料表
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    trade_type = db.Column(db.String(10), nullable=False)  # "買入" 或 "賣出"
    mode = db.Column(db.String(10), default="整股")  # 整股或零股
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# 投資個性測驗結果資料表
class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    style = db.Column(db.String(20), nullable=False)
    suggestion = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
