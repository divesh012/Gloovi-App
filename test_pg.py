import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="salon_booking_db",
    user="postgres",
    password="Divesh@123",
    port="5432"
)

print("Connected Successfully!")

conn.close()