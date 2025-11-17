from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import pymysql
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import session, redirect, url_for, flash

app = Flask(__name__)
CORS(app)
app.secret_key = 'your_secret_key_here'

# ===================== DATABASE CONFIG =====================
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Vibhaganesh2522$',
    'database': 'gym_management',
    'cursorclass': pymysql.cursors.DictCursor
}

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

# -------------------- AUTH HELPERS --------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("user_login"))
        return f(*args, **kwargs)
    return decorated

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") != role:
                flash("Access denied.", "danger")
                if role == "admin":
                    return redirect(url_for("admin_login"))
                else:
                    return redirect(url_for("user_login"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# -------------------- ADMIN LOGIN --------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM Admin WHERE Username=%s", (username,))
        admin = cur.fetchone()
        conn.close()

        if admin and check_password_hash(admin["PasswordHash"], password):
            session.clear()
            session["user_id"] = admin["AdminID"]
            session["role"] = "admin"
            session["username"] = admin["Username"]
            return redirect(url_for("admin_dashboard"))

        flash("Invalid credentials", "danger")
        return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


# -------------------- MEMBER LOGIN --------------------
@app.route("/login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        identifier = request.form.get("identifier")
        password = request.form.get("password")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM Member 
            WHERE Email=%s OR Name=%s LIMIT 1
        """, (identifier, identifier))
        member = cur.fetchone()
        conn.close()

        if member and member["PasswordHash"] and check_password_hash(member["PasswordHash"], password):
            session.clear()
            session["user_id"] = member["MemberID"]
            session["role"] = "member"
            session["username"] = member["Name"]
            return redirect(url_for("user_dashboard"))

        flash("Invalid credentials", "danger")
        return redirect(url_for("user_login"))

    return render_template("user_login.html")


# -------------------- LOGOUT --------------------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("user_login"))


# -------------------- DASHBOARDS --------------------
@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    return render_template("admin_dashboard.html")

@app.route("/user/dashboard")
@role_required("member")
def user_dashboard():
    return render_template("user_dashboard.html")




# ===================== HELPERS =====================
def normalize_date(s):
    if not s:
        return None
    s = str(s).strip()
    try:
        # Accept several formats
        if "/" in s and len(s.split("/")[0]) == 2:
            return datetime.strptime(s, "%d/%m/%Y").strftime("%Y-%m-%d")
        if "-" in s and len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
        if "T" in s:
            return datetime.fromisoformat(s.split("T")[0]).strftime("%Y-%m-%d")
        return None
    except Exception:
        return None


# ===================== HOME / DASHBOARD =====================
@app.route('/')
def index():
    return render_template('index.html', current_year=datetime.now().year)


@app.route('/dashboard')
def dashboard():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Active members
        cur.execute("SELECT COUNT(*) AS c FROM Member WHERE Status='Active'")
        active_members = cur.fetchone()['c'] or 0

        # Revenue
        cur.execute("SELECT SUM(Amount) AS total FROM Payment WHERE Status='Paid'")
        revenue = cur.fetchone()['total'] or 0

        # Trainers
        cur.execute("SELECT COUNT(*) AS c FROM Trainer")
        trainers = cur.fetchone()['c'] or 0

        # Recent payments
        cur.execute("""
            SELECT p.PaymentID, p.PaymentDate, m.Name AS MemberName,
                   p.Amount, p.PaymentMethod, p.Status
            FROM Payment p
            LEFT JOIN Member m ON m.MemberID = p.MemberID
            ORDER BY p.PaymentDate DESC LIMIT 5
        """)
        recent = cur.fetchall()

        # Member status distribution
        cur.execute("""
            SELECT Status, COUNT(*) AS Count
            FROM Member
            GROUP BY Status
        """)
        status_rows = cur.fetchall()
        member_status_labels = [r["Status"] for r in status_rows]
        member_status_counts = [r["Count"] for r in status_rows]

        # Monthly revenue chart
        cur.execute("""
            SELECT DATE_FORMAT(PaymentDate, '%Y-%m') AS Month,
                   SUM(Amount) AS Total
            FROM Payment
            WHERE Status='Paid'
            GROUP BY Month
            ORDER BY Month
        """)
        rev = cur.fetchall()
        monthly_labels = [r["Month"] for r in rev]
        monthly_values = [float(r["Total"]) for r in rev]

        conn.close()

        return render_template("dashboard.html",
            active_members=active_members,
            total_revenue=float(revenue),
            total_trainers=trainers,
            recent_payments=recent,
            member_status_labels=member_status_labels,
            member_status_counts=member_status_counts,
            monthly_labels=monthly_labels,
            monthly_values=monthly_values
        )

    except Exception as e:
        print("💥 Dashboard Error:", e)
        return "Error", 500


# ===================== MEMBERS PAGE & API =====================
@app.route('/members')
def members_page():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT m.*, t.Name AS TrainerName, t.Specialization
            FROM Member m
            LEFT JOIN Trainer t ON t.TrainerID = m.TrainerID
            ORDER BY m.MemberID DESC
        """)
        rows = cur.fetchall()
        conn.close()
        return render_template('members.html', members=rows)
    except Exception as e:
        print("❌ Error loading members page:", e)
        return "Error loading members.", 500


@app.post("/api/members")
def api_create_member():
    try:
        data = request.get_json(force=True) or {}
        name = data.get("name")
        email = data.get("email")
        phone = data.get("phone")
        dob = normalize_date(data.get("dateOfBirth"))
        join_date = normalize_date(data.get("joinDate"))
        status = data.get("status") or "Active"

        if not name:
            return jsonify({"success": False, "error": "Name is required"}), 400

        # ⭐ DEFAULT MEMBER PASSWORD ⭐
        password_hash = generate_password_hash("member123")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO Member (Name, Email, Phone, DateOfBirth, JoinDate, Status, PasswordHash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, email, phone, dob, join_date, status, password_hash))

        member_id = cur.lastrowid

        conn.commit()
        conn.close()
        return jsonify({"success": True, "MemberID": member_id})

    except Exception as e:
        print("❌ Error adding member:", e)
        return jsonify({"success": False, "error": str(e)}), 500



@app.get("/api/members")
def api_members_list():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT MemberID, Name FROM Member ORDER BY MemberID DESC")
        rows = cur.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        print("❌ Error fetching members list:", e)
        return jsonify([]), 500



# DELETE a member (needed by members.html)
@app.delete("/api/members/<int:member_id>")
def api_delete_member(member_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # delete related sessions, memberplans, payments optionally depending on your schema
        cur.execute("DELETE FROM Session WHERE MemberID=%s", (member_id,))
        cur.execute("DELETE FROM MemberPlan WHERE MemberID=%s", (member_id,))
        cur.execute("DELETE FROM Payment WHERE MemberID=%s", (member_id,))
        cur.execute("DELETE FROM Progress WHERE MemberID=%s", (member_id,))
        cur.execute("DELETE FROM Member WHERE MemberID=%s", (member_id,))

        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Delete member error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


# Assign trainer to a single member
@app.post('/api/members/<int:member_id>/trainer')
def api_assign_trainer(member_id):
    try:
        data = request.get_json() or {}
        trainer_id = data.get('TrainerID')
        if not trainer_id:
            return jsonify({"success": False, "error": "TrainerID required"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE Member SET TrainerID = %s WHERE MemberID = %s", (trainer_id, member_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Assign trainer error:", e)
        return jsonify({"success": False, "error": str(e)}), 500

# Unassign trainer for a single member
@app.delete('/api/members/<int:member_id>/trainer')
def api_unassign_trainer(member_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE Member SET TrainerID = NULL WHERE MemberID = %s", (member_id,))
        # optionally unset Session.TrainerID for that member (only if you want)
        cur.execute("UPDATE Session SET TrainerID = NULL WHERE MemberID = %s", (member_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Unassign trainer error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


# ===================== TRAINERS PAGE & API =====================
@app.route('/trainers')
def trainers_page():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT t.TrainerID, t.Name, t.Specialization, t.Phone, t.HireDate,
                   COUNT(CASE WHEN s.Status != 'Cancelled' THEN 1 END) AS SessionCount
            FROM Trainer t
            LEFT JOIN Session s ON s.TrainerID = t.TrainerID
            GROUP BY t.TrainerID
            ORDER BY t.TrainerID DESC
        """)
        rows = cur.fetchall()
        conn.close()
        return render_template('trainers.html', trainers=rows)
    except Exception as e:
        print("❌ Error loading trainers page:", e)
        return "Error loading trainers.", 500


@app.get('/api/trainers')
def api_get_trainers():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT TrainerID, Name, Specialization, Phone, HireDate FROM Trainer ORDER BY TrainerID DESC")
        rows = cur.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        print("❌ Error fetching trainers:", e)
        return jsonify([]), 500


@app.post('/api/trainers')
def api_create_trainer():
    try:
        data = request.get_json() or {}
        name = data.get("name")
        specialization = data.get("specialization")
        phone = data.get("phone")
        hire_date = normalize_date(data.get("hireDate"))

        if not (name and specialization):
            return jsonify({"success": False, "error": "Name and specialization required"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO Trainer (Name, Specialization, Phone, HireDate) VALUES (%s,%s,%s,%s)",
                    (name, specialization, phone, hire_date))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Create trainer error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.delete('/api/trainers/<int:trainer_id>')
def api_delete_trainer(trainer_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Unassign trainer from members first
        cur.execute("UPDATE Member SET TrainerID = NULL WHERE TrainerID = %s", (trainer_id,))
        cur.execute("DELETE FROM Trainer WHERE TrainerID = %s", (trainer_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Delete trainer error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


# ===================== SESSIONS (used by templates) =====================
@app.post('/api/sessions')
def api_create_session():
    try:
        data = request.get_json() or {}
        trainer_id = data.get("TrainerID")
        member_id = data.get("MemberID")
        date_ = normalize_date(data.get("ScheduledDate"))
        time_ = data.get("ScheduledTime")
        status = data.get("Status", "Scheduled")

        if not (trainer_id and member_id and date_ and time_):
            return jsonify({"success": False, "error": "Missing fields"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO Session (TrainerID, MemberID, ScheduledDate, ScheduledTime, Status)
            VALUES (%s, %s, %s, %s, %s)
        """, (trainer_id, member_id, date_, time_, status))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Create session error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/trainers/<int:trainer_id>/sessions')
def api_trainer_sessions(trainer_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT s.SessionID, s.MemberID, s.TrainerID,
                   m.Name AS MemberName,
                   DATE_FORMAT(s.ScheduledDate, '%%Y-%%m-%%d') AS ScheduledDate,
                   s.ScheduledTime, s.Status
            FROM Session s
            LEFT JOIN Member m ON m.MemberID = s.MemberID
            WHERE s.TrainerID = %s
            ORDER BY s.ScheduledDate DESC, s.ScheduledTime DESC
        """, (trainer_id,))
        rows = cur.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        print("❌ Error fetching trainer sessions:", e)
        return jsonify([]), 500


@app.put('/api/sessions/<int:session_id>')
def api_update_session(session_id):
    try:
        data = request.get_json() or {}
        status = data.get("Status")
        allowed = ["Scheduled", "Ongoing", "Completed", "Cancelled"]
        if status not in allowed:
            return jsonify({"success": False, "error": "Invalid status"}), 400
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE Session SET Status = %s WHERE SessionID = %s", (status, session_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Update session error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.delete('/api/sessions/<int:session_id>')
def api_delete_session(session_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM Session WHERE SessionID = %s", (session_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Delete session error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


# ===================== MEMBERSHIP PLANS =====================
@app.route('/plans')
def plans_page():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM MembershipPlan ORDER BY PlanID DESC")
        rows = cur.fetchall()
        conn.close()
        return render_template("plans.html", plans=rows)

    except Exception as e:
        print("❌ Error loading plans page:", e)
        return "Error", 500


@app.get("/api/plans")
def api_get_plans():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM MembershipPlan ORDER BY PlanID DESC")
        rows = cur.fetchall()
        conn.close()
        return jsonify(rows)

    except Exception as e:
        print("❌ Error fetching plans:", e)
        return jsonify([]), 500


@app.post("/api/plans")
def api_create_plan():
    try:
        data = request.get_json() or {}
        name = data.get("PlanName")
        duration = data.get("DurationMonths")
        price = data.get("Price")

        if not (name and duration and price):
            return jsonify({"success": False, "error": "Missing plan fields"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO MembershipPlan (PlanName, DurationMonths, Price)
            VALUES (%s, %s, %s)
        """, (name, duration, price))

        conn.commit()
        conn.close()
        return jsonify({"success": True})

    except Exception as e:
        print("❌ Create plan error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


# ===================== ASSIGN PLAN + AUTO PAYMENT =====================
@app.post("/api/member-plans")
def api_assign_plan():
    try:
        data = request.get_json() or {}
        member_id = data.get("MemberID")
        plan_id = data.get("PlanID")
        start_date = normalize_date(data.get("StartDate"))
        spec = data.get("PreferredSpecialization")

        if not (member_id and plan_id and start_date):
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT DurationMonths, Price FROM MembershipPlan WHERE PlanID=%s", (plan_id,))
        plan = cur.fetchone()
        duration = int(plan["DurationMonths"])
        price = float(plan["Price"])

        # Calculate end date
        end_date = (
            datetime.strptime(start_date, "%Y-%m-%d")
            + timedelta(days=30 * duration)
        ).strftime("%Y-%m-%d")

        # Insert member plan
        cur.execute("""
            INSERT INTO MemberPlan (MemberID, PlanID, StartDate, EndDate, PreferredSpecialization)
            VALUES (%s, %s, %s, %s, %s)
        """, (member_id, plan_id, start_date, end_date, spec))

        # Auto-payment
        cur.execute("""
            INSERT INTO Payment (MemberID, Amount, PaymentDate, PaymentMethod, Status)
            VALUES (%s, %s, CURDATE(), 'UPI', 'Paid')
        """, (member_id, price))

        conn.commit()
        conn.close()
        return jsonify({"success": True})

    except Exception as e:
        print("❌ Assign plan error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


# ===================== PAYMENTS PAGE =====================
@app.route('/payments')
def payments_page():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT p.*, m.Name AS MemberName
            FROM Payment p
            LEFT JOIN Member m ON m.MemberID = p.MemberID
            ORDER BY p.PaymentDate DESC
        """)
        rows = cur.fetchall()
        conn.close()
        return render_template("payments.html", payments=rows)

    except Exception as e:
        print("❌ Error loading payments:", e)
        return "Error loading payments.", 500
    
@app.post("/api/payments")
def api_add_payment():
    try:
        data = request.get_json() or {}

        
        member_id = data.get("memberId") or data.get("MemberID")
        amount = data.get("amount") or data.get("Amount")
        date_ = normalize_date(data.get("paymentDate") or data.get("PaymentDate"))
        method = data.get("paymentMethod") or data.get("PaymentMethod")
        status = data.get("status") or data.get("Status")

        if not (member_id and amount and date_ and method):
            return jsonify({"success": False, "error": "Missing fields"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO Payment (MemberID, Amount, PaymentDate, PaymentMethod, Status)
            VALUES (%s, %s, %s, %s, %s)
        """, (member_id, amount, date_, method, status))

        conn.commit()
        conn.close()

        return jsonify({"success": True})

    except Exception as e:
        print("❌ Add payment error:", e)
        return jsonify({"success": False, "error": str(e)}), 500



# ===================== PROGRESS PAGES & APIs =====================
def fetch_progress_rows(cur):
    """
    Robust select for progress rows. Try to include BMI / MuscleMass / BodyFat.
    If the DB schema lacks some columns, fall back gracefully and ensure returned
    rows always contain the same keys (with None for missing values).
    """
    # First attempt: full select
    try:
        cur.execute("""
            SELECT pr.ProgressID,
                   pr.MemberID,
                   m.Name AS MemberName,
                   DATE_FORMAT(pr.Date, '%Y-%m-%d') AS Date,
                   pr.Weight,
                   pr.BodyFat,
                   pr.BMI,
                   pr.MuscleMass,
                   pr.Notes
            FROM Progress pr
            LEFT JOIN Member m ON m.MemberID = pr.MemberID
            ORDER BY pr.Date DESC
        """)
        rows = cur.fetchall()
        # Normalize keys to ensure presence
        for r in rows:
            r.setdefault('BodyFat', None)
            r.setdefault('BMI', None)
            r.setdefault('MuscleMass', None)
            r.setdefault('Notes', None)
        return rows
    except Exception as e:
        # Fall back to minimal select if schema differs
        print("⚠️ Progress full-select failed, falling back:", e)
        cur.execute("""
            SELECT pr.ProgressID,
                   pr.MemberID,
                   m.Name AS MemberName,
                   DATE_FORMAT(pr.Date, '%%Y-%%m-%%d') AS Date,
                   pr.Weight,
                   pr.Notes
            FROM Progress pr
            LEFT JOIN Member m ON m.MemberID = pr.MemberID
            ORDER BY pr.Date DESC
        """)
        rows = cur.fetchall()
        for r in rows:
            r.setdefault('BodyFat', None)
            r.setdefault('BMI', None)
            r.setdefault('MuscleMass', None)
            r.setdefault('Notes', None)
        return rows


# Progress page (renders template with progress rows + members for forms)
@app.route('/progress')
def progress_page():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        rows = fetch_progress_rows(cur)

        # members for select lists (MemberID + Name)
        cur.execute("SELECT MemberID, Name FROM Member ORDER BY Name")
        members = cur.fetchall()

        conn.close()
        return render_template('progress.html', progress=rows, members=members)

    except Exception as e:
        print("❌ Error loading progress page:", e)
        return "Error loading progress page", 500


# API: GET all progress or filtered by member via ?member_id=
@app.get('/api/progress')
def api_get_progress():
    try:
        member_id = request.args.get('member_id')
        conn = get_db_connection()
        cur = conn.cursor()

        if member_id:
            cur.execute("""
                SELECT pr.ProgressID,
                       pr.MemberID,
                       m.Name AS MemberName,
                       DATE_FORMAT(pr.Date, '%%Y-%%m-%%d') AS Date,
                       pr.Weight,
                       pr.BodyFat,
                       pr.BMI,
                       pr.MuscleMass,
                       pr.Notes
                FROM Progress pr
                LEFT JOIN Member m ON m.MemberID = pr.MemberID
                WHERE pr.MemberID = %s
                ORDER BY pr.Date DESC
            """, (member_id,))
            rows = cur.fetchall()
            for r in rows:
                r.setdefault('BodyFat', None)
                r.setdefault('BMI', None)
                r.setdefault('MuscleMass', None)
                r.setdefault('Notes', None)
            conn.close()
            return jsonify(rows)

        # no member filter — use robust helper
        rows = fetch_progress_rows(cur)
        conn.close()
        return jsonify(rows)

    except Exception as e:
        print("❌ Error fetching progress:", e)
        return jsonify([]), 500


# API: add progress (handles presence/absence of optional columns)
@app.post('/api/progress')
def api_add_progress():
    try:
        data = request.get_json() or {}
        member_id = data.get("MemberID")
        date_ = normalize_date(data.get("Date"))
        weight = data.get("Weight")
        bmi = data.get("BMI")
        muscle = data.get("MuscleMass")
        bodyfat = data.get("BodyFat")
        notes = data.get("Notes")

        if not (member_id and date_ and (weight is not None and weight != "")):
            return jsonify({"success": False, "error": "Missing required fields (MemberID, Date, Weight)"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        # Try a full insert first (works when all optional columns exist)
        try:
            cur.execute("""
                INSERT INTO Progress (MemberID, Date, Weight, BodyFat, BMI, MuscleMass, Notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (member_id, date_, weight, bodyfat, bmi, muscle, notes))
        except Exception as e:
            # Fallback insert: try without optional columns that might be missing
            print("⚠️ Insert with all columns failed, trying fallback insert:", e)
            # Attempt an insert with only the columns that are very likely to exist
            cur.execute("""
                INSERT INTO Progress (MemberID, Date, Weight, Notes)
                VALUES (%s, %s, %s, %s)
            """, (member_id, date_, weight, notes))

        conn.commit()
        conn.close()
        return jsonify({"success": True})

    except Exception as e:
        print("❌ Add progress error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


# API: update progress (robust update tries full update then fallback)
@app.put('/api/progress/<int:progress_id>')
def api_update_progress(progress_id):
    try:
        data = request.get_json() or {}
        date_ = normalize_date(data.get("Date"))
        weight = data.get("Weight")
        bmi = data.get("BMI")
        muscle = data.get("MuscleMass")
        bodyfat = data.get("BodyFat")
        notes = data.get("Notes")

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute("""
                UPDATE Progress
                SET Date=%s, Weight=%s, BodyFat=%s, BMI=%s, MuscleMass=%s, Notes=%s
                WHERE ProgressID=%s
            """, (date_, weight, bodyfat, bmi, muscle, notes, progress_id))
        except Exception as e:
            print("⚠️ Update with optional columns failed, falling back:", e)
            cur.execute("""
                UPDATE Progress
                SET Date=%s, Weight=%s, Notes=%s
                WHERE ProgressID=%s
            """, (date_, weight, notes, progress_id))

        conn.commit()
        conn.close()
        return jsonify({"success": True})

    except Exception as e:
        print("❌ Update progress error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


# API: delete progress
@app.delete('/api/progress/<int:progress_id>')
def api_delete_progress(progress_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM Progress WHERE ProgressID=%s", (progress_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print("❌ Delete progress error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


# Analytics: time series for charts (returns date, weight, optional bodyfat)
@app.get('/api/analytics/progress/<int:member_id>')
def api_progress_timeseries(member_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Try select including BodyFat
        try:
            cur.execute("""
                SELECT DATE_FORMAT(Date, '%%Y-%%m-%%d') AS date,
                       Weight AS weight,
                       BodyFat AS bodyfat
                FROM Progress
                WHERE MemberID = %s
                ORDER BY Date ASC
            """, (member_id,))
            rows = cur.fetchall()

            for r in rows:
                r.setdefault('bodyfat', None)

            conn.close()
            return jsonify(rows)

        except Exception as e:
            print("⚠️ Timeseries select with bodyfat failed, falling back:", e)

            cur.execute("""
                SELECT DATE_FORMAT(Date, '%%Y-%%m-%%d') AS date,
                       Weight AS weight
                FROM Progress
                WHERE MemberID = %s
                ORDER BY Date ASC
            """, (member_id,))
            rows = cur.fetchall()

            for r in rows:
                r.setdefault('bodyfat', None)

            conn.close()
            return jsonify(rows)

    except Exception as e:
        print("❌ Error fetching timeseries:", e)
        return jsonify([]), 500


# ===================== RUN =====================
if __name__ == "__main__":
    app.run(debug=True, port=5000)
