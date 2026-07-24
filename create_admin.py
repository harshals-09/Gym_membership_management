# create_admin.py
import pymysql
from werkzeug.security import generate_password_hash

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Vibhaganesh2522$',
    'database': 'gym_management',
    'cursorclass': pymysql.cursors.DictCursor
}

username = "admin"      # change as needed
password = "AdminPassword!"  # change as needed
fullname = "Gym Admin"

conn = pymysql.connect(**DB_CONFIG)
cur = conn.cursor()
pw_hash = generate_password_hash(password)
cur.execute("INSERT INTO Admin (Username, PasswordHash, FullName) VALUES (%s, %s, %s)",
            (username, pw_hash, fullname))
conn.commit()
conn.close()
print("Admin user created:", username)
