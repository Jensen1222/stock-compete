from app import app
from models import db, User

with app.app_context():
    user = db.session.get(User, 2)
    if user:
        print(f"🔁 原本餘額：{user.balance}")
        user.balance = 5747670
        db.session.commit()
        print(f"✅ 餘額已更新為：{user.balance}")
    else:
        print("❌ 找不到 id=2 的使用者")
