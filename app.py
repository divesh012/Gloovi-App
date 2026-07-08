import os
import sqlite3
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash, send_from_directory
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import razorpay
import urllib.parse
import requests
import hmac
import hashlib
import base64
import math
import time
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,
)
import os
import shutil
from datetime import datetime, date

import psycopg2
from psycopg2.extras import RealDictCursor
import razorpay
from dotenv import load_dotenv
from flask import Flask
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ----------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# ----------------------------------------------------
load_dotenv()

# ----------------------------------------------------
# FLASK APP
# ----------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv(
    "SECRET_KEY",
    "5e7f9b2c1d4a8f0e6c9b7a1d3e5f8c2b"
)

# ----------------------------------------------------
# ADMIN
# ----------------------------------------------------
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# ----------------------------------------------------
# RAZORPAY
# ----------------------------------------------------
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)
razorpay_client.set_app_details(
    {
        "title": "Gloora Salon Booking",
        "version": "1.0",
    }
)

# ----------------------------------------------------
# GEOAPIFY
# ----------------------------------------------------
GEOAPIFY_KEY = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"

# ----------------------------------------------------
# UPLOAD FOLDER
# ----------------------------------------------------
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXT = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
}

# ----------------------------------------------------
# SQLITE BACKUP PATH (KEEP IF YOU STILL USE BACKUPS)
# ----------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "database.db")

BACKUP_DIR = os.path.join(BASE_DIR, "backup")
os.makedirs(BACKUP_DIR, exist_ok=True)

# ----------------------------------------------------
# POSTGRESQL
# ----------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

print("DATABASE_URL =", DATABASE_URL)

def get_db_connection():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )

try:
    conn = get_db_connection()
    print("✅ PostgreSQL Connected")
    conn.close()
except Exception as e:
    print("❌ PostgreSQL Error:", e)
# -------------------- INIT DATABASE -------------------- #
def init_all_databases():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        print("🔧 Creating PostgreSQL tables...")

        # USERS
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users_data (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            mobile TEXT UNIQUE,
            password TEXT NOT NULL,
            gender TEXT NOT NULL
        );
        """)

        # SALONS
        cur.execute("""
        CREATE TABLE IF NOT EXISTS salons_data (
            id SERIAL PRIMARY KEY,
            salon_name TEXT NOT NULL,
            address TEXT,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            contact TEXT NOT NULL,
            status TEXT DEFAULT 'ON',
            owner_username TEXT,
            owner_id INTEGER,
            email TEXT,
            price DOUBLE PRECISION DEFAULT 0,
            pass_key TEXT NOT NULL,
            rating_total INTEGER DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            image TEXT,
            worker_count INTEGER DEFAULT 1
        );
        """)

        # SERVICES
        cur.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id SERIAL PRIMARY KEY,
            service_name TEXT UNIQUE NOT NULL
        );
        """)

        # SALON SERVICES
        cur.execute("""
        CREATE TABLE IF NOT EXISTS salon_services (
            id SERIAL PRIMARY KEY,
            salon_id INTEGER REFERENCES salons_data(id) ON DELETE CASCADE,
            service_id INTEGER REFERENCES services(id) ON DELETE CASCADE,
            price DOUBLE PRECISION
        );
        """)

        # SLOT REMINDERS
        cur.execute("""
        CREATE TABLE IF NOT EXISTS slot_reminders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            salon_id INTEGER NOT NULL,
            slot_datetime TEXT NOT NULL,
            reminder_time TEXT NOT NULL,
            sent INTEGER DEFAULT 0
        );
        """)

        # SLOT DATA
        cur.execute("""
        CREATE TABLE IF NOT EXISTS slot_data (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users_data(id) ON DELETE CASCADE,
            username TEXT,
            salon_id INTEGER REFERENCES salons_data(id) ON DELETE CASCADE,
            service_id INTEGER REFERENCES services(id) ON DELETE CASCADE,
            slot_date TEXT,
            slot_time TEXT,
            start_time TEXT,
            end_time TEXT,
            selected_services TEXT DEFAULT '',
            total_price DOUBLE PRECISION DEFAULT 0,
            payment_status TEXT DEFAULT 'pending'
        );
        """)

        conn.commit()

        print("✅ ALL POSTGRESQL TABLES CREATED SUCCESSFULLY")

    except Exception as e:
        print("❌ DATABASE INIT ERROR:", e)
        raise

    finally:
        cur.close()
        conn.close()


# -------------------------------------------------------
# CREATE TABLES WHEN APP STARTS
# -------------------------------------------------------
init_all_databases()

# -------------------- HELPERS -------------------- #
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def save_image(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    filename = f"{int(time.time())}_{filename}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file_storage.save(filepath)
    return f"uploads/{filename}"

def haversine(lat1, lon1, lat2, lon2):
    # distance in kilometers
    R = 6371.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# -------------------- STATIC PAGES -------------------- #
@app.route("/")
def home():
    return render_template("gender.html", username=session.get("username"))

@app.route("/gender")
def gender():
    return render_template("gender.html", username=session.get("username"))

@app.route("/about")
def about():
    return render_template("about.html", username=session.get("username"))

@app.route("/services_categories")
def services_categories():
    return render_template("services_categories.html", username=session.get("username"))

@app.route("/contact_us")
def contact_us():
    return render_template("contact_us.html", username=session.get("username"))

@app.route("/help")
def help_page():
    username = session.get("username")
    if not username:
        message = " Login Required"
        description = "Please sign in to access personalized help, order support, and chat assistance."
        return render_template("help.html", login_required=True, message=message, description=description, username=None)
    return render_template("help.html", username=username, login_required=False)

@app.route("/term")
def term():
    return render_template("term.html", username=session.get("username"))

@app.route("/cancellation")
def cancellation():
    return render_template("cancellation.html", username=session.get("username"))

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", username=session.get("username"))

# -------------------- AUTH (Login Page name normalized) -------------------- #
@app.route("/login", methods=["GET", "POST"])
def login_page():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        # ---------------- ADMIN LOGIN ----------------

        if username == ADMIN_USERNAME and email == ADMIN_EMAIL and password == ADMIN_PASSWORD:

            session.clear()
            session["admin"] = True

            flash("Admin Login Successful", "success")

            return redirect(url_for("admin_dashboard"))

        # ---------------- NORMAL USER LOGIN ----------------

        conn = get_db_connection()

        cur = conn.cursor()
        cur = conn.execute(
            """
            SELECT *
            FROM users_data
            WHERE username=%s AND email=%s
            """,
            (username, email)
        )
        user = cur.fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["username"] = user["username"]
            session["email"] = user["email"]
            session["user_id"] = user["id"]

            flash(
                f"Welcome back, {user['username']}!",
                "success"
            )

            return redirect(url_for("male"))

        flash("Invalid credentials!", "error")

        return redirect(url_for("male", login=1))

    return redirect(url_for("male", login=1))


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("gender"))

#-------------ADMIN DASHBOARD----------------------------#

@app.route('/admin/dashboard')
def admin_dashboard():

    if not session.get("admin"):
        return redirect(url_for("male", login=1))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM users_data"
    )
    users = cur.fetchall()


    cur.execute(
        "SELECT * FROM salons_data"
    )
    salons = cur.fetchall()


    cur.execute(
        "SELECT * FROM services"
    )
    services = cur.fetchall()


    cur.execute(
        "SELECT * FROM slot_data"
    )
    bookings = cur.fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        users=users,
        salons=salons,
        services=services,
        bookings=bookings
    )

@app.route("/admin-logout")
def admin_logout():

    session.clear()

    flash("Admin Logged Out", "success")

    return redirect(url_for("gender"))
#-----------------DELETE USER-----------------------------------#

@app.route('/admin/delete_user/<int:id>')
def delete_user(id):

    conn = get_db_connection()

    cur = conn.cursor()

    cur.execute(
        "DELETE FROM users_data WHERE id=%s",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_salon/<int:id>')
def delete_salon(id):

    conn = get_db_connection()

    cur = conn.cursor()

    cur.execute(
        "DELETE FROM salons_data WHERE id=%s",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete_service/<int:id>')
def delete_service(id):

    conn = get_db_connection()

    cur = conn.cursor

    cur.execute(
        "DELETE FROM services WHERE id=%s",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_booking/<int:id>')
def delete_booking(id):

    conn = get_db_connection()

    cur = conn.cursor()

    conn.execute(
        "DELETE FROM slot_data WHERE id=%s",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))


# -------------------- COMMON AUTH HANDLER -------------------- #
def handle_auth(action, gender_page):
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    mobile = request.form.get("mobile", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not email or not password:
        flash("All fields are mandatory!", "error")
        return redirect(url_for(gender_page))

    if not email.lower().endswith("@gmail.com"):
        flash("Please enter a valid Gmail address.", "error")
        return redirect(url_for(gender_page))

    conn = get_db_connection()
    cur = conn.cursor()

    # ---------------- REGISTER ----------------
    if action == "register":

        hashed_pw = generate_password_hash(password)
        gender = gender_page

        try:
            cur.execute("""
                INSERT INTO users_data
                (username, email, mobile, password, gender)
                VALUES (%s, %s, %s, %s, %s)
            """, (username, email, mobile, hashed_pw, gender))

            conn.commit()

            flash(
                "Registration successful! Please login.",
                "success"
            )
            from psycopg2 import IntegrityError
        except IntegrityError:
            flash(
                "Username, Email, or Mobile already exists!",
                "error"
            )

        conn.close()
        return redirect(url_for(gender_page))

    # ---------------- LOGIN ----------------
    elif action == "login":

        # ADMIN LOGIN
        if (
            username == ADMIN_USERNAME
            and email == ADMIN_EMAIL
            and password == ADMIN_PASSWORD
        ):

            session.clear()
            session["admin"] = True

            flash("Admin Login Successful", "success")

            conn.close()

            return redirect(url_for("admin_dashboard"))

        # NORMAL USER LOGIN
        cur.execute(
            """
            SELECT *
            FROM users_data
            WHERE username=%s AND email=%s
            """,
            (username, email)
        )

        user = cur.fetchone()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["username"] = user["username"]
            session["email"] = user["email"]
            session["user_id"] = user["id"]

            flash(
                f"Welcome back, {user['username']}!",
                "success"
            )

            conn.close()

            return redirect(url_for("male"))

        flash("Invalid credentials!", "error")

    conn.close()

    return redirect(url_for(gender_page))

# -------------------- MALE / FEMALE PAGES -------------------- #
@app.route("/male", methods=["GET", "POST"])
def male():
    show_login = request.args.get("login") == "1"

    if request.method == "POST":
        return handle_auth(request.form.get("action"), "male")

    return render_template(
        "male_page.html",
        show_login=show_login,
        username=session.get("username")
    )


@app.route("/female", methods=["GET", "POST"])
def female():
    show_login = request.args.get("login") == "1"

    if request.method == "POST":
        return handle_auth(request.form.get("action"), "female")

    return render_template(
        "female_page.html",
        show_login=show_login,
        username=session.get("username")
    )

# ------------------ FORGOT PASSWORD MALE ------------------ #
@app.route("/forgot_password_male", methods=["GET", "POST"])
def forgot_password_male():
    if request.method == "POST":
        mobile = request.form.get("mobile")

        conn = get_db_connection()
        cur = conn.cursor()
        cur = conn.execute(
            "SELECT * FROM users_data WHERE mobile=%s AND gender='male'",
            (mobile,)
        )
        user = cur.fetchone()
        conn.close()

        if not user:
            flash("Mobile not found!", "error")
            return redirect(url_for("forgot_password_male"))

        # Secure OTP
        otp = str(random.randint(100000, 999999))
        session["reset_mobile"] = mobile
        session["reset_otp"] = otp

        result = send_sms(mobile, f"Your OTP for password reset is {otp}")

        if result and result.get("return") is True:
            flash("OTP sent to your registered mobile!", "success")
        else:
            print("❌ SMS FAILED:", result)
            flash(f"SMS failed. OTP (test): {otp}", "warning")

        return redirect(url_for("verify_otp"))

    return render_template("forgot_password_male.html")


# ------------------ FORGOT PASSWORD FEMALE ------------------ #
@app.route("/forgot_password_female", methods=["GET", "POST"])
def forgot_password_female():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()

        if not mobile:
            flash("Please enter mobile number!", "error")
            return redirect(url_for("forgot_password_female"))

        conn = get_db_connection()
        cur = conn.cursor()
        cur = conn.execute(
            "SELECT id FROM users_data WHERE mobile=%s AND gender='female'",
            (mobile,)
        )
        user = cur.fetchone()
        conn.close()

        if not user:
            flash("Mobile number not registered!", "error")
            return redirect(url_for("forgot_password_female"))

        otp = str(random.randint(100000, 999999))
        session["reset_mobile"] = mobile
        session["reset_otp"] = otp
        session["otp_time"] = time.time()
        session["otp_attempts"] = 0

        res = send_sms(mobile, f"Your OTP for password reset is {otp}. Valid for 5 minutes.")

        if res and res.get("return") is True:
            flash("OTP sent to your registered mobile number.", "success")
            return redirect(url_for("verify_otp"))
        else:
            flash("Failed to send OTP. Please try again later.", "error")
            return redirect(url_for("forgot_password_female"))

    return render_template("forgot_password_female.html")
# ------------------ VERIFY OTP ------------------ #
@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()

        if entered_otp == session.get("reset_otp"):
            flash("OTP verified successfully ✅", "success")
            return redirect(url_for("reset_password"))
        else:
            flash("Invalid OTP ❌", "error")
            return redirect(url_for("verify_otp"))

    return render_template("verify_otp.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if not session.get("otp_verified"):
        flash("OTP verification required!", "error")
        return redirect(url_for("forgot_password_male"))

    if request.method == "POST":
        new_password = request.form.get("password")
        mobile = session.get("reset_mobile")

        if not mobile:
            flash("Session expired. Try again.", "error")
            return redirect(url_for("forgot_password_male"))

        hashed = generate_password_hash(new_password)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users_data SET password=%s WHERE mobile=%s",
            (hashed, mobile)
        )
        conn.commit()
        conn.close()

        # ✅ Clear only reset-related session data
        session.pop("reset_mobile", None)
        session.pop("reset_otp", None)
        session.pop("otp_verified", None)

        # ✅ IMPORTANT FIX
        flash("Password updated successfully! Please login.", "success")
        return redirect(url_for("male", login=1))  # 👈 this works

    return render_template("reset_password.html")



# -------------------- SERVE UPLOADS -------------------- #
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)
# -------------------- REGISTER SALON -------------------- #
@app.route("/register_salon", methods=["GET", "POST"])
def register_salon():
    if request.method == "POST":

        salon_name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        contact = request.form.get("contact", "").strip()
        pass_key = request.form.get("pass_key", "").strip()

        try:
            worker_count = int(request.form.get("worker_count", 1))
            if worker_count < 1:
                worker_count = 1
        except ValueError:
            worker_count = 1

        image_file = request.files.get("image")

        # SERVICES
        service_names = request.form.getlist("service_name[]")
        service_prices = request.form.getlist("service_price[]")

        valid_services = []

        for s_name, s_price in zip(service_names, service_prices):
            s_name = s_name.strip()
            s_price = s_price.strip()

            if not s_name or not s_price:
                continue

            try:
                price_val = float(s_price)
            except ValueError:
                continue

            valid_services.append((s_name, price_val))

        # VALIDATION
        if not all([salon_name, city, state, contact, pass_key]):
            flash("All fields marked with * are mandatory!", "error")
            return render_template("register_salon.html")

        if not valid_services:
            flash("Please add at least one valid service with price!", "error")
            return render_template("register_salon.html")

        hashed_pass_key = generate_password_hash(pass_key)
        image_path = save_image(image_file)

        with get_db_connection() as conn:
            cur = conn.cursor()

            # INSERT SALON
            cur.execute("""
                INSERT INTO salons_data
                (salon_name, owner_username, owner_id, email, contact,
                 address, city, state, image, pass_key, worker_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                salon_name,
                session.get("username", ""),
                session.get("user_id", ""),
                session.get("email", ""),
                contact,
                address,
                city,
                state,
                image_path,
                hashed_pass_key,
                worker_count
            ))

            salon_id = cur.fetchone()["id"]

            # INSERT SERVICES
            for s_name, price_val in valid_services:

                cur.execute(
                    "SELECT id FROM services WHERE service_name=%s",
                    (s_name,)
                )
                service = cur.fetchone()

                if service:
                    service_id = service["id"]
                else:
                    cur.execute("""
                        INSERT INTO services (service_name)
                        VALUES (%s)
                        RETURNING id
                    """, (s_name,))

                    service_id = cur.fetchone()["id"]

                # MAP TABLE
                cur.execute("""
                    INSERT INTO salon_services (salon_id, service_id, price)
                    VALUES (%s, %s, %s)
                """, (salon_id, service_id, price_val))

            conn.commit()

        flash("Salon registered successfully!", "success")
        return redirect(url_for("show_salons"))

    return render_template("register_salon.html")

# -------------------- SHOW SALONS -------------------- #

def get_salon_services(conn, salon_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            s.id AS service_id,
            s.service_name,
            ss.price
        FROM salon_services ss
        JOIN services s ON ss.service_id = s.id
        WHERE ss.salon_id = %s
    """, (salon_id,))

    rows = cur.fetchall()

    services = []
    for r in rows:
        services.append({
            "id": r["service_id"],
            "name": r["service_name"],
            "price": r["price"]
        })

    return services


@app.route("/salons")
def show_salons():

    search = request.args.get("search", "").strip().lower()

    with get_db_connection() as conn:
        cur = conn.cursor()

        if search:
            cur.execute("""
                SELECT * FROM salons_data
                WHERE LOWER(salon_name) LIKE %s
                OR LOWER(address) LIKE %s
            """, (f"%{search}%", f"%{search}%"))
        else:
            cur.execute("SELECT * FROM salons_data")

        salons = cur.fetchall()

    salon_list = []

    with get_db_connection() as conn:
        for s in salons:
            d = dict(s)

            d["services"] = get_salon_services(conn, s["id"]) or []

            d["avg_rating"] = (
                round(s["rating_total"] / s["rating_count"], 1)
                if s["rating_count"] else 0
            )

            d["image"] = s["image"]   # FIXED

            salon_list.append(d)

    return render_template(
        "show_salon.html",
        salons=salon_list,
        username=session.get("username"),
        user_id=session.get("user_id"),
        search=search
    )


# -------------------- RECOMMEND (accepts lat & lon and shows nearest first) -------------------- #
@app.route("/recommend", methods=["GET"])
def recommend():

    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    category = request.args.get("category", default=None, type=str)

    if lat is None or lon is None:
        flash("Location not provided.", "error")
        return redirect(url_for("show_salons"))

    with get_db_connection() as conn:
        cur = conn.cursor()

        if category:
            cur.execute("""
                SELECT * FROM salons_data
                WHERE LOWER(salon_name) LIKE %s
            """, (f"%{category.lower()}%",))
        else:
            cur.execute("SELECT * FROM salons_data")

        salons = cur.fetchall()

    salons_list = []

    for s in salons:
        d = dict(s)
        d["image"] = s["image"]   # FIXED

        try:
            d["distance_km"] = round(
                haversine(lat, lon, s["lat"], s["lng"]), 2
            ) if s["lat"] and s["lng"] else None
        except:
            d["distance_km"] = None

        salons_list.append(d)

    salons_list.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"]))

    return render_template("show_salon.html", salons=salons_list)
# -------------------- RATE SALON -------------------- #
@app.route("/rate/<int:salon_id>", methods=["POST"])
def rate_salon(salon_id):
    try:
        rating = int(request.form.get("rating", 0))
    except Exception:
        rating = 0

    if rating < 1 or rating > 5:
        flash("Invalid rating value!", "error")
        return redirect(url_for("show_salons"))

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT rating_total, rating_count FROM salons_data WHERE id=%s", (salon_id,))
        salon = cur.fetchone()
        if not salon:
            flash("Salon not found!", "error")
            return redirect(url_for("show_salons"))
        new_total = salon["rating_total"] + rating
        new_count = salon["rating_count"] + 1
        cur.execute("UPDATE salons_data SET rating_total=%s, rating_count=%s WHERE id=%s", (new_total, new_count, salon_id))
        conn.commit()

    flash("Thank you for rating!", "success")
    return redirect(url_for("show_salons"))
# -------------------- SALON TOGGLE -------------------- #
@app.route("/toggle_verify/<int:salon_id>", methods=["POST"])
def toggle_verify(salon_id):

    entered_key = request.form.get("pass_key")

    if not entered_key:
        flash("Please enter the passkey.", "error")
        return redirect(url_for("show_salons"))

    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT pass_key, status FROM salons_data WHERE id=%s",
            (salon_id,)
        )

        salon = cur.fetchone()

        if not salon:
            flash("Salon not found!", "error")
            return redirect(url_for("show_salons"))

        if not check_password_hash(salon["pass_key"], entered_key):
            flash("Wrong Passkey!", "error")
            return redirect(url_for("show_salons"))

        new_status = "OFF" if salon["status"] == "ON" else "ON"

        cur.execute(
            "UPDATE salons_data SET status=%s WHERE id=%s",
            (new_status, salon_id)
        )

        conn.commit()

    flash(f"Salon turned {new_status}", "success")
    return redirect(url_for("show_salons"))


# -------------------- WORKER PAGE -------------------- #
@app.route("/salon/<int:salon_id>/workers")
def worker_toggle_page(salon_id):
    if "username" not in session:
        flash("Login required", "error")
        return redirect(url_for("login_page"))

    # Passkey verification
    if session.get("verified_worker_salon_id") != salon_id:
        flash("Passkey verification required", "error")
        return redirect(url_for("verify_worker_page_get", salon_id=salon_id))

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Get salon details
        cur.execute(
            "SELECT * FROM salons_data WHERE id=%s",
            (salon_id,)
        )
        salon = cur.fetchone()

        if not salon:
            flash("Salon not found!", "error")
            return redirect(url_for("show_salons"))

        # Get all pending bookings for this salon
        cur.execute("""
            SELECT *
            FROM slot_data
            WHERE salon_id=%s
              AND payment_status='paid'
              AND booking_status='Pending'
            ORDER BY slot_date, slot_time
        """, (salon_id,))

        pending_bookings = cur.fetchall()

    # Generate workers list
    workers = [
        {
            "id": i + 1,
            "status": "ON" if i < salon["worker_count"] else "OFF"
        }
        for i in range(salon["worker_count"])
    ]

    return render_template(
        "worker_toggle.html",
        salon=salon,
        workers=workers,
        pending_bookings=pending_bookings
    )


@app.route("/accept_booking/<int:slot_id>", methods=["POST"])
def accept_booking(slot_id):

    if "username" not in session:
        flash("Login required", "error")
        return redirect(url_for("login_page"))

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Get booking details
        cur.execute("""
            SELECT salon_id, slot_date, slot_time
            FROM slot_data
            WHERE id=%s
        """, (slot_id,))

        booking = cur.fetchone()

        if not booking:
            flash("Booking not found.", "error")
            return redirect(request.referrer)

        salon_id = booking["salon_id"]
        slot_date = booking["slot_date"]
        slot_time = booking["slot_time"]

        # Get available workers
        cur.execute("""
            SELECT worker_count
            FROM salons_data
            WHERE id=%s
        """, (salon_id,))

        salon = cur.fetchone()

        worker_count = salon["worker_count"]

        # Count confirmed bookings for the SAME date & time
        cur.execute("""
            SELECT COUNT(*) AS total
            FROM slot_data
            WHERE salon_id=%s
              AND slot_date=%s
              AND slot_time=%s
              AND booking_status='Confirmed'
        """, (salon_id, slot_date, slot_time))

        confirmed = cur.fetchone()["total"]

        # Check availability
        if confirmed >= worker_count:
            flash("No workers available for this slot.", "error")
            return redirect(request.referrer)

        # Confirm booking
        cur.execute("""
            UPDATE slot_data
            SET booking_status='Confirmed'
            WHERE id=%s
        """, (slot_id,))

        conn.commit()

    flash("Booking confirmed successfully!", "success")
    return redirect(request.referrer)

@app.route("/reject_booking/<int:slot_id>", methods=["POST"])
def reject_booking(slot_id):

    if "username" not in session:
        flash("Login required", "error")
        return redirect(url_for("login_page"))

    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            UPDATE slot_data
            SET booking_status='Rejected'
            WHERE id=%s
        """, (slot_id,))

        conn.commit()

    flash("Booking rejected!", "success")

    return redirect(request.referrer)

# check 6
# -------------------- WORKER PASSKEY VERIFICATION PAGE (GET) -------------------- #
@app.route("/verify_worker_page/<int:salon_id>")
def verify_worker_page_get(salon_id):
    """
    Render passkey entry page for workers.
    GET only, just shows the form.
    """
    return render_template("verify_worker_passkey.html", salon_id=salon_id)


# -------------------- WORKER PASSKEY SUBMIT (POST) -------------------- #
@app.route("/verify_worker_access/<int:salon_id>", methods=["POST"])
def verify_worker_access_post(salon_id):
    if session.get("verified_worker_salon_id") == salon_id:
        return redirect(url_for("worker_toggle_page", salon_id=salon_id))

    entered_key = request.form.get("pass_key")
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("SELECT pass_key FROM salons_data WHERE id=%s",
                             (salon_id,))
        salon = cur.fetchone()

    if not salon or not check_password_hash(salon["pass_key"], entered_key):
        flash("Wrong Passkey!", "error")
        return redirect(url_for("show_salons"))

    session["verified_worker_salon_id"] = salon_id
    return redirect(url_for("worker_toggle_page", salon_id=salon_id))


# -------------------- VERIFY WORKER ACCESS PAGE -------------------- #
@app.route("/verify_worker/<int:salon_id>", methods=["GET", "POST"])
def verify_worker_page(salon_id):
    if request.method == "POST":
        entered_key = request.form.get("pass_key")
        with get_db_connection() as conn:
            cur = conn.cursor()

            cur.execute(
                "SELECT pass_key FROM salons_data WHERE id=%s",
                (salon_id,)
            )
            salon = cur.fetchone()

        if salon and check_password_hash(salon["pass_key"], entered_key):
            session["verified_salon_id"] = salon_id
            flash("Passkey verified!", "success")
            return redirect(url_for("worker_toggle_page", salon_id=salon_id))
        else:
            flash("Wrong Passkey!", "error")
            return redirect(url_for("verify_worker_page", salon_id=salon_id))

    return render_template("verify_worker.html", salon_id=salon_id)

# -------------------- UPDATE WORKER COUNT -------------------- #
@app.route("/update_worker_count/<int:salon_id>", methods=["POST"])
def update_worker_count(salon_id):
    if "username" not in session:
        flash("Login required", "error")
        return redirect(url_for("login_page"))

    worker_count = request.form.get("worker_count", "1")
    try:
        worker_count = int(worker_count)
    except ValueError:
        worker_count = 1

    if worker_count < 1:
        flash("Worker count must be at least 1", "error")
        return redirect(url_for("worker_toggle_page", salon_id=salon_id))

    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            "UPDATE salons_data SET worker_count=%s WHERE id=%s",
            (worker_count, salon_id)
        )
        conn.commit()

    flash(f"Worker count updated to {worker_count}", "success")
    return redirect(url_for("worker_toggle_page", salon_id=salon_id))

from datetime import datetime, timedelta
from flask import request, session, redirect, url_for, flash, render_template


from datetime import datetime, timedelta

# -------------------- SLOT HELPERS -------------------- #

def generate_required_slots(start_time, service_count):

    start_dt = datetime.strptime(start_time, "%H:%M")

    slots = []

    for i in range(service_count):
        slot = (
            start_dt + timedelta(minutes=i * 30)
        ).strftime("%H:%M")

        slots.append(slot)

    return slots

#--------------Book SLot ---------------------#

@app.route("/book-slot/<int:salon_id>", methods=["GET", "POST"])
def book_slot_for_salon(salon_id):

    # ---------- AUTH CHECK ----------
    if "username" not in session or "user_id" not in session:
        flash("Please login first to book a slot!", "error")
        return redirect(url_for("login_page"))

    # ---------- FETCH SALON & SERVICES ----------
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM salons_data WHERE id=%s",
            (salon_id,)
        )
        salon = cur.fetchone()

        services = get_salon_services(conn, salon_id)

    if not salon:
        flash("Salon not found!", "error")
        return redirect(url_for("show_salons"))

    # ---------- POST ----------
    if request.method == "POST":

        slot_date = request.form.get("slot_date")
        slot_time = request.form.get("slot_time")
        selected_services = request.form.getlist("selected_services[]")

        total_price = request.form.get("total_price", "0")

        try:
            total_price = float(total_price)
        except ValueError:
            total_price = 0

        # ---------- VALIDATION ----------
        if (
            not slot_date or
            not slot_time or
            not selected_services or
            total_price <= 0
        ):
            flash("Please select date, time and at least one service!", "error")
            return redirect(url_for("book_slot_for_salon", salon_id=salon_id))

        # ---------- PARSE DATETIME ----------
        try:
            selected_start = datetime.strptime(
                f"{slot_date} {slot_time}",
                "%Y-%m-%d %H:%M"
            )
        except ValueError:
            flash("Invalid date or time!", "error")
            return redirect(url_for("book_slot_for_salon", salon_id=salon_id))

        # ---------- PREVENT PAST BOOKINGS ----------
        if selected_start < datetime.now():
            flash("You cannot book past time slots!", "error")
            return redirect(url_for("book_slot_for_salon", salon_id=salon_id))

        # ---------- SLOT CALCULATION ----------
        service_count = len(selected_services)

        required_slots = generate_required_slots(
            slot_time,
            service_count
        )

        start_time = required_slots[0]

        end_dt = (
            datetime.strptime(start_time, "%H:%M")
            + timedelta(minutes=30)
        )

        end_time = end_dt.strftime("%H:%M")

        # ---------- CHECK SALON CLOSING TIME ----------
        if end_time > "22:00":
            flash("Selected services exceed salon closing time (10:00 PM).", "error")
            return redirect(url_for("book_slot_for_salon", salon_id=salon_id))

        # ---------- CHECK SLOT AVAILABILITY ----------
        with get_db_connection() as conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT slot_time
                FROM slot_data
                WHERE salon_id = %s
                AND slot_date = %s
                AND payment_status = 'paid'
            """, (salon_id, slot_date))

            rows = cur.fetchall()

        booked_count = {}

        for r in rows:
            if not r["slot_time"]:
                continue

            for slot in r["slot_time"].split(","):
                booked_count[slot] = booked_count.get(slot, 0) + 1

        worker_count = max(int(salon["worker_count"] or 1), 1)

        for slot in required_slots:
            if booked_count.get(slot, 0) >= worker_count:
                flash(f"Time slot {slot} is unavailable.", "error")
                return redirect(url_for("book_slot_for_salon", salon_id=salon_id))

        # ---------- SAVE TEMP BOOKING ----------
        session["pending_booking"] = {
            "salon_id": salon_id,
            "slot_date": slot_date,
            "slot_time": ",".join(required_slots),
            "start_time": start_time,
            "end_time": end_time,
            "selected_services": selected_services,
            "service_total": total_price,
            "platform_fee": service_count * 10
        }

        return redirect(url_for("payment", salon_id=salon_id))

    # ---------- GET ----------
    return render_template(
        "book_slot.html",
        salon=salon,
        services=services,
        username=session.get("username", ""),
        current_datetime=datetime
    )

@app.route("/get-booked-slots/<int:salon_id>/<slot_date>")
def get_booked_slots(salon_id, slot_date):

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT worker_count
            FROM salons_data
            WHERE id = %s
        """, (salon_id,))
        salon = cur.fetchone()


        worker_count = max(
            int(salon["worker_count"] or 1),
            1
        )

        cur.execute("""
            SELECT slot_time
            FROM slot_data
            WHERE salon_id = %s
            AND slot_date = %s
            AND payment_status = 'paid'
        """, (
            salon_id,
            slot_date
        ))
        rows = cur.fetchall()


    booked_slots = {}

    for row in rows:

        if not row["slot_time"]:
            continue

        for slot in row["slot_time"].split(","):
            booked_slots[slot] = (
                booked_slots.get(slot, 0) + 1
            )

    return jsonify({
        "bookedSlots": booked_slots,
        "workerCount": worker_count
    })
#----------------Payment--------------------#

@app.route("/payment/<int:salon_id>")
def payment(salon_id):

    print("PAYMENT ROUTE HIT")
    print("SESSION:", dict(session))

    if "username" not in session or "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login_page"))

    booking = session.get("pending_booking")

    print("PENDING BOOKING:", booking)

    if not booking:
        flash("No pending booking found!", "error")
        return redirect(url_for("show_salons"))

    service_count = len(booking["selected_services"])

    platform_fee = float(booking.get("platform_fee", 0))
    service_total = float(booking.get("service_total", 0))

    try:
        order = razorpay_client.order.create({
            "amount": int(platform_fee * 100),
            "currency": "INR",
            "payment_capture": 1
        })

        print("RAZORPAY ORDER CREATED:", order["id"])

    except Exception as e:
        print("Razorpay Order Error:", e)
        flash("Unable to create payment order.", "error")
        return redirect(url_for("show_salons"))

    return render_template(
        "payment.html",
        username=session["username"],
        slot_date=booking["slot_date"],
        start_time=booking["start_time"],
        end_time=booking["end_time"],
        service_total=service_total,
        platform_fee=platform_fee,
        service_count=service_count,
        razorpay_key=RAZORPAY_KEY_ID,
        razorpay_order=order
    )
# -------------------- PAYMENT SUCCESS HANDLER -------------------- #
@app.route("/payment-success", methods=["POST"])
def payment_success():

    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login_page"))

    payment_id = request.form.get("razorpay_payment_id")
    order_id = request.form.get("razorpay_order_id")
    signature = request.form.get("razorpay_signature")

    if not payment_id or not order_id or not signature:
        flash("Payment failed!", "error")
        return redirect(url_for("show_salons"))

    # ---------- VERIFY ----------
    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature
        })
    except Exception as e:
        print("Payment verification failed:", e)
        flash("Payment verification failed!", "error")
        return redirect(url_for("show_salons"))

    booking = session.get("pending_booking")

    if not booking:
        flash("Booking session expired!", "error")
        return redirect(url_for("show_salons"))

    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            # ---------- INSERT BOOKING (THIS WAS MISSING) ----------
       
            cur.execute("""

                INSERT INTO slot_data (
                    user_id,
                    username,
                    salon_id,
                    slot_date,
                    slot_time,
                    start_time,
                    end_time,
                    selected_services,
                    total_price,
                    payment_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

                    payment_status,
                        booking_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s)
            """, (
                session["user_id"],
                session["username"],
                booking["salon_id"],
                booking["slot_date"],
                booking["slot_time"],
                booking["start_time"],
                booking["end_time"],
                ",".join(booking["selected_services"]),
                booking["service_total"],
                "paid"
                "paid",
                "Pending"
            ))

            conn.commit()

        # clear session
        session.pop("pending_booking", None)

        flash("Payment successful! Slot booked.", "success")

    except Exception as e:
        print("DB ERROR:", e)
        flash("Something went wrong after payment!", "error")

    return redirect(url_for("show_salons"))

# -------------------- ADMIN DATABASE VIEW -------------------- #
# @app.route("/database_views")
# def database_views():
#     if not session.get("admin"):
#         flash("Admin access only!", "error")
#         return redirect(url_for("gender"))

#     with get_db_connection() as conn:
#         users = conn.execute("SELECT * FROM users_data").fetchall()
#         salons = conn.execute("SELECT * FROM salons_data").fetchall()
#         slots = conn.execute("SELECT * FROM slot_data").fetchall()

#     return render_template(
#         "database_views.html",
#         users=users,
#         salons=salons,
#         slots=slots,
#         username=session.get("username")
#     )
# -------------------- RUN APP -------------------- #
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
