from app import app
from models import db

with app.app_context():
    db.create_all()
    print("✅ 資料表已成功建立")
