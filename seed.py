import sqlite3
import random
from datetime import datetime, timedelta

conn = sqlite3.connect('smm_panel.db')
cur = conn.cursor()

methods  = ['click', 'payme', 'uzcard', 'humo', 'crypto']
statuses = ['completed', 'completed', 'completed', 'pending', 'failed']
descs    = ['Hisob toldirish', 'Balans yuklash', 'Tulov', 'Depozit', 'Refill']
types    = ['deposit', 'deposit', 'deposit', 'withdrawal', 'refund']

def rand_date():
    days = random.randint(1, 365)
    dt = datetime.now() - timedelta(days=days)
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def rand_amount():
    return round(random.choice([
        5000, 10000, 15000, 20000, 25000,
        50000, 75000, 100000, 150000, 200000,
        500000, 1000000
    ]) * random.uniform(0.8, 1.2), 2)

for i in range(600):
    user_id = random.randint(1, 5)
    cur.execute("INSERT INTO deposits (user_id, amount, method, status, tx_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, rand_amount(), random.choice(methods), random.choice(statuses), f"TX{random.randint(100000,999999)}", rand_date()))

for i in range(600):
    user_id = random.randint(1, 5)
    cur.execute("INSERT INTO transactions (user_id, type, amount, description, ref_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, random.choice(types), rand_amount(), random.choice(descs), f"REF{random.randint(10000,99999)}", random.choice(statuses), rand_date()))

conn.commit()
conn.close()
print("600ta deposit + 600ta transaction qoshildi!")
