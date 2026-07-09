import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("UPDATE salons_data SET status='OFF'")
conn.commit()

cur.close()
conn.close()

print("All salons reset to OFF.")