import json
import os
import time
import uuid

DB_FILE = "data.json"

class Database:
    def __init__(self):
        self.file = DB_FILE
        self._init_db()

    def _init_db(self):
        if not os.path.exists(self.file):
            data = {
                "users": {},
                "settings": {
                    "start_text": "👋 Welcome to Premium MMS!\n\n🔥 50,000+ Videos\n\nChoose an option below 👇",
                    "upi_id": "yourname@upi",
                    "private_link": "https://t.me/+example",
                    "plans": {
                        "plan_1": {"name": "Basic", "price": 59},
                        "plan_2": {"name": "Standard", "price": 99},
                        "plan_3": {"name": "Most Popular", "price": 149},
                        "plan_4": {"name": "VIP", "price": 199}
                    }
                },
                "payments": {},
                "demo_videos": []
            }
            self._save(data)

    def _load(self):
        with open(self.file, "r") as f:
            return json.load(f)

    def _save(self, data):
        with open(self.file, "w") as f:
            json.dump(data, f, indent=2)

    def add_user(self, user_id, username):
        data = self._load()
        uid = str(user_id)
        if uid not in data["users"]:
            data["users"][uid] = {
                "username": username,
                "joined": time.time()
            }
            self._save(data)

    def get_all_users(self):
        data = self._load()
        return [int(uid) for uid in data["users"].keys()]

    def get_total_users(self):
        data = self._load()
        return len(data["users"])

    def get_settings(self):
        data = self._load()
        return data.get("settings", {})

    def update_setting(self, key, value):
        data = self._load()
        data["settings"][key] = value
        self._save(data)

    def add_payment(self, user_id, plan_name, price, file_id):
        data = self._load()
        payment_id = str(uuid.uuid4())[:8]
        data["payments"][payment_id] = {
            "user_id": user_id,
            "plan": plan_name,
            "price": price,
            "file_id": file_id,
            "status": "pending",
            "time": time.time()
        }
        self._save(data)
        return payment_id

    def update_payment(self, payment_id, status):
        data = self._load()
        if payment_id in data["payments"]:
            data["payments"][payment_id]["status"] = status
            self._save(data)

    def add_demo_video(self, file_id):
        data = self._load()
        data["demo_videos"].append({"file_id": file_id})
        self._save(data)

    def get_demo_videos(self):
        data = self._load()
        return data.get("demo_videos", [])

    def clear_demo_videos(self):
        data = self._load()
        data["demo_videos"] = []
        self._save(data)

db = Database()
