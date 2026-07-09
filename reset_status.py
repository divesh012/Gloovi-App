import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()   # Load variables from .env

DATABASE_URL = os.getenv("DATABASE_URL")

print(DATABASE_URL)   # Temporary: check if it's loaded

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("UPDATE salons_data SET status='OFF'")
conn.commit()

cur.close()
conn.close()

print("All salon statuses reset to OFF.")