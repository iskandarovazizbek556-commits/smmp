import sqlite3
import random
import hashlib
from datetime import datetime, timedelta

conn = sqlite3.connect('smm_panel.db')
cur = conn.cursor()

uzbek_names = [
    'azizbek', 'jasurbek', 'sardorbek', 'boburbek', 'otabek',
    'sherzod', 'ulugbek', 'sanjar', 'bekzod', 'eldor',
    'dilnoza', 'malika', 'nilufar', 'sarvinoz', 'mohira',
    'zulfiya', 'kamola', 'munira', 'feruza', 'shahnoza',
    'javlon', 'umid', 'mirzo', 'doniyor', 'firdavs',
    'husan', 'islom', 'lochinbek', 'mansur', 'nodir'
]

domains = ['gmail.com', 'mail.ru', 'yahoo.com', 'inbox.ru']

def fake_password():
    return hashlib.sha256(b'Password123').hexdigest()

def rand_date():
    start = datetime(2024, 12, 1)
    end   = datetime(2025, 5, 1)
    delta = end - start
    return (start + timedelta(days=random.randint(0, delta.days),
                              hours=random.randint(0,23),
                              minutes=random.randint(0,59))).strftime('%Y-%m-%d %H:%M:%S')

def rand_ref():
    return ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))

for i in range(150):
    name     = random.choice(uzbek_names) + str(random.randint(10, 999))
    email    = f"{name}@{random.choice(domains)}"
    password = fake_password()
    ref_code = rand_ref()
    date     = rand_date()

    try:
        cur.execute("""
            INSERT INTO users (username, email, password, balance, role, ref_code, is_active, created_at)
            VALUES (?, ?, ?, 0, 'user', ?, 1, ?)
        """, (name, email, password, ref_code, date))
    except:
        pass  # duplicate bo'lsa o'tkazib yuboradi

conn.commit()
conn.close()
print("150ta fake user qoshildi!")
