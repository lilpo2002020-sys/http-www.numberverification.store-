from flask import Flask, render_template, request, redirect, session, Response, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- DATABASE ----------------
def get_db():
    return sqlite3.connect("data.db")

def init_db():
    db = get_db()
    c = db.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        joined TEXT,
        status TEXT,
        approved_at TEXT
    )
    """)

    try:
        c.execute("ALTER TABLE users ADD COLUMN approved_at TEXT")
    except:
        pass

    c.execute("""
    CREATE TABLE IF NOT EXISTS numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT,
        username TEXT,
        time TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT,
        time TEXT
    )
    """)

    c.execute("INSERT OR IGNORE INTO admins (id, username, password, role) VALUES (1, 'admin', 'admin123', 'super')")

    db.commit()
    db.close()

init_db()

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form["username"]
        pw = request.form["password"]

        db = get_db()
        c = db.cursor()
        admin = c.execute("SELECT * FROM admins WHERE username=? AND password=?", (user, pw)).fetchone()
        db.close()

        if admin:
            session["admin"] = user
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="Invalid login")

    return render_template("login.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "admin" not in session:
        return redirect("/")
    db = get_db()
    c = db.cursor()

    # USERS
    c.execute("SELECT * FROM users")
    users = c.fetchall()

    # NUMBERS
    c.execute("SELECT * FROM numbers")
    numbers = c.fetchall()

    # BASIC STATS
    total = len(users)
    approved = len([u for u in users if u[3] == "approved"])
    pending = len([u for u in users if u[3] == "pending"])
    banned = len([u for u in users if u[3] == "banned"])

    # ✅ NEW: ACTIVE USERS (users who verified numbers)
    active_users = len(set([n[2] for n in numbers]))

    # ✅ NEW: GROWTH RATE (simple logic)
    if total > 0:
        growth = round((approved / total) * 100, 1)
    else:
        growth = 0

    return render_template(
        "dashboard.html",
        users=users,
        numbers=numbers,
        total=total,
        approved=approved,
        pending=pending,
        banned=banned,
        active_users=active_users,
        growth=growth
    )

# ---------------- PENDING USERS ----------------
@app.route("/pending-users")
def pending_users():
    if "admin" not in session:
        return redirect("/")

    db = get_db()
    c = db.cursor()
    users = c.execute("SELECT * FROM users WHERE status='pending'").fetchall()
    db.close()

    return render_template("pending_users.html", users=users)

@app.route("/numbers")
def numbers_page():
    db = get_db()
    c = db.cursor()

    c.execute("SELECT number, username, time FROM numbers")
    rows = c.fetchall()

    db.close()

    from datetime import datetime, timedelta

    now = datetime.now()

    daily = []
    weekly = []
    monthly = []

    for n in rows:
        try:
            record_time = datetime.strptime(n[2], "%Y-%m-%d %H:%M:%S")
        except:
            continue

        # DAILY (today only)
        if record_time.date() == now.date():
            daily.append(n)

        # WEEKLY (last 7 days)
        if record_time >= now - timedelta(days=7):
            weekly.append(n)

        # MONTHLY (last 30 days)
        if record_time >= now - timedelta(days=30):
            monthly.append(n)

    return render_template(
        "numbers.html",
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        daily_labels=["Day 1", "Day 2"],
        daily_values=[5, 10],
        weekly_labels=["Week 1", "Week 2"],
        weekly_values=[20, 40],
        growth=20,
        trend="Up"
    )

# ---------------- ALL USERS ----------------
@app.route("/users")
def users_page():
    if "admin" not in session:
        return redirect("/")

    db = get_db()
    c = db.cursor()

    users = c.execute("SELECT * FROM users").fetchall()

    db.close()

    return render_template("users.html", users=users)

# ---------------- ACTIONS ----------------
@app.route("/approve/<int:user_id>")
def approve(user_id):
    db = get_db()
    c = db.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute(
        "UPDATE users SET status='approved', approved_at=? WHERE user_id=?",
        (now, user_id)
    )

    c.execute(
        "INSERT INTO logs (action,time) VALUES (?,?)",
        (f"Approved {user_id}", now)
    )

    db.commit()
    db.close()

    return redirect("/dashboard")

@app.route("/reject/<int:user_id>")
def reject(user_id):
    db = get_db()
    c = db.cursor()

    c.execute("UPDATE users SET status='rejected' WHERE user_id=?", (user_id,))
    c.execute("INSERT INTO logs (action,time) VALUES (?,?)", (f"Rejected {user_id}", datetime.now()))

    db.commit()
    db.close()

    return redirect("/pending-users")

@app.route("/ban/<int:user_id>")
def ban(user_id):
    db = get_db()
    c = db.cursor()

    c.execute("UPDATE users SET status='banned' WHERE user_id=?", (user_id,))
    c.execute("INSERT INTO logs (action,time) VALUES (?,?)", (f"Banned {user_id}", datetime.now()))

    db.commit()
    db.close()

    return redirect("/dashboard")

# ---------------- API ----------------
@app.route("/api/stats")
def stats():
    db = get_db()
    c = db.cursor()

    total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    approved = c.execute("SELECT COUNT(*) FROM users WHERE status='approved'").fetchone()[0]
    pending = c.execute("SELECT COUNT(*) FROM users WHERE status='pending'").fetchone()[0]
    banned = c.execute("SELECT COUNT(*) FROM users WHERE status='banned'").fetchone()[0]

    db.close()

    return jsonify({
        "total": total,
        "approved": approved,
        "pending": pending,
        "banned": banned
    })

# ---------------- WHITELIST ----------------
@app.route("/whitelist")
def whitelist():
    if "admin" not in session:
        return redirect("/")

    db = get_db()
    c = db.cursor()
    users = c.execute("SELECT * FROM users WHERE status='approved'").fetchall()
    db.close()

    return render_template("whitelist.html", users=users)

# ---------------- SETTINGS ----------------
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "admin" not in session:
        return redirect("/")

    db = get_db()
    c = db.cursor()

    message = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")

        if username and password:
            try:
                c.execute(
                    "INSERT INTO admins (username, password, role) VALUES (?, ?, ?)",
                    (username, password, role)
                )
                db.commit()
                message = "✅ Admin added successfully"
            except:
                message = "❌ Username already exists"

    admins = c.execute("SELECT username, role FROM admins").fetchall()
    logs = c.execute("SELECT action, time FROM logs ORDER BY id DESC LIMIT 10").fetchall()

    db.close()

    return render_template("settings.html", admins=admins, logs=logs, message=message)

# ✅ STEP 2 ADDED HERE
@app.route("/clear-logs")
def clear_logs():
    if "admin" not in session:
        return redirect("/")

    db = get_db()
    c = db.cursor()

    c.execute("DELETE FROM logs")

    db.commit()
    db.close()

    return redirect("/settings")

# ---------------- EXPORT ----------------
@app.route("/export")
def export():
    db = get_db()
    c = db.cursor()
    users = c.execute("SELECT * FROM users").fetchall()
    db.close()

    def generate():
        yield "ID,Username,Status\n"
        for u in users:
            yield f"{u[0]},{u[1]},{u[3]}\n"

    return Response(generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=users.csv"}
    )

# ---------------- CHANGE PASSWORD ----------------
@app.route("/change-password", methods=["GET", "POST"])
def change_password():
    if "admin" not in session:
        return redirect("/")

    error = None
    success = None

    if request.method == "POST":
        old = request.form["old"]
        new = request.form["new"]
        confirm = request.form["confirm"]

        db = get_db()
        c = db.cursor()

        admin = c.execute(
            "SELECT * FROM admins WHERE username=? AND password=?",
            (session["admin"], old)
        ).fetchone()

        if not admin:
            error = "Old password is incorrect"
        elif new != confirm:
            error = "Passwords do not match"
        else:
            c.execute(
                "UPDATE admins SET password=? WHERE username=?",
                (new, session["admin"])
            )
            db.commit()
            success = "Password updated successfully"

        db.close()

    return render_template("change_password.html", error=error, success=success)

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- RUN ----------------
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "WORKING ✅"

if __name__ == "__main__":
    app.run(port=5000)