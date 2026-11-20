# app.py
import os
import io
import re
import csv
import uuid
import random
import string
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, redirect, url_for, flash, request,
                   abort, send_file, session, jsonify, send_from_directory)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from werkzeug.utils import secure_filename
from sqlalchemy import func, case as sql_case

try:
    from flask_mail import Mail, Message
    MAIL_OK = True
except Exception:
    MAIL_OK = False

from config import Config
from models import (db, User, Category, Complaint, Assignment, ComplaintUpdate,
                    Attachment, Notification, Feedback, STATUSES, PRIORITIES, ROLES)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer)
    REPORTLAB_OK = True
except Exception:
    REPORTLAB_OK = False

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

mail = None
if MAIL_OK and app.config.get("MAIL_USERNAME"):
    app.config.setdefault("MAIL_SERVER", "smtp.gmail.com")
    app.config.setdefault("MAIL_PORT", 587)
    app.config.setdefault("MAIL_USE_TLS", True)
    mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in first."
login_manager.login_message_category = "warning"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def generate_tracking_id():
    while True:
        tid = "CMP-{}-{}".format(
            datetime.utcnow().strftime("%Y%m%d"),
            "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        )
        if not Complaint.query.filter_by(tracking_id=tid).first():
            return tid


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def save_attachments(files, complaint_id):
    for f in files:
        if f and f.filename and allowed_file(f.filename):
            ext = f.filename.rsplit(".", 1)[1].lower()
            stored = f"{uuid.uuid4().hex}.{ext}"
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], stored))
            original = secure_filename(f.filename) or f"attachment.{ext}"
            db.session.add(Attachment(complaint_id=complaint_id, filename=stored, original_name=original))


def notify(user_id, complaint_id, message):
    db.session.add(Notification(user_id=user_id, complaint_id=complaint_id, message=message))


def notify_admins(complaint_id, message):
    for admin in User.query.filter_by(role="admin", is_active=True).all():
        notify(admin.id, complaint_id, message)


def t(key, **kwargs):
    text = (key or "").replace("_", " ").replace("-", " ").title()
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


# ============================================================
# SLA — Service Level Agreement (Default: 2 Hours)
# ============================================================
SLA_HOURS = {
    "Urgent": 2,
    "High": 2,
    "Medium": 2,
    "Low": 2,
}


def calculate_sla_deadline(priority, base=None):
    hours = SLA_HOURS.get(priority, 2)
    return (base or datetime.utcnow()) + timedelta(hours=hours)


def get_sla_status(complaint):
    if not complaint.sla_deadline:
        return {"status": "no_sla", "hours_left": None,
                "label": "No SLA", "color": "secondary"}

    if complaint.status in ("Resolved", "Closed", "Rejected"):
        if complaint.resolved_at and complaint.resolved_at <= complaint.sla_deadline:
            return {"status": "completed_on_time", "hours_left": 0,
                    "label": "Resolved in time", "color": "success"}
        elif complaint.resolved_at:
            return {"status": "completed_late", "hours_left": 0,
                    "label": "Resolved late", "color": "warning"}
        return {"status": "completed", "hours_left": 0,
                "label": "Completed", "color": "secondary"}

    if complaint.is_escalated:
        return {"status": "escalated", "hours_left": 0,
                "label": "Escalated", "color": "danger"}

    now = datetime.utcnow()
    hours_left = (complaint.sla_deadline - now).total_seconds() / 3600

    if hours_left < 0:
        return {"status": "exceeded", "hours_left": round(hours_left, 1),
                "label": "SLA Exceeded", "color": "danger"}
    elif hours_left < 1:
        return {"status": "urgent", "hours_left": round(hours_left, 1),
                "label": "Approaching", "color": "warning"}
    else:
        return {"status": "on_time", "hours_left": round(hours_left, 1),
                "label": "On Track", "color": "info"}


def check_and_escalate_overdue():
    missing = Complaint.query.filter(
        Complaint.sla_deadline.is_(None),
        Complaint.status.notin_(["Resolved", "Closed", "Rejected"]),
    ).all()
    for c in missing:
        c.sla_deadline = calculate_sla_deadline(c.priority, c.created_at)

    overdue = Complaint.query.filter(
        Complaint.status.notin_(["Resolved", "Closed", "Rejected"]),
        Complaint.sla_deadline.isnot(None),
        Complaint.sla_deadline < datetime.utcnow(),
        Complaint.is_escalated.is_(False),
    ).all()

    count = 0
    for c in overdue:
        c.is_escalated = True
        c.escalated_at = datetime.utcnow()

        db.session.add(ComplaintUpdate(
            complaint_id=c.id,
            updated_by=None,
            status="Escalated",
            message=(
                f"SLA deadline ({c.sla_deadline.strftime('%d %b %Y, %I:%M %p')}) "
                f"exceeded for {c.priority}-priority complaint. "
                f"Auto-escalated to higher authority."
            ),
        ))

        notify_admins(c.id,
                      f"🚨 ESCALATED: Complaint {c.tracking_id} breached SLA ({c.priority} priority).")

        if c.officer_id:
            notify(c.officer_id, c.id,
                   f"⚠️ Your complaint {c.tracking_id} has been escalated to higher authority — SLA exceeded.")

        notify(c.user_id, c.id,
               f"Your complaint {c.tracking_id} has been escalated to higher authority for faster action.")

        count += 1

    db.session.commit()
    return count


# ============================================================
# Duplicate Detection
# ============================================================
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "this", "that",
    "these", "those", "i", "you", "he", "she", "it", "we", "they",
    "আমি", "আমরা", "তুমি", "আপনি", "সে", "তারা", "এই", "সেই", "এবং",
    "বা", "কিন্তু", "একটি", "একটা", "হয়", "হয়েছে", "হয়নি", "করে", "করেছে",
    "থেকে", "জন্য", "সাথে", "আছে", "নেই", "একই", "খুব",
}


def _tokenize(text):
    text = (text or "").lower()
    words = re.findall(r"[\w\u0980-\u09FF]+", text)
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def find_similar_complaints(title, description, category_id=None,
                            exclude_id=None, threshold=0.35):
    if not title or not description:
        return []

    new_tokens = _tokenize(title + " " + description)
    if not new_tokens:
        return []

    q = Complaint.query.filter(
        Complaint.status.notin_(["Closed", "Rejected"])
    )
    if category_id:
        q = q.filter(Complaint.category_id == category_id)
    if exclude_id:
        q = q.filter(Complaint.id != exclude_id)

    candidates = q.all()
    scored = []
    for c in candidates:
        old_tokens = _tokenize((c.title or "") + " " + (c.description or ""))
        if not old_tokens:
            continue
        intersection = new_tokens & old_tokens
        union = new_tokens | old_tokens
        if not union:
            continue
        score = len(intersection) / len(union)
        if category_id and c.category_id == category_id:
            score = min(score * 1.15, 1.0)
        if score >= threshold:
            scored.append((c, round(score, 2)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:5]


# ============================================================
# API — Duplicate check (AJAX)
# ============================================================
@app.route("/api/check-duplicates", methods=["POST"])
@role_required("user")
def check_duplicates_api():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    category_id = data.get("category_id")

    try:
        category_id = int(category_id) if category_id else None
    except ValueError:
        category_id = None

    if not title or not description:
        return jsonify({"count": 0, "duplicates": []})

    similar = find_similar_complaints(title, description, category_id)

    return jsonify({
        "count": len(similar),
        "duplicates": [
            {
                "id": c.id,
                "tracking_id": c.tracking_id,
                "title": c.title,
                "status": c.status,
                "priority": c.priority,
                "similarity": round(score * 100),
                "url": url_for("complaint_detail", cid=c.id),
            }
            for c, score in similar
        ],
    })


@app.context_processor
def inject_globals():
    unread = 0
    try:
        if current_user.is_authenticated:
            unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    except Exception:
        unread = 0
    return dict(
        unread_count=unread,
        STATUSES=STATUSES,
        PRIORITIES=PRIORITIES,
        get_sla_status=get_sla_status,
        t=t,
    )


@app.route("/")
def root():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_router"))
    return render_template("auth/login.html")


@app.route("/home")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_router"))
    return render_template("index.html")


@app.route("/dashboard")
@login_required
def dashboard_router():
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    if current_user.role == "officer":
        return redirect(url_for("officer_dashboard"))
    return redirect(url_for("user_dashboard"))


@app.route("/track", methods=["GET", "POST"])
def track():
    complaint, tid = None, ""
    if request.method == "POST":
        tid = request.form.get("tracking_id", "").strip().upper()
        if not tid:
            flash("Please enter a Tracking ID.", "warning")
        else:
            complaint = Complaint.query.filter_by(tracking_id=tid).first()
            
    layout = "base.html" if current_user.is_authenticated else "base_public.html"
    return render_template("track.html", complaint=complaint, tid=tid, layout=layout)


# ============================================================
# REGISTER
# ============================================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_router"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        errors = {}
        if len(name) < 3:
            errors["name"] = "Name must be at least 3 characters long."
        if not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", email):
            errors["email"] = "Please enter a valid email address."
        if phone and (not phone.isdigit() or len(phone) != 11):
            errors["phone"] = "Phone number must be exactly 11 digits."
        if len(password) < 6:
            errors["password"] = "Password must be at least 6 characters long."
        if password != confirm:
            errors["confirm"] = "Passwords must match."
        if email and User.query.filter_by(email=email).first():
            errors["email"] = "This email is already registered."

        if errors:
            return render_template("auth/register.html", errors=errors, form_data=request.form)

        user = User(name=name, email=email, phone=phone, role="user")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Registration successful! Please log in now.", "success")
        return redirect(url_for("login"))

    return render_template("auth/register.html", errors={}, form_data={})


# ============================================================
# LOGIN
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_router"))

    login_error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        selected_role = request.form.get("role", "user")

        if not email or not password:
            login_error = "Email and Password cannot be empty."
        else:
            user = User.query.filter_by(email=email).first()
            if user and user.is_active and user.check_password(password):
                if user.role == selected_role:
                    login_user(user, remember=bool(request.form.get("remember")))
                    session.permanent = True
                    flash(f"Welcome, {user.name}!", "success")
                    return redirect(url_for("dashboard_router"))
                else:
                    login_error = f"Access Denied. You selected '{selected_role}', but your account is '{user.role}'."
            else:
                login_error = "Incorrect email or password, or account is inactive."

    return render_template("auth/login.html", login_error=login_error)


# ============================================================
# LOGOUT
# ============================================================
@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    session.clear()

    response = redirect(url_for("login"))
    response.delete_cookie("session")
    response.delete_cookie("remember_token")

    flash("You have successfully logged out.", "info")
    return response


# ============================================================
# FORGOT / RESET PASSWORD
# ============================================================
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_router"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", email):
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for("forgot_password"))

        otp = str(random.randint(100000, 999999))

        user = User.query.filter_by(email=email, is_active=True).first()
        if user:
            user.reset_otp = otp
            user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()

        if app.debug:
            print("\n" + "█" * 60)
            print(f"█  PASSWORD RESET OTP FOR: {email.ljust(31)} █")
            print(f"█  OTP CODE: {otp.center(45)} █")
            print("█" * 60 + "\n")
            session["display_otp"] = otp

        session["reset_email"] = email
        flash(f"An OTP has been generated for {email}! Please verify it below.", "info")
        return redirect(url_for("verify_otp"))

    return render_template("auth/forgot_password.html")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if "reset_email" not in session:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()
        email = session.get("reset_email")
        user = User.query.filter_by(email=email, is_active=True).first()

        is_valid = False
        if user:
            if (user.reset_otp and user.reset_otp == entered_otp
                    and user.otp_expiry and user.otp_expiry >= datetime.utcnow()):
                is_valid = True
        elif app.debug and session.get("display_otp") == entered_otp:
            is_valid = True

        if is_valid:
            session["otp_verified"] = True
            session.pop("display_otp", None)
            flash("OTP verified successfully. Please set a new password.", "success")
            return redirect(url_for("reset_password"))
        else:
            flash("Invalid or expired OTP. Please try again.", "danger")

    return render_template("auth/verify_otp.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if not session.get("otp_verified") or "reset_email" not in session:
        flash("Please verify your OTP first.", "warning")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("auth/reset_password.html")
        if password != confirm:
            flash("Passwords must match.", "danger")
            return render_template("auth/reset_password.html")

        user = User.query.filter_by(email=session["reset_email"]).first()

        if user:
            user.set_password(password)
            user.reset_otp = None
            user.otp_expiry = None
            db.session.commit()
            flash("Password changed successfully. Please log in.", "success")
        else:
            flash("OTP verified! But this email is not registered, so password could not be saved in DB. (Demo Mode)", "warning")

        session.pop("reset_email", None)
        session.pop("otp_verified", None)

        return redirect(url_for("login"))

    return render_template("auth/reset_password.html")


# ============================================================
# USER DASHBOARD
# ============================================================
@app.route("/user/dashboard")
@role_required("user")
def user_dashboard():
    base = Complaint.query.filter_by(user_id=current_user.id)

    stats = {
        "total": base.count(),
        "pending": base.filter_by(status="Pending").count(),
        "in_progress": base.filter(Complaint.status.in_(["In Review", "Assigned", "In Progress"])).count(),
        "resolved": base.filter(Complaint.status.in_(["Resolved", "Closed"])).count(),
    }

    by_status = dict(
        db.session.query(Complaint.status, func.count(Complaint.id))
        .filter(Complaint.user_id == current_user.id)
        .group_by(Complaint.status).all()
    )
    by_category = (
        db.session.query(Category.name, func.count(Complaint.id))
        .join(Complaint, Complaint.category_id == Category.id)
        .filter(Complaint.user_id == current_user.id)
        .group_by(Category.name).all()
    )

    recent = base.order_by(Complaint.created_at.desc()).limit(5).all()
    pending_feedback = base.filter(Complaint.status.in_(["Resolved", "Closed"])).filter(~Complaint.feedback.has()).all()
    recent_notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(3).all()

    return render_template(
        "user/dashboard.html",
        stats=stats, by_status=by_status, by_category=by_category,
        recent=recent, pending_feedback=pending_feedback, recent_notifs=recent_notifs,
    )


# ============================================================
# COMPLAINTS LIST
# ============================================================
@app.route("/complaints")
@login_required
def complaints_list():
    base_q = Complaint.query
    if current_user.role == "user":
        base_q = base_q.filter(Complaint.user_id == current_user.id)
    elif current_user.role == "officer":
        base_q = base_q.filter(Complaint.officer_id == current_user.id)

    stats = {
        "total": base_q.count(),
        "pending": base_q.filter(Complaint.status == "Pending").count(),
        "in_progress": base_q.filter(
            Complaint.status.in_(["In Review", "Assigned", "In Progress"])
        ).count(),
        "resolved": base_q.filter(
            Complaint.status.in_(["Resolved", "Closed"])
        ).count(),
    }

    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    priority = request.args.get("priority", "").strip()
    category_id = request.args.get("category_id", type=int)
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    sort = request.args.get("sort", "newest").strip()

    q = base_q
    if status in STATUSES:
        q = q.filter(Complaint.status == status)
    if priority in PRIORITIES:
        q = q.filter(Complaint.priority == priority)
    if category_id:
        q = q.filter(Complaint.category_id == category_id)
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(
            Complaint.tracking_id.like(like),
            Complaint.title.like(like),
            Complaint.location.like(like),
            Complaint.description.like(like),
        ))
    if date_from:
        try:
            q = q.filter(Complaint.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(Complaint.created_at <= datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
        except ValueError:
            pass

    if sort == "oldest":
        q = q.order_by(Complaint.created_at.asc())
    elif sort == "priority":
        priority_case = sql_case(
            (Complaint.priority == "Urgent", 1),
            (Complaint.priority == "High", 2),
            (Complaint.priority == "Medium", 3),
            (Complaint.priority == "Low", 4),
            else_=5,
        )
        q = q.order_by(priority_case, Complaint.created_at.desc())
    elif sort == "updated":
        q = q.order_by(Complaint.updated_at.desc())
    else:
        q = q.order_by(Complaint.created_at.desc())

    pagination = q.paginate(
        page=request.args.get("page", 1, type=int), per_page=12, error_out=False)

    categories = Category.query.order_by(Category.name).all()

    officers = []
    if current_user.role == "admin":
        officers = User.query.filter_by(role="officer", is_active=True).order_by(User.name).all()

    active_filters = []
    if search:          active_filters.append(("q", f'Search: "{search}"'))
    if status:          active_filters.append(("status", f"Status: {status}"))
    if priority:        active_filters.append(("priority", f"Priority: {priority}"))
    if category_id:
        cat = db.session.get(Category, category_id)
        if cat:
            active_filters.append(("category_id", f"Category: {cat.name}"))
    if date_from:       active_filters.append(("date_from", f"From: {date_from}"))
    if date_to:         active_filters.append(("date_to", f"To: {date_to}"))

    return render_template(
        "complaints/list.html",
        pagination=pagination,
        complaints=pagination.items,
        stats=stats,
        categories=categories,
        officers=officers,
        search=search, status=status, priority=priority,
        category_id=category_id,
        date_from=date_from, date_to=date_to,
        sort=sort,
        active_filters=active_filters,
    )


# ============================================================
# COMPLAINT DETAIL
# ============================================================
@app.route("/complaints/<int:cid>")
@login_required
def complaint_detail(cid):
    c = db.session.get(Complaint, cid) or abort(404)
    if current_user.role == "user" and c.user_id != current_user.id:
        abort(403)
    if current_user.role == "officer" and c.officer_id != current_user.id:
        abort(403)

    officers = []
    officer_stats = {}
    if current_user.role == "admin":
        officers = (
            User.query.filter_by(role="officer", is_active=True)
            .order_by(User.name).all()
        )
        for o in officers:
            active = Complaint.query.filter(
                Complaint.officer_id == o.id,
                Complaint.status.in_(["Assigned", "In Progress"]),
            ).count()
            resolved = Complaint.query.filter(
                Complaint.officer_id == o.id,
                Complaint.status.in_(["Resolved", "Closed"]),
            ).count()
            officer_stats[o.id] = {"active": active, "resolved": resolved}

    assignments = (
        Assignment.query.filter_by(complaint_id=c.id)
        .order_by(Assignment.assigned_at.desc()).all()
    )

    reopen_count = ComplaintUpdate.query.filter_by(
        complaint_id=c.id, status="Reopened"
    ).count()

    can_reopen = (
        current_user.role == "user"
        and c.user_id == current_user.id
        and c.status in ("Resolved", "Closed")
    )

    if not c.sla_deadline:
        c.sla_deadline = calculate_sla_deadline(c.priority, c.created_at)
        db.session.commit()

    sla = get_sla_status(c)

    return render_template(
        "complaints/detail.html",
        c=c, officers=officers, officer_stats=officer_stats,
        assignments=assignments,
        reopen_count=reopen_count,
        can_reopen=can_reopen,
        sla=sla,
    )


# ============================================================
# SERVE UPLOADED FILES (protected)
# ============================================================
@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    att = Attachment.query.filter_by(filename=filename).first()
    if not att:
        abort(404)

    complaint = att.complaint
    if complaint:
        if current_user.role == "user" and complaint.user_id != current_user.id:
            abort(403)
        if current_user.role == "officer" and complaint.officer_id != current_user.id:
            abort(403)

    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ============================================================
# COMPLAINT REOPEN
# ============================================================
@app.route("/complaints/<int:cid>/reopen", methods=["POST"])
@role_required("user")
def reopen_complaint(cid):
    c = db.session.get(Complaint, cid) or abort(404)

    if c.user_id != current_user.id:
        abort(403)

    if c.status not in ("Resolved", "Closed"):
        flash("Only resolved or closed complaints can be reopened.", "warning")
        return redirect(url_for("complaint_detail", cid=c.id))

    reason = request.form.get("reason", "").strip()
    if len(reason) < 10:
        flash("Please provide a reason (at least 10 characters) for reopening.", "danger")
        return redirect(url_for("complaint_detail", cid=c.id))
    if len(reason) > 500:
        flash("Reason is too long (maximum 500 characters).", "danger")
        return redirect(url_for("complaint_detail", cid=c.id))

    if c.officer_id:
        new_status = "In Progress"
    else:
        new_status = "Pending"

    old_status = c.status
    c.status = new_status
    c.resolved_at = None

    had_feedback = c.feedback is not None
    if had_feedback:
        db.session.delete(c.feedback)

    db.session.add(ComplaintUpdate(
        complaint_id=c.id,
        updated_by=current_user.id,
        status="Reopened",
        message=f"Complaint reopened by user. Reason: {reason}",
    ))

    db.session.add(ComplaintUpdate(
        complaint_id=c.id,
        updated_by=current_user.id,
        status=new_status,
        message=f"Status changed from '{old_status}' to '{new_status}' due to reopen.",
    ))

    notify_admins(
        c.id,
        f"Complaint {c.tracking_id} was reopened by user {current_user.name}."
    )
    if c.officer_id:
        notify(
            c.officer_id,
            c.id,
            f"Complaint {c.tracking_id} has been reopened. Please review again."
        )

    db.session.commit()

    flash(
        f"Complaint {c.tracking_id} has been reopened. "
        f"{'Your previous feedback was removed. ' if had_feedback else ''}"
        f"An officer will review it again.",
        "success",
    )
    return redirect(url_for("complaint_detail", cid=c.id))


# ============================================================
# EXTEND SLA DEADLINE (Admin & Officer)
# ============================================================
@app.route("/complaints/<int:cid>/extend-sla", methods=["POST"])
@role_required("admin", "officer")
def extend_sla(cid):
    c = db.session.get(Complaint, cid) or abort(404)
    
    days = request.form.get("days", type=int) or 0
    hours = request.form.get("hours", type=int) or 0
    minutes = request.form.get("minutes", type=int) or 0
    seconds = request.form.get("seconds", type=int) or 0

    if days == 0 and hours == 0 and minutes == 0 and seconds == 0:
        flash("Please enter a valid time to extend the deadline.", "danger")
        return redirect(url_for("complaint_detail", cid=c.id))

    new_deadline = datetime.utcnow() + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

    c.sla_deadline = new_deadline
    c.is_escalated = False 

    db.session.add(ComplaintUpdate(
        complaint_id=c.id,
        updated_by=current_user.id,
        status="SLA Extended",
        message=f"SLA deadline reset to {days}d {hours}h {minutes}m {seconds}s from now. New deadline: {new_deadline.strftime('%d %b %Y, %I:%M %p')}"
    ))

    notify(c.user_id, c.id, f"Your complaint {c.tracking_id} SLA deadline has been updated.")
    if c.officer_id and c.officer_id != current_user.id:
        notify(c.officer_id, c.id, f"SLA deadline for complaint {c.tracking_id} updated.")

    db.session.commit()

    flash(f"SLA Deadline successfully updated. New deadline: {new_deadline.strftime('%d %b %Y, %I:%M %p')}", "success")
    return redirect(url_for("complaint_detail", cid=c.id))


# ============================================================
# COMPLAINT NEW
# ============================================================
@app.route("/complaints/new", methods=["GET", "POST"])
@role_required("user")
def complaint_new():
    categories = Category.query.order_by(Category.name).all()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category_id = request.form.get("category_id", type=int)
        priority = request.form.get("priority", "Medium")
        location = request.form.get("location", "").strip()
        force_submit = request.form.get("force_submit") == "1"

        errors = []
        if len(title) < 5:
            errors.append("Title must be at least 5 characters long.")
        if len(description) < 20:
            errors.append("Description must be at least 20 characters long.")
        if not category_id or not db.session.get(Category, category_id):
            errors.append("Please select a category.")
        if priority not in PRIORITIES:
            errors.append("Please select a valid priority.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("complaints/form.html", categories=categories, form_data=request.form)

        if not force_submit:
            duplicates = find_similar_complaints(title, description, category_id)
            if duplicates:
                return render_template(
                    "complaints/form.html",
                    categories=categories,
                    duplicates=duplicates,
                    pending_data={
                        "title": title,
                        "description": description,
                        "category_id": category_id,
                        "priority": priority,
                        "location": location,
                    },
                    show_duplicate_warning=True,
                )

        complaint = Complaint(
            tracking_id=generate_tracking_id(), user_id=current_user.id,
            category_id=category_id, title=title, description=description,
            location=location, priority=priority, status="Pending",
            sla_deadline=calculate_sla_deadline(priority),
        )

        if force_submit:
            similar = find_similar_complaints(title, description, category_id)
            if similar:
                complaint.duplicate_of = similar[0][0].id
                complaint.is_duplicate_flag = True

        db.session.add(complaint)
        db.session.flush()

        save_attachments(request.files.getlist("attachments"), complaint.id)
        db.session.add(ComplaintUpdate(
            complaint_id=complaint.id, updated_by=current_user.id,
            status="Pending", message="Complaint submitted successfully."))
        notify_admins(complaint.id,
                      f"New complaint submitted: {complaint.tracking_id} — {complaint.title}")
        db.session.commit()

        flash(f"Complaint submitted. Tracking ID: {complaint.tracking_id}", "success")
        return redirect(url_for("complaint_detail", cid=complaint.id))

    return render_template("complaints/form.html", categories=categories)


# ============================================================
# ASSIGNMENT
# ============================================================
@app.route("/complaints/<int:cid>/assign", methods=["POST"])
@role_required("admin")
def assign_officer(cid):
    c = db.session.get(Complaint, cid) or abort(404)
    officer = User.query.filter_by(
        id=request.form.get("officer_id", type=int),
        role="officer", is_active=True,
    ).first()
    if not officer:
        flash("Please select a valid officer.", "danger")
        return redirect(url_for("complaint_detail", cid=c.id))

    old_officer = c.officer
    is_reassign = old_officer is not None and old_officer.id != officer.id
    notes = request.form.get("notes", "").strip()

    c.officer_id = officer.id
    c.status = "Assigned"

    db.session.add(Assignment(
        complaint_id=c.id, officer_id=officer.id,
        assigned_by=current_user.id, notes=notes,
    ))

    if is_reassign:
        msg = f"Reassigned from {old_officer.name} to {officer.name}."
    else:
        msg = f"Assigned to {officer.name}."
    if notes:
        msg += f" Note: {notes}"

    db.session.add(ComplaintUpdate(
        complaint_id=c.id, updated_by=current_user.id,
        status="Assigned", message=msg,
    ))

    notify(officer.id, c.id, f"You have been assigned complaint {c.tracking_id}")
    if is_reassign:
        notify(old_officer.id, c.id, f"Complaint {c.tracking_id} has been reassigned.")
    notify(c.user_id, c.id, f"Your complaint {c.tracking_id} has been assigned to an officer.")

    db.session.commit()

    flash("Complaint reassigned successfully." if is_reassign else "Officer assigned successfully.", "success")
    return redirect(url_for("complaint_detail", cid=c.id))


@app.route("/admin/complaints/bulk-assign", methods=["POST"])
@role_required("admin")
def bulk_assign():
    data = request.get_json(silent=True) or {}
    ids = data.get("complaint_ids", [])
    officer_id = data.get("officer_id")

    officer = User.query.filter_by(id=officer_id, role="officer", is_active=True).first()
    if not officer:
        return jsonify({"ok": False, "error": "Invalid officer"}), 400

    count = 0
    skipped = 0
    for cid in ids:
        c = db.session.get(Complaint, cid)
        if not c or c.officer_id:
            skipped += 1
            continue
        c.officer_id = officer.id
        c.status = "Assigned"
        db.session.add(Assignment(
            complaint_id=c.id, officer_id=officer.id,
            assigned_by=current_user.id, notes="Bulk assigned",
        ))
        db.session.add(ComplaintUpdate(
            complaint_id=c.id, updated_by=current_user.id,
            status="Assigned", message=f"Bulk-assigned to {officer.name}.",
        ))
        notify(officer.id, c.id, f"You have been assigned complaint {c.tracking_id}")
        notify(c.user_id, c.id, f"Your complaint {c.tracking_id} has been assigned to an officer.")
        count += 1

    db.session.commit()
    return jsonify({"ok": True, "assigned": count, "skipped": skipped})


@app.route("/admin/assignments")
@role_required("admin")
def admin_assignments():
    page = request.args.get("page", 1, type=int)
    officer_filter = request.args.get("officer_id", type=int)
    search = request.args.get("q", "").strip()

    q = Assignment.query.order_by(Assignment.assigned_at.desc())

    if officer_filter:
        q = q.filter(Assignment.officer_id == officer_filter)

    if search:
        like = f"%{search}%"
        q = q.join(Complaint).filter(db.or_(
            Complaint.tracking_id.like(like),
            Complaint.title.like(like),
        ))

    pagination = q.paginate(page=page, per_page=20, error_out=False)

    officers = User.query.filter_by(role="officer").order_by(User.name).all()
    officer_stats = {}
    for o in officers:
        officer_stats[o.id] = {
            "total": Assignment.query.filter_by(officer_id=o.id).count(),
            "active": Complaint.query.filter(
                Complaint.officer_id == o.id,
                Complaint.status.in_(["Assigned", "In Progress"]),
            ).count(),
            "resolved": Complaint.query.filter(
                Complaint.officer_id == o.id,
                Complaint.status.in_(["Resolved", "Closed"]),
            ).count(),
        }

    return render_template(
        "admin/assignments.html",
        pagination=pagination,
        assignments=pagination.items,
        officers=officers,
        officer_stats=officer_stats,
        officer_filter=officer_filter,
        search=search,
    )


# ============================================================
# STATUS UPDATE + UPDATE LOG
# ============================================================
@app.route("/complaints/<int:cid>/status", methods=["POST"])
@role_required("admin", "officer")
def update_status(cid):
    c = db.session.get(Complaint, cid) or abort(404)

    if current_user.role == "officer" and c.officer_id != current_user.id:
        abort(403)

    new_status = request.form.get("status", "").strip()
    message = request.form.get("message", "").strip()

    if new_status not in STATUSES:
        flash("Invalid status value.", "danger")
        return redirect(url_for("complaint_detail", cid=c.id))

    if current_user.role == "officer":
        allowed = ("In Progress", "Resolved")
    else:
        allowed = tuple(STATUSES)

    if new_status not in allowed:
        flash(f"You are not allowed to set status to '{new_status}'.", "danger")
        return redirect(url_for("complaint_detail", cid=c.id))

    if new_status == c.status:
        flash(f"Complaint is already in '{new_status}' status.", "warning")
        return redirect(url_for("complaint_detail", cid=c.id))

    if new_status in ("Resolved", "Closed", "Rejected") and not message:
        flash(f"A message is required when marking as '{new_status}'.", "danger")
        return redirect(url_for("complaint_detail", cid=c.id))

    old_status = c.status
    c.status = new_status
    if new_status in ("Resolved", "Closed") and not c.resolved_at:
        c.resolved_at = datetime.utcnow()

    db.session.add(ComplaintUpdate(
        complaint_id=c.id,
        updated_by=current_user.id,
        status=new_status,
        message=message or f"Status changed from {old_status} to {new_status}.",
    ))

    notify(c.user_id, c.id, f"Your complaint {c.tracking_id} status is now: {new_status}")
    if current_user.role == "officer" and new_status == "Resolved":
        notify_admins(c.id, f"Complaint {c.tracking_id} marked resolved by {current_user.name}.")

    db.session.commit()
    flash(f"Status updated from '{old_status}' to '{new_status}'.", "success")
    return redirect(url_for("complaint_detail", cid=c.id))


@app.route("/admin/updates")
@role_required("admin")
def admin_updates():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "").strip()
    search = request.args.get("q", "").strip()
    officer_filter = request.args.get("by", type=int)

    q = ComplaintUpdate.query.order_by(ComplaintUpdate.created_at.desc())

    if status_filter in STATUSES or status_filter == "SLA Extended":
        q = q.filter(ComplaintUpdate.status == status_filter)
    if officer_filter:
        q = q.filter(ComplaintUpdate.updated_by == officer_filter)
    if search:
        like = f"%{search}%"
        q = q.join(Complaint).filter(db.or_(
            Complaint.tracking_id.like(like),
            Complaint.title.like(like),
        ))

    pagination = q.paginate(page=page, per_page=25, error_out=False)

    status_counts = dict(
        db.session.query(ComplaintUpdate.status, func.count(ComplaintUpdate.id))
        .group_by(ComplaintUpdate.status).all()
    )

    staff = User.query.filter(User.role.in_(["admin", "officer"])) \
                     .order_by(User.name).all()

    return render_template(
        "admin/updates.html",
        pagination=pagination,
        updates=pagination.items,
        status_counts=status_counts,
        staff=staff,
        status_filter=status_filter,
        officer_filter=officer_filter,
        search=search,
    )


# ============================================================
# SLA MONITOR
# ============================================================
@app.route("/admin/sla")
@role_required("admin")
def admin_sla():
    newly_escalated = check_and_escalate_overdue()

    tab = request.args.get("tab", "overdue")

    base_active = Complaint.query.filter(
        Complaint.status.notin_(["Resolved", "Closed", "Rejected"]),
        Complaint.sla_deadline.isnot(None),
    )

    now = datetime.utcnow()
    soon = now + timedelta(hours=2)
    now_utc = now

    overdue_list = base_active.filter(Complaint.sla_deadline < now) \
        .order_by(Complaint.sla_deadline.asc()).all()

    approaching_list = base_active.filter(
        Complaint.sla_deadline >= now,
        Complaint.sla_deadline < soon,
    ).order_by(Complaint.sla_deadline.asc()).all()

    # ⬇️ এখানে status.notin_ যুক্ত করা হয়েছে, যাতে Resolved কমপ্লেইন Escalated লিস্টে না আসে
    escalated_list = Complaint.query.filter(
        Complaint.is_escalated == True,
        Complaint.status.notin_(["Resolved", "Closed", "Rejected"])
    ).order_by(Complaint.escalated_at.desc()).all()

    on_track_list = base_active.filter(Complaint.sla_deadline >= soon) \
        .order_by(Complaint.sla_deadline.asc()).all()

    resolved_total = Complaint.query.filter(
        Complaint.status.in_(["Resolved", "Closed"]),
        Complaint.resolved_at.isnot(None),
    ).count()

    resolved_on_time = Complaint.query.filter(
        Complaint.status.in_(["Resolved", "Closed"]),
        Complaint.resolved_at.isnot(None),
        Complaint.sla_deadline.isnot(None),
        Complaint.resolved_at <= Complaint.sla_deadline,
    ).count()

    compliance_rate = round(resolved_on_time / resolved_total * 100, 1) if resolved_total else 0

    stats = {
        "overdue": len(overdue_list),
        "approaching": len(approaching_list),
        "on_track": len(on_track_list),
        "escalated": len(escalated_list),
        "compliance_rate": compliance_rate,
        "resolved_total": resolved_total,
        "resolved_on_time": resolved_on_time,
    }

    for c in overdue_list + approaching_list + on_track_list + escalated_list:
        c._sla_info = get_sla_status(c)

    return render_template(
        "admin/sla.html",
        tab=tab,
        stats=stats,
        overdue_list=overdue_list,
        approaching_list=approaching_list,
        on_track_list=on_track_list,
        escalated_list=escalated_list,
        newly_escalated=newly_escalated,
        SLA_HOURS=SLA_HOURS,
        now_utc=now_utc,
    )


@app.route("/admin/sla/check", methods=["POST"])
@role_required("admin")
def admin_sla_check():
    count = check_and_escalate_overdue()
    if count:
        flash(f"{count} complaint(s) auto-escalated due to SLA breach.", "warning")
    else:
        flash("No overdue complaints found.", "info")
    return redirect(url_for("admin_sla"))


# ============================================================
# FEEDBACK
# ============================================================
@app.route("/complaints/<int:cid>/feedback", methods=["POST"])
@role_required("user")
def submit_feedback(cid):
    c = db.session.get(Complaint, cid) or abort(404)

    if c.user_id != current_user.id:
        abort(403)

    if c.status not in ("Resolved", "Closed"):
        flash("You can only rate complaints that have been resolved.", "warning")
        return redirect(url_for("complaint_detail", cid=c.id))

    if c.feedback:
        flash("You have already submitted feedback for this complaint.", "info")
        return redirect(url_for("complaint_detail", cid=c.id))

    rating = request.form.get("rating", type=int)
    comment = request.form.get("comment", "").strip()

    if not rating or rating < 1 or rating > 5:
        flash("Please select a rating between 1 and 5 stars.", "danger")
        return redirect(url_for("complaint_detail", cid=c.id))

    if len(comment) > 1000:
        flash("Comment must be at most 1000 characters.", "danger")
        return redirect(url_for("complaint_detail", cid=c.id))

    fb = Feedback(
        complaint_id=c.id,
        user_id=current_user.id,
        rating=rating,
        comment=comment,
    )
    db.session.add(fb)

    notify_admins(c.id, f"{rating}★ feedback received for complaint {c.tracking_id}.")
    if c.officer_id:
        notify(c.officer_id, c.id, f"You received {rating}★ feedback on complaint {c.tracking_id}.")

    db.session.commit()
    flash(f"Thank you! Your {rating}-star feedback has been recorded.", "success")
    return redirect(url_for("complaint_detail", cid=c.id))


@app.route("/admin/feedback")
@role_required("admin")
def admin_feedback():
    page = request.args.get("page", 1, type=int)
    rating_filter = request.args.get("rating", type=int)
    officer_filter = request.args.get("officer_id", type=int)
    search = request.args.get("q", "").strip()

    q = Feedback.query.order_by(Feedback.created_at.desc())

    if rating_filter and 1 <= rating_filter <= 5:
        q = q.filter(Feedback.rating == rating_filter)
    if officer_filter:
        q = q.join(Complaint).filter(Complaint.officer_id == officer_filter)
    if search:
        like = f"%{search}%"
        q = q.join(Complaint).filter(db.or_(
            Complaint.tracking_id.like(like),
            Complaint.title.like(like),
        ))

    pagination = q.paginate(page=page, per_page=20, error_out=False)

    total = Feedback.query.count()
    avg = db.session.query(func.avg(Feedback.rating)).scalar()
    rating_counts = dict(
        db.session.query(Feedback.rating, func.count(Feedback.id))
        .group_by(Feedback.rating).all()
    )

    officers = User.query.filter_by(role="officer").order_by(User.name).all()
    officer_fb_stats = {}
    for o in officers:
        stats = db.session.query(
            func.count(Feedback.id),
            func.avg(Feedback.rating),
        ).join(Complaint, Complaint.id == Feedback.complaint_id) \
         .filter(Complaint.officer_id == o.id).first()
        officer_fb_stats[o.id] = {
            "count": stats[0] or 0,
            "avg": round(stats[1], 1) if stats[1] else 0,
        }

    return render_template(
        "admin/feedback.html",
        pagination=pagination,
        feedbacks=pagination.items,
        total=total,
        avg_rating=round(avg, 1) if avg else 0,
        rating_counts=rating_counts,
        officers=officers,
        officer_fb_stats=officer_fb_stats,
        rating_filter=rating_filter,
        officer_filter=officer_filter,
        search=search,
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================
@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    newly_escalated = check_and_escalate_overdue()

    stats = {
        "total": Complaint.query.count(),
        "pending": Complaint.query.filter_by(status="Pending").count(),
        "in_progress": Complaint.query.filter(Complaint.status.in_(["Assigned", "In Progress"])).count(),
        "resolved": Complaint.query.filter(Complaint.status.in_(["Resolved", "Closed"])).count(),
        "rejected": Complaint.query.filter_by(status="Rejected").count(),
        "today": Complaint.query.filter(func.date(Complaint.created_at) == datetime.utcnow().date()).count(),
        "users": User.query.filter_by(role="user").count(),
        "officers": User.query.filter_by(role="officer", is_active=True).count(),
        "escalated": Complaint.query.filter_by(is_escalated=True).count(),
    }

    now_utc = datetime.utcnow()

    sla_overdue = (
        Complaint.query
        .filter(
            Complaint.status.notin_(["Resolved", "Closed", "Rejected"]),
            Complaint.sla_deadline.isnot(None),
            Complaint.sla_deadline < now_utc,
        )
        .order_by(Complaint.sla_deadline.asc())
        .limit(10).all()
    )

    sla_approaching = (
        Complaint.query
        .filter(
            Complaint.status.notin_(["Resolved", "Closed", "Rejected"]),
            Complaint.sla_deadline.isnot(None),
            Complaint.sla_deadline >= now_utc,
            Complaint.sla_deadline < now_utc + timedelta(hours=2),
        )
        .order_by(Complaint.sla_deadline.asc())
        .limit(10).all()
    )

    by_status = dict(db.session.query(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status).all())
    by_category = (
        db.session.query(Category.name, func.count(Complaint.id))
        .outerjoin(Complaint, Complaint.category_id == Category.id)
        .group_by(Category.name).all()
    )
    by_priority = dict(db.session.query(Complaint.priority, func.count(Complaint.id)).group_by(Complaint.priority).all())

    labels, counts = [], []
    now = datetime.utcnow()
    for i in range(5, -1, -1):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y:04d}-{m:02d}"
        labels.append(datetime(y, m, 1).strftime("%b %Y"))
        counts.append(Complaint.query.filter(func.strftime("%Y-%m", Complaint.created_at) == key).count())

    recent = Complaint.query.order_by(Complaint.created_at.desc()).limit(6).all()
    officers = User.query.filter_by(role="officer", is_active=True).all()
    workload = [(o, Complaint.query.filter(
        Complaint.officer_id == o.id,
        Complaint.status.in_(["Assigned", "In Progress"])).count()) for o in officers]
    avg_rating = db.session.query(func.avg(Feedback.rating)).scalar()

    return render_template(
        "admin/dashboard.html",
        stats=stats, by_status=by_status,
        by_category=by_category, by_priority=by_priority,
        trend_labels=labels, trend_counts=counts, recent=recent,
        workload=workload,
        avg_rating=round(avg_rating, 1) if avg_rating else 0,
        sla_overdue=sla_overdue,
        sla_approaching=sla_approaching,
        newly_escalated=newly_escalated,
        now_utc=now_utc,
    )


# ============================================================
# ADMIN — USERS
# ============================================================
@app.route("/admin/users", methods=["GET", "POST"])
@role_required("admin")
def admin_users():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        department = request.form.get("department", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "officer")

        errors = []
        if len(name) < 3:
            errors.append("Name must be at least 3 characters long.")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", email):
            errors.append("Please enter a valid email.")
        if phone and (not phone.isdigit() or len(phone) != 11):
            errors.append("Phone number must be exactly 11 digits.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters long.")
        if role not in ("officer", "admin"):
            errors.append("Please select a valid role.")
        if email and User.query.filter_by(email=email).first():
            errors.append("This email is already in use.")

        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            u = User(name=name, email=email, phone=phone,
                     department=department, role=role)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash(f"{role.capitalize()} created successfully.", "success")
        return redirect(url_for("admin_users"))

    role_filter = request.args.get("role", "")
    search = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()

    q = User.query
    if role_filter in ROLES:
        q = q.filter(User.role == role_filter)
    if status_filter == "active":
        q = q.filter(User.is_active.is_(True))
    elif status_filter == "inactive":
        q = q.filter(User.is_active.is_(False))
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(
            User.name.like(like),
            User.email.like(like),
            User.phone.like(like),
            User.department.like(like),
        ))

    users = q.order_by(User.created_at.desc()).all()

    stats = {
        "total": User.query.count(),
        "users": User.query.filter_by(role="user").count(),
        "officers": User.query.filter_by(role="officer", is_active=True).count(),
        "admins": User.query.filter_by(role="admin").count(),
        "inactive": User.query.filter_by(is_active=False).count(),
    }

    return render_template("admin/users.html", users=users,
                           role_filter=role_filter, search=search,
                           status_filter=status_filter, stats=stats)


@app.route("/admin/users/<int:uid>/edit", methods=["POST"])
@role_required("admin")
def edit_user(uid):
    u = db.session.get(User, uid) or abort(404)

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    department = request.form.get("department", "").strip()
    new_role = request.form.get("role", u.role).strip()

    errors = []
    if len(name) < 3:
        errors.append("Name must be at least 3 characters long.")
    if phone and (not phone.isdigit() or len(phone) != 11):
        errors.append("Phone number must be exactly 11 digits.")
    if new_role not in ROLES:
        errors.append("Invalid role.")
    if u.id == current_user.id and new_role != "admin":
        errors.append("You cannot change your own admin role.")

    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(url_for("admin_users"))

    u.name = name
    u.phone = phone
    u.department = department
    u.role = new_role
    db.session.commit()
    flash(f"User '{u.name}' updated successfully.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:uid>/reset-password", methods=["POST"])
@role_required("admin")
def reset_user_password(uid):
    u = db.session.get(User, uid) or abort(404)

    new_password = request.form.get("new_password", "").strip()
    if len(new_password) < 6:
        flash("Password must be at least 6 characters long.", "danger")
        return redirect(url_for("admin_users"))

    u.set_password(new_password)
    db.session.commit()

    notify(u.id, None, f"Your password has been reset by admin. New password: {new_password}")
    flash(f"Password reset for '{u.name}'. Share this password securely: {new_password}", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:uid>/delete", methods=["POST"])
@role_required("admin")
def delete_user(uid):
    u = db.session.get(User, uid) or abort(404)

    if u.id == current_user.id:
        flash("You cannot delete your own account.", "warning")
        return redirect(url_for("admin_users"))

    has_complaints = Complaint.query.filter_by(user_id=u.id).count()
    has_assignments = Complaint.query.filter_by(officer_id=u.id).count()

    if has_complaints or has_assignments:
        flash(
            f"Cannot delete '{u.name}' — has {has_complaints} complaint(s) "
            f"and {has_assignments} assigned complaint(s). Deactivate instead.",
            "warning"
        )
        return redirect(url_for("admin_users"))

    db.session.delete(u)
    db.session.commit()
    flash(f"User '{u.name}' deleted successfully.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:uid>/toggle", methods=["POST"])
@role_required("admin")
def toggle_user(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.id == current_user.id:
        flash("You cannot deactivate your own account.", "warning")
        return redirect(url_for("admin_users"))
    u.is_active = not u.is_active
    db.session.commit()
    flash(f"Account has been {'activated' if u.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin_users"))


# ============================================================
# ADMIN — CATEGORIES
# ============================================================
@app.route("/admin/categories", methods=["GET", "POST"])
@role_required("admin")
def admin_categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if len(name) < 2:
            flash("Category name must be at least 2 characters long.", "danger")
        elif Category.query.filter_by(name=name).first():
            flash("This category already exists.", "warning")
        else:
            db.session.add(Category(name=name, description=description))
            db.session.commit()
            flash("Category added.", "success")
        return redirect(url_for("admin_categories"))

    search = request.args.get("q", "").strip()

    q = Category.query
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(
            Category.name.like(like),
            Category.description.like(like),
        ))

    categories = q.order_by(Category.name).all()
    counts = dict(
        db.session.query(Complaint.category_id, func.count(Complaint.id))
        .group_by(Complaint.category_id).all()
    )

    return render_template("admin/categories.html", categories=categories, counts=counts, search=search)


@app.route("/admin/categories/<int:cid>/edit", methods=["POST"])
@role_required("admin")
def edit_category(cid):
    cat = db.session.get(Category, cid) or abort(404)

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    if len(name) < 2:
        flash("Category name must be at least 2 characters long.", "danger")
        return redirect(url_for("admin_categories"))

    existing = Category.query.filter(Category.name == name, Category.id != cat.id).first()
    if existing:
        flash("Another category with this name already exists.", "warning")
        return redirect(url_for("admin_categories"))

    cat.name = name
    cat.description = description
    db.session.commit()
    flash(f"Category '{cat.name}' updated successfully.", "success")
    return redirect(url_for("admin_categories"))


@app.route("/admin/categories/<int:cid>/delete", methods=["POST"])
@role_required("admin")
def delete_category(cid):
    cat = db.session.get(Category, cid) or abort(404)
    if Complaint.query.filter_by(category_id=cat.id).first():
        flash("Cannot delete this category as it has associated complaints.", "warning")
    else:
        db.session.delete(cat)
        db.session.commit()
        flash("Category deleted.", "success")
    return redirect(url_for("admin_categories"))


# ============================================================
# OFFICER DASHBOARD
# ============================================================
@app.route("/officer/dashboard")
@role_required("officer")
def officer_dashboard():
    mine = Complaint.query.filter_by(officer_id=current_user.id)
    stats = {
        "assigned": mine.count(),
        "active": mine.filter(Complaint.status.in_(["Assigned", "In Progress"])).count(),
        "resolved": mine.filter(Complaint.status.in_(["Resolved", "Closed"])).count(),
        "urgent": mine.filter(
            Complaint.priority.in_(["High", "Urgent"]),
            Complaint.status.in_(["Assigned", "In Progress"])).count(),
    }
    by_status = dict(
        db.session.query(Complaint.status, func.count(Complaint.id))
        .filter(Complaint.officer_id == current_user.id)
        .group_by(Complaint.status).all()
    )
    recent = mine.order_by(Complaint.created_at.desc()).limit(6).all()
    return render_template("officer/dashboard.html", stats=stats, by_status=by_status, recent=recent)


# ============================================================
# NOTIFICATIONS
# ============================================================
@app.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(100).all()
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return render_template("notifications.html", items=items)


# ============================================================
# PROFILE
# ============================================================
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "profile":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            address = request.form.get("address", "").strip()

            errors = []
            if len(name) < 3:
                errors.append("Name must be at least 3 characters long.")
            elif len(name) > 120:
                errors.append("Name is too long (maximum 120 characters).")

            if phone:
                if not phone.isdigit() or len(phone) != 11:
                    errors.append("Phone number must be exactly 11 digits.")

            if len(address) > 255:
                errors.append("Address is too long (maximum 255 characters).")

            if errors:
                for e in errors:
                    flash(e, "danger")
            else:
                current_user.name = name
                current_user.phone = phone
                current_user.address = address
                db.session.commit()
                flash("Profile updated successfully.", "success")

            return redirect(url_for("profile"))

        elif action == "password":
            old = request.form.get("old_password", "")
            new = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")

            if not current_user.check_password(old):
                flash("Current password is incorrect.", "danger")
            elif len(new) < 6:
                flash("New password must be at least 6 characters long.", "danger")
            elif new != confirm:
                flash("New passwords do not match.", "danger")
            elif new == old:
                flash("New password must be different from the current one.", "warning")
            else:
                current_user.set_password(new)
                db.session.commit()
                flash("Password changed successfully.", "success")

            return redirect(url_for("profile"))

    stats = {}

    if current_user.role == "user":
        base = Complaint.query.filter_by(user_id=current_user.id)
        stats = {
            "total": base.count(),
            "resolved": base.filter(Complaint.status.in_(["Resolved", "Closed"])).count(),
            "pending": base.filter(Complaint.status.in_(["Pending", "In Review", "Assigned", "In Progress"])).count(),
            "pending_feedback": base.filter(Complaint.status.in_(["Resolved", "Closed"])).filter(~Complaint.feedback.has()).count(),
        }

    elif current_user.role == "officer":
        base = Complaint.query.filter_by(officer_id=current_user.id)
        avg = (
            db.session.query(func.avg(Feedback.rating))
            .join(Complaint, Complaint.id == Feedback.complaint_id)
            .filter(Complaint.officer_id == current_user.id)
            .scalar()
        )
        stats = {
            "assigned": base.count(),
            "resolved": base.filter(Complaint.status.in_(["Resolved", "Closed"])).count(),
            "active": base.filter(Complaint.status.in_(["Assigned", "In Progress"])).count(),
            "avg_rating": round(avg, 1) if avg else 0,
        }

    else:
        stats = {
            "total_complaints": Complaint.query.count(),
            "total_users": User.query.filter_by(role="user").count(),
            "total_officers": User.query.filter_by(role="officer", is_active=True).count(),
        }

    return render_template("profile.html", stats=stats)


# ============================================================
# REPORTS
# ============================================================
def _report_query():
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    status = request.args.get("status", "")
    q = Complaint.query
    if start:
        try:
            q = q.filter(Complaint.created_at >= datetime.strptime(start, "%Y-%m-%d"))
        except ValueError:
            pass
    if end:
        try:
            q = q.filter(Complaint.created_at <= datetime.strptime(end, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
        except ValueError:
            pass
    if status in STATUSES:
        q = q.filter(Complaint.status == status)
    return q, start, end, status


@app.route("/admin/reports")
@role_required("admin")
def admin_reports():
    q, start, end, status_filter = _report_query()
    complaints = q.order_by(Complaint.created_at.desc()).all()

    total = len(complaints)
    resolved = sum(1 for c in complaints if c.status in ("Resolved", "Closed"))
    pending = sum(1 for c in complaints if c.status == "Pending")
    rejected = sum(1 for c in complaints if c.status == "Rejected")
    in_progress = sum(1 for c in complaints if c.status in ("In Review", "Assigned", "In Progress"))
    today = sum(1 for c in complaints if c.created_at.date() == datetime.utcnow().date())

    resolution_times = []
    for c in complaints:
        if c.resolved_at and c.created_at:
            delta = (c.resolved_at - c.created_at).total_seconds() / 3600
            resolution_times.append(delta)
    avg_resolution_hours = round(sum(resolution_times) / len(resolution_times), 1) if resolution_times else 0

    by_status = dict(db.session.query(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status).all())
    by_category = (
        db.session.query(Category.name, func.count(Complaint.id))
        .outerjoin(Complaint, Complaint.category_id == Category.id)
        .group_by(Category.name).all()
    )
    by_priority = dict(db.session.query(Complaint.priority, func.count(Complaint.id)).group_by(Complaint.priority).all())

    labels, counts, resolved_counts = [], [], []
    now = datetime.utcnow()
    for i in range(5, -1, -1):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y:04d}-{m:02d}"
        month_q = Complaint.query.filter(func.strftime("%Y-%m", Complaint.created_at) == key)
        labels.append(datetime(y, m, 1).strftime("%b %Y"))
        counts.append(month_q.count())
        resolved_counts.append(month_q.filter(Complaint.status.in_(["Resolved", "Closed"])).count())

    daily_labels, daily_counts = [], []
    for i in range(29, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        cnt = Complaint.query.filter(func.date(Complaint.created_at) == day.date()).count()
        daily_labels.append(day.strftime("%d %b"))
        daily_counts.append(cnt)

    officers = User.query.filter_by(role="officer", is_active=True).all()
    officer_perf = []
    for o in officers:
        total_o = Complaint.query.filter_by(officer_id=o.id).count()
        resolved_o = Complaint.query.filter(Complaint.officer_id == o.id, Complaint.status.in_(["Resolved", "Closed"])).count()
        avg_rating_o = db.session.query(func.avg(Feedback.rating)).join(Complaint, Complaint.id == Feedback.complaint_id).filter(Complaint.officer_id == o.id).scalar()
        officer_perf.append({
            "officer": o, "total": total_o, "resolved": resolved_o,
            "rate": round(resolved_o / total_o * 100, 1) if total_o else 0,
            "rating": round(avg_rating_o, 1) if avg_rating_o else 0,
        })
    officer_perf.sort(key=lambda x: x["resolved"], reverse=True)

    avg_rating = db.session.query(func.avg(Feedback.rating)).scalar()
    feedback_count = Feedback.query.count()
    rating_dist = dict(db.session.query(Feedback.rating, func.count(Feedback.id)).group_by(Feedback.rating).all())

    # ✅ Complaints Data Table এর জন্য পেজিনেশন যুক্ত করা হলো
    page = request.args.get("page", 1, type=int)
    complaints_pagination = q.order_by(Complaint.created_at.desc()).paginate(page=page, per_page=10, error_out=False)

    return render_template(
        "admin/reports.html",
        total=total, resolved=resolved, pending=pending,
        rejected=rejected, in_progress=in_progress, today=today,
        avg_resolution_hours=avg_resolution_hours,
        by_status=by_status, by_category=by_category, by_priority=by_priority,
        trend_labels=labels, trend_counts=counts, trend_resolved=resolved_counts,
        daily_labels=daily_labels, daily_counts=daily_counts,
        officer_perf=officer_perf,
        avg_rating=round(avg_rating, 1) if avg_rating else 0,
        feedback_count=feedback_count, rating_dist=rating_dist,
        complaints=complaints, 
        complaints_pagination=complaints_pagination, # নতুন প্যারামিটার
        start=start, end=end, status=status_filter,
    )


@app.route("/admin/reports/csv")
@role_required("admin")
def report_csv():
    q, start, end, status = _report_query()
    complaints = q.order_by(Complaint.created_at.desc()).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Tracking ID", "Title", "Category", "Priority", "Status", "User", "Officer", "Location", "Created At", "Resolved At"])
    for c in complaints:
        writer.writerow([
            c.tracking_id, c.title,
            c.category.name if c.category else "-",
            c.priority, c.status,
            c.user.name if c.user else "-",
            c.officer.name if c.officer else "-",
            c.location or "-",
            c.created_at.strftime("%Y-%m-%d %H:%M"),
            c.resolved_at.strftime("%Y-%m-%d %H:%M") if c.resolved_at else "-",
        ])
    data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    return send_file(data, mimetype="text/csv", as_attachment=True, download_name=f"complaints_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv")


@app.route("/admin/reports/pdf")
@role_required("admin")
def report_pdf():
    if not REPORTLAB_OK:
        flash("To generate PDF, install reportlab: pip install reportlab", "warning")
        return redirect(url_for("admin_reports"))
    q, start, end, status = _report_query()
    complaints = q.order_by(Complaint.created_at.desc()).all()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Online Complaint Management System", styles["Title"]),
        Paragraph(f"Complaint Report — generated {datetime.utcnow().strftime('%d %b %Y, %H:%M')}", styles["Normal"]),
        Spacer(1, 14),
    ]
    table_data = [["Tracking ID", "Title", "Category", "Priority", "Status", "Officer", "Date"]]
    for c in complaints:
        table_data.append([
            c.tracking_id,
            (c.title[:32] + "…") if len(c.title) > 32 else c.title,
            c.category.name if c.category else "-",
            c.priority, c.status,
            c.officer.name if c.officer else "-",
            c.created_at.strftime("%d-%m-%Y"),
        ])
    if len(table_data) == 1:
        story.append(Paragraph("No complaints found for the selected filters.", styles["Normal"]))
    else:
        table = Table(table_data, repeatRows=1, colWidths=[92, 118, 74, 52, 66, 72, 60])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fb")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
    story.append(Spacer(1, 16))
    story.append(Paragraph(f"Total complaints: {len(complaints)}", styles["Heading3"]))
    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=f"complaints_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.pdf")


# ============================================================
# ERROR HANDLERS
# ============================================================
@app.errorhandler(403)
def err_403(e):
    return render_template("errors/error.html", code=403, message="You do not have permission to access this page."), 403

@app.errorhandler(404)
def err_404(e):
    return render_template("errors/error.html", code=404, message="Page not found."), 404

@app.errorhandler(413)
def err_413(e):
    return render_template("errors/error.html", code=413, message="File size must be less than 5 MB."), 413

@app.errorhandler(500)
def err_500(e):
    db.session.rollback()
    try:
        return render_template("errors/error.html", code=500, message="A server error has occurred."), 500
    except Exception:
        return "<h1 style='text-align:center; margin-top:50px;'>500 - Internal Server Error</h1>", 500


# ============================================================
# BOOTSTRAP — Dialect-aware Auto-migration
# ============================================================
def bootstrap():
    with app.app_context():
        db.create_all()
        from sqlalchemy import text, inspect
        import warnings
        from sqlalchemy.exc import SAWarning

        dialect = db.engine.dialect.name
        if dialect == "sqlite":
            migrations = [
                ("sla_deadline",      "ALTER TABLE complaints ADD COLUMN sla_deadline DATETIME"),
                ("is_escalated",      "ALTER TABLE complaints ADD COLUMN is_escalated BOOLEAN DEFAULT 0"),
                ("escalated_at",      "ALTER TABLE complaints ADD COLUMN escalated_at DATETIME"),
                ("duplicate_of",      "ALTER TABLE complaints ADD COLUMN duplicate_of INTEGER"),
                ("is_duplicate_flag", "ALTER TABLE complaints ADD COLUMN is_duplicate_flag BOOLEAN DEFAULT 0"),
            ]
        else:
            migrations = [
                ("sla_deadline",      "ALTER TABLE complaints ADD COLUMN sla_deadline DATETIME NULL"),
                ("is_escalated",      "ALTER TABLE complaints ADD COLUMN is_escalated TINYINT(1) DEFAULT 0"),
                ("escalated_at",      "ALTER TABLE complaints ADD COLUMN escalated_at DATETIME NULL"),
                ("duplicate_of",      "ALTER TABLE complaints ADD COLUMN duplicate_of INT NULL"),
                ("is_duplicate_flag", "ALTER TABLE complaints ADD COLUMN is_duplicate_flag TINYINT(1) DEFAULT 0"),
            ]

        try:
            inspector = inspect(db.engine)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SAWarning)
                existing_cols = {c["name"] for c in inspector.get_columns("complaints")}

            with db.engine.connect() as conn:
                for col_name, stmt in migrations:
                    if col_name not in existing_cols:
                        try:
                            conn.execute(text(stmt))
                            conn.commit()
                            print(f"[MIGRATE] Added column: {col_name} ({dialect})")
                        except Exception as e:
                            print(f"[MIGRATE] Skip {col_name}: {e}")
                            conn.rollback()
        except Exception as e:
            print(f"[MIGRATE] Column check failed: {e}")

        if not User.query.filter_by(role="admin").first():
            admin = User(name="Mahinur Rahman", email="mahinurrahman1631@gmail.com", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)

        if not User.query.filter_by(role="officer").first():
            officer = User(name="Demo Officer", email="officer@cms.local", role="officer", department="Roads & Highways")
            officer.set_password("officer123")
            db.session.add(officer)

        if not User.query.filter_by(email="t@gmail.com").first():
            test_user = User(name="Test User", email="t@gmail.com", phone="01712345678", role="user")
            test_user.set_password("user123")
            db.session.add(test_user)

        if Category.query.count() == 0:
            for name, desc in [
                ("Road & Infrastructure", "Roads, drains, bridges related"),
                ("Electricity", "Power supply and lines related"),
                ("Water Supply", "Water and sewerage"),
                ("Sanitation", "Garbage and cleanliness"),
                ("Others", "Other complaints"),
            ]:
                db.session.add(Category(name=name, description=desc))

        db.session.commit()


if __name__ == "__main__":
    print("--- Starting Database Bootstrap ---")
    bootstrap()
    print("--- Flask Server Starting on http://127.0.0.1:5000 ---")
    app.run(host="127.0.0.1", port=5000, debug=True)
    