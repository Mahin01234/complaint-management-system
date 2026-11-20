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
                   abort, send_file, session)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func

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
        tid = "CMP-{}-{}".format(datetime.utcnow().strftime("%Y%m%d"), "".join(random.choices(string.ascii_uppercase + string.digits, k=4)))
        if not Complaint.query.filter_by(tracking_id=tid).first():
            return tid

def allowed_file(filename):
    return ("." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"])

def save_attachments(files, complaint_id):
    for f in files:
        if f and f.filename and allowed_file(f.filename):
            ext = f.filename.rsplit(".", 1)[1].lower()
            stored = "{}.{}".format(uuid.uuid4().hex, ext)
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], stored))
            original = secure_filename(f.filename) or "attachment." + ext
            db.session.add(Attachment(complaint_id=complaint_id, filename=stored, original_name=original))

def notify(user_id, complaint_id, message):
    db.session.add(Notification(user_id=user_id, complaint_id=complaint_id, message=message))

def notify_admins(complaint_id, message):
    for admin in User.query.filter_by(role="admin", is_active=True).all():
        notify(admin.id, complaint_id, message)

@app.context_processor
def inject_globals():
    unread = 0
    try:
        if current_user.is_authenticated:
            unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    except Exception:
        unread = 0  
    return dict(unread_count=unread, STATUSES=STATUSES, PRIORITIES=PRIORITIES)

@app.route("/")
def root():
    if current_user.is_authenticated:
        logout_user()
        session.clear()
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
        if tid:
            complaint = Complaint.query.filter_by(tracking_id=tid).first()
            if not complaint:
                flash("No complaint found with this Tracking ID.", "danger")
        else:
            flash("Please enter a Tracking ID.", "warning")
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
            errors['name'] = "Name must be at least 3 characters long."
        if not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", email):
            errors['email'] = "Please enter a valid email address."
        if phone and len(phone) != 11:
            errors['phone'] = "Phone number must be exactly 11 digits."
        if len(password) < 6:
            errors['password'] = "Password must be at least 6 characters long."
        if password != confirm:
            errors['confirm'] = "Passwords must match."
        if email and User.query.filter_by(email=email).first():
            errors['email'] = "This email is already registered."

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

        print("\n--- LOGIN ATTEMPT ---")
        print(f"Email: '{email}' | Role: '{selected_role}'")
        print(f"Total Users in DB: {User.query.count()}")

        if not email or not password:
            login_error = "Email and Password cannot be empty."
            print("Result: Empty fields.")
        else:
            user = User.query.filter_by(email=email).first()

            if user:
                print(f"User Found! DB Role: '{user.role}' | Active: {user.is_active}")
                print(f"Password Match: {user.check_password(password)}")
                
                if user.is_active and user.check_password(password):
                    if user.role == selected_role:
                        login_user(user, remember=bool(request.form.get("remember")))
                        session.permanent = True
                        flash(f"Welcome, {user.name}!", "success")
                        print("Status: Login SUCCESSFUL\n")
                        return redirect(url_for("dashboard_router"))
                    else:
                        login_error = f"Access Denied. You selected '{selected_role}', but your account is '{user.role}'."
                        print("Status: Login FAILED - Role Mismatch\n")
                else:
                    login_error = "Incorrect email or password, or account is inactive."
                    print("Status: Login FAILED - Wrong Password or Inactive\n")
            else:
                login_error = "Incorrect email or password, or account is inactive."
                print("Status: Login FAILED - User NOT FOUND in DB\n")

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
    response.delete_cookie('session')
    response.delete_cookie('remember_token')
    
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
        
        if not email or "@" not in email or "." not in email:
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for("forgot_password"))

        otp = str(random.randint(100000, 999999))
        
        user = User.query.filter_by(email=email, is_active=True).first()
        if user:
            user.reset_otp = otp
            user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()

        print("\n")
        print("█" * 60)
        print("█" + " " * 58 + "█")
        print(f"█  🔐 PASSWORD RESET OTP FOR: {email.ljust(28)} █")
        print(f"█  🔑 OTP CODE: {otp.center(43)} █")
        print("█" + " " * 58 + "█")
        print("█" * 60)
        print("\n")

        session['reset_email'] = email
        session['display_otp'] = otp 
        
        flash(f"An OTP has been generated for {email}! Please check the popup below.", "info")
        return redirect(url_for("verify_otp"))

    return render_template("auth/forgot_password.html")

@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if 'reset_email' not in session:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()
        
        if session.get('display_otp') == entered_otp:
            session['otp_verified'] = True
            session.pop('display_otp', None) 
            flash("OTP verified successfully. Please set a new password.", "success")
            return redirect(url_for("reset_password"))
        else:
            flash("Invalid OTP. Please try again.", "danger")

    return render_template("auth/verify_otp.html")

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if not session.get('otp_verified') or 'reset_email' not in session:
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

        user = User.query.filter_by(email=session['reset_email']).first()
        
        if user:
            user.set_password(password)
            user.reset_otp = None
            user.otp_expiry = None
            db.session.commit()
            flash("Password changed successfully. Please log in.", "success")
        else:
            flash("OTP verified! But this email is not registered, so password could not be saved in DB. (Demo Mode)", "warning")

        session.pop('reset_email', None)
        session.pop('otp_verified', None)
        
        return redirect(url_for("login"))

    return render_template("auth/reset_password.html")

# ============================================================
# USER DASHBOARD & COMPLAINTS
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
    
    by_status = dict(db.session.query(Complaint.status, func.count(Complaint.id)).filter(Complaint.user_id == current_user.id).group_by(Complaint.status).all())
    by_category = db.session.query(Category.name, func.count(Complaint.id)).join(Complaint, Complaint.category_id == Category.id).filter(Complaint.user_id == current_user.id).group_by(Category.name).all()
    
    recent = base.order_by(Complaint.created_at.desc()).limit(5).all()
    pending_feedback = base.filter(Complaint.status.in_(["Resolved", "Closed"])).filter(~Complaint.feedback.has()).all()
    recent_notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(3).all()
    
    return render_template("user/dashboard.html", stats=stats, by_status=by_status, 
                           by_category=by_category, recent=recent, pending_feedback=pending_feedback, 
                           recent_notifs=recent_notifs)

@app.route("/complaints")
@login_required
def complaints_list():
    q = Complaint.query
    if current_user.role == "user": q = q.filter(Complaint.user_id == current_user.id)
    elif current_user.role == "officer": q = q.filter(Complaint.officer_id == current_user.id)
    
    status, priority, search = request.args.get("status", "").strip(), request.args.get("priority", "").strip(), request.args.get("q", "").strip()
    if status in STATUSES: q = q.filter(Complaint.status == status)
    if priority in PRIORITIES: q = q.filter(Complaint.priority == priority)
    if search: q = q.filter(db.or_(Complaint.tracking_id.like(f"%{search}%"), Complaint.title.like(f"%{search}%"), Complaint.location.like(f"%{search}%")))
    
    pagination = q.order_by(Complaint.created_at.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=10, error_out=False)
    return render_template("complaints/list.html", pagination=pagination, complaints=pagination.items, status=status, priority=priority, search=search)

@app.route("/complaints/<int:cid>")
@login_required
def complaint_detail(cid):
    c = db.session.get(Complaint, cid) or abort(404)
    if current_user.role == "user" and c.user_id != current_user.id: abort(403)
    if current_user.role == "officer" and c.officer_id != current_user.id: abort(403)
    officers = User.query.filter_by(role="officer", is_active=True).order_by(User.name).all() if current_user.role == "admin" else []
    return render_template("complaints/detail.html", c=c, officers=officers)

@app.route("/complaints/new", methods=["GET", "POST"])
@role_required("user")
def complaint_new():
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        title, description, category_id, priority, location = request.form.get("title", "").strip(), request.form.get("description", "").strip(), request.form.get("category_id", type=int), request.form.get("priority", "Medium"), request.form.get("location", "").strip()
        errors = []
        if len(title) < 5: errors.append("Title must be at least 5 characters long.")
        if len(description) < 20: errors.append("Description must be at least 20 characters long.")
        if not category_id or not db.session.get(Category, category_id): errors.append("Please select a category.")
        if priority not in PRIORITIES: errors.append("Please select a valid priority.")
        if errors:
            for e in errors: flash(e, "danger")
            return render_template("complaints/form.html", categories=categories)
        
        complaint = Complaint(tracking_id=generate_tracking_id(), user_id=current_user.id, category_id=category_id, title=title, description=description, location=location, priority=priority, status="Pending")
        db.session.add(complaint); db.session.flush()
        save_attachments(request.files.getlist("attachments"), complaint.id)
        db.session.add(ComplaintUpdate(complaint_id=complaint.id, updated_by=current_user.id, status="Pending", message="Complaint submitted successfully."))
        notify_admins(complaint.id, f"New complaint submitted: {complaint.tracking_id} — {complaint.title}")
        db.session.commit()
        flash(f"Complaint submitted. Tracking ID: {complaint.tracking_id}", "success")
        return redirect(url_for("complaint_detail", cid=complaint.id))
    return render_template("complaints/form.html", categories=categories)

@app.route("/complaints/<int:cid>/assign", methods=["POST"])
@role_required("admin")
def assign_officer(cid):
    c = db.session.get(Complaint, cid) or abort(404)
    officer = User.query.filter_by(id=request.form.get("officer_id", type=int), role="officer", is_active=True).first()
    if not officer: flash("Please select a valid officer.", "danger"); return redirect(url_for("complaint_detail", cid=c.id))
    c.officer_id = officer.id; c.status = "Assigned"
    db.session.add(Assignment(complaint_id=c.id, officer_id=officer.id, assigned_by=current_user.id, notes=request.form.get("notes", "").strip()))
    db.session.add(ComplaintUpdate(complaint_id=c.id, updated_by=current_user.id, status="Assigned", message=f"Assigned to {officer.name}."))
    notify(officer.id, c.id, f"You have been assigned a new complaint: {c.tracking_id}")
    notify(c.user_id, c.id, f"Your complaint {c.tracking_id} has been sent to an officer.")
    db.session.commit()
    flash("Officer assigned successfully.", "success")
    return redirect(url_for("complaint_detail", cid=c.id))

@app.route("/complaints/<int:cid>/status", methods=["POST"])
@role_required("admin", "officer")
def update_status(cid):
    c = db.session.get(Complaint, cid) or abort(404)
    new_status, message = request.form.get("status", ""), request.form.get("message", "").strip()
    if new_status not in STATUSES: abort(400)
    if current_user.role == "officer" and (c.officer_id != current_user.id or new_status not in ("In Progress", "Resolved")): abort(403)
    old_status = c.status; c.status = new_status
    if new_status in ("Resolved", "Closed") and not c.resolved_at: c.resolved_at = datetime.utcnow()
    db.session.add(ComplaintUpdate(complaint_id=c.id, updated_by=current_user.id, status=new_status, message=message or f"Status changed from {old_status} to {new_status}."))
    notify(c.user_id, c.id, f"The status of your complaint {c.tracking_id} is now: {new_status}")
    db.session.commit()
    flash("Status updated successfully.", "success")
    return redirect(url_for("complaint_detail", cid=c.id))

@app.route("/complaints/<int:cid>/feedback", methods=["POST"])
@role_required("user")
def submit_feedback(cid):
    c = db.session.get(Complaint, cid) or abort(404)
    if c.user_id != current_user.id: abort(403)
    if c.status not in ("Resolved", "Closed"): flash("Complaint is not resolved yet.", "warning"); return redirect(url_for("complaint_detail", cid=c.id))
    if c.feedback: flash("You have already submitted feedback.", "info"); return redirect(url_for("complaint_detail", cid=c.id))
    rating, comment = request.form.get("rating", type=int), request.form.get("comment", "").strip()
    if not rating or rating < 1 or rating > 5: flash("Please provide a rating between 1 and 5.", "danger"); return redirect(url_for("complaint_detail", cid=c.id))
    db.session.add(Feedback(complaint_id=c.id, user_id=current_user.id, rating=rating, comment=comment))
    notify_admins(c.id, f"{rating}★ feedback received for complaint {c.tracking_id}.")
    db.session.commit()
    flash("Thank you for your feedback!", "success")
    return redirect(url_for("complaint_detail", cid=c.id))

# ============================================================
# ADMIN & OFFICER DASHBOARDS
# ============================================================
@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    stats = {
        "total": Complaint.query.count(), 
        "pending": Complaint.query.filter_by(status="Pending").count(), 
        "in_progress": Complaint.query.filter(Complaint.status.in_(["Assigned", "In Progress"])).count(), 
        "resolved": Complaint.query.filter(Complaint.status.in_(["Resolved", "Closed"])).count(), 
        "rejected": Complaint.query.filter_by(status="Rejected").count(), 
        "today": Complaint.query.filter(func.date(Complaint.created_at) == datetime.utcnow().date()).count(), 
        "users": User.query.filter_by(role="user").count(), 
        "officers": User.query.filter_by(role="officer", is_active=True).count()
    }
    by_status = dict(db.session.query(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status).all())
    by_category = db.session.query(Category.name, func.count(Complaint.id)).outerjoin(Complaint, Complaint.category_id == Category.id).group_by(Category.name).all()
    by_priority = dict(db.session.query(Complaint.priority, func.count(Complaint.id)).group_by(Complaint.priority).all())
    
    labels, counts = [], []
    today = datetime.utcnow().replace(day=1)
    for i in range(5, -1, -1):
        month = (today - timedelta(days=31 * i)).replace(day=1)
        key = month.strftime("%Y-%m")
        labels.append(month.strftime("%b %Y"))
        counts.append(Complaint.query.filter(func.strftime("%Y-%m", Complaint.created_at) == key).count())
        
    recent = Complaint.query.order_by(Complaint.created_at.desc()).limit(6).all()
    officers = User.query.filter_by(role="officer", is_active=True).all()
    workload = [(o, Complaint.query.filter(Complaint.officer_id == o.id, Complaint.status.in_(["Assigned", "In Progress"])).count()) for o in officers]
    avg_rating = db.session.query(func.avg(Feedback.rating)).scalar()
    
    return render_template("admin/dashboard.html", stats=stats, by_status=by_status, by_category=by_category, by_priority=by_priority, trend_labels=labels, trend_counts=counts, recent=recent, workload=workload, avg_rating=round(avg_rating, 1) if avg_rating else 0)

@app.route("/admin/users", methods=["GET", "POST"])
@role_required("admin")
def admin_users():
    if request.method == "POST":
        name, email, phone, department, password, role = request.form.get("name", "").strip(), request.form.get("email", "").strip().lower(), request.form.get("phone", "").strip(), request.form.get("department", "").strip(), request.form.get("password", ""), request.form.get("role", "officer")
        errors = []
        if len(name) < 3: errors.append("Name must be at least 3 characters long.")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", email): errors.append("Please enter a valid email.")
        if len(password) < 6: errors.append("Password must be at least 6 characters long.")
        if role not in ("officer", "admin"): errors.append("Please select a valid role.")
        if email and User.query.filter_by(email=email).first(): errors.append("This email is already in use.")
        if errors:
            for e in errors: flash(e, "danger")
        else:
            u = User(name=name, email=email, phone=phone, department=department, role=role)
            u.set_password(password); db.session.add(u); db.session.commit()
            flash(f"{role.capitalize()} created successfully.", "success")
        return redirect(url_for("admin_users"))
    role_filter = request.args.get("role", "")
    q = User.query.filter(User.role == role_filter) if role_filter in ROLES else User.query
    users = q.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users, role_filter=role_filter)

@app.route("/admin/users/<int:uid>/toggle", methods=["POST"])
@role_required("admin")
def toggle_user(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.id == current_user.id: flash("You cannot deactivate your own account.", "warning"); return redirect(url_for("admin_users"))
    u.is_active = not u.is_active; db.session.commit()
    flash(f"Account has been {'activated' if u.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/categories", methods=["GET", "POST"])
@role_required("admin")
def admin_categories():
    if request.method == "POST":
        name, description = request.form.get("name", "").strip(), request.form.get("description", "").strip()
        if len(name) < 2: flash("Category name must be at least 2 characters long.", "danger")
        elif Category.query.filter_by(name=name).first(): flash("This category already exists.", "warning")
        else:
            db.session.add(Category(name=name, description=description)); db.session.commit()
            flash("Category added.", "success")
        return redirect(url_for("admin_categories"))
    categories = Category.query.order_by(Category.name).all()
    counts = dict(db.session.query(Complaint.category_id, func.count(Complaint.id)).group_by(Complaint.category_id).all())
    return render_template("admin/categories.html", categories=categories, counts=counts)

@app.route("/admin/categories/<int:cid>/delete", methods=["POST"])
@role_required("admin")
def delete_category(cid):
    cat = db.session.get(Category, cid) or abort(404)
    if Complaint.query.filter_by(category_id=cat.id).first(): flash("Cannot delete this category as it has associated complaints.", "warning")
    else:
        db.session.delete(cat); db.session.commit()
        flash("Category deleted.", "success")
    return redirect(url_for("admin_categories"))

@app.route("/officer/dashboard")
@role_required("officer")
def officer_dashboard():
    mine = Complaint.query.filter_by(officer_id=current_user.id)
    stats = {"assigned": mine.count(), "active": mine.filter(Complaint.status.in_(["Assigned", "In Progress"])).count(), "resolved": mine.filter(Complaint.status.in_(["Resolved", "Closed"])).count(), "urgent": mine.filter(Complaint.priority.in_(["High", "Urgent"]), Complaint.status.in_(["Assigned", "In Progress"])).count()}
    by_status = dict(db.session.query(Complaint.status, func.count(Complaint.id)).filter(Complaint.officer_id == current_user.id).group_by(Complaint.status).all())
    recent = mine.order_by(Complaint.created_at.desc()).limit(6).all()
    return render_template("officer/dashboard.html", stats=stats, by_status=by_status, recent=recent)

@app.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(100).all()
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True}); db.session.commit()
    return render_template("notifications.html", items=items)

# ============================================================
# PROFILE (Address Added)
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
            if len(name) < 3: 
                flash("Name must be at least 3 characters long.", "danger")
            else:
                current_user.name = name
                current_user.phone = phone
                current_user.address = address
                db.session.commit()
                flash("Profile updated.", "success")
        elif action == "password":
            old, new, confirm = request.form.get("old_password", ""), request.form.get("new_password", ""), request.form.get("confirm_password", "")
            if not current_user.check_password(old): flash("Current password is incorrect.", "danger")
            elif len(new) < 6: flash("New password must be at least 6 characters long.", "danger")
            elif new != confirm: flash("New passwords must match.", "danger")
            else:
                current_user.set_password(new); db.session.commit()
                flash("Password changed.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html")

# ============================================================
# REPORTS
# ============================================================
def _report_query():
    start, end, status = request.args.get("start", ""), request.args.get("end", ""), request.args.get("status", "")
    q = Complaint.query
    if start:
        try: q = q.filter(Complaint.created_at >= datetime.strptime(start, "%Y-%m-%d"))
        except ValueError: pass
    if end:
        try: q = q.filter(Complaint.created_at <= datetime.strptime(end, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
        except ValueError: pass
    if status in STATUSES: q = q.filter(Complaint.status == status)
    return q, start, end, status

@app.route("/admin/reports")
@role_required("admin")
def admin_reports():
    q, start, end, status = _report_query()
    complaints = q.order_by(Complaint.created_at.desc()).all()
    by_status = dict(db.session.query(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status).all())
    by_category = db.session.query(Category.name, func.count(Complaint.id)).outerjoin(Complaint, Complaint.category_id == Category.id).group_by(Category.name).all()
    by_priority = dict(db.session.query(Complaint.priority, func.count(Complaint.id)).group_by(Complaint.priority).all())
    avg_rating = db.session.query(func.avg(Feedback.rating)).scalar()
    return render_template("admin/reports.html", complaints=complaints, by_status=by_status, by_category=by_category, by_priority=by_priority, avg_rating=round(avg_rating, 1) if avg_rating else 0, start=start, end=end, status=status)

@app.route("/admin/reports/csv")
@role_required("admin")
def report_csv():
    q, start, end, status = _report_query()
    complaints = q.order_by(Complaint.created_at.desc()).all()
    buf = io.StringIO(); writer = csv.writer(buf)
    writer.writerow(["Tracking ID", "Title", "Category", "Priority", "Status", "User", "Officer", "Location", "Created At", "Resolved At"])
    for c in complaints:
        writer.writerow([c.tracking_id, c.title, c.category.name if c.category else "-", c.priority, c.status, c.user.name if c.user else "-", c.officer.name if c.officer else "-", c.location or "-", c.created_at.strftime("%Y-%m-%d %H:%M"), c.resolved_at.strftime("%Y-%m-%d %H:%M") if c.resolved_at else "-"])
    data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    return send_file(data, mimetype="text/csv", as_attachment=True, download_name=f"complaints_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv")

@app.route("/admin/reports/pdf")
@role_required("admin")
def report_pdf():
    if not REPORTLAB_OK: flash("To generate PDF, install reportlab: pip install reportlab", "warning"); return redirect(url_for("admin_reports"))
    q, start, end, status = _report_query()
    complaints = q.order_by(Complaint.created_at.desc()).all()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = [Paragraph("Online Complaint Management System", styles["Title"]), Paragraph(f"Complaint Report — generated {datetime.utcnow().strftime('%d %b %Y, %H:%M')}", styles["Normal"]), Spacer(1, 14)]
    table_data = [["Tracking ID", "Title", "Category", "Priority", "Status", "Officer", "Date"]]
    for c in complaints: table_data.append([c.tracking_id, (c.title[:32] + "…") if len(c.title) > 32 else c.title, c.category.name if c.category else "-", c.priority, c.status, c.officer.name if c.officer else "-", c.created_at.strftime("%d-%m-%Y")])
    if len(table_data) == 1: story.append(Paragraph("No complaints found for the selected filters.", styles["Normal"]))
    else:
        table = Table(table_data, repeatRows=1, colWidths=[92, 118, 74, 52, 66, 72, 60])
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fb")]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("PADDING", (0, 0), (-1, -1), 4)]))
        story.append(table)
    story.append(Spacer(1, 16)); story.append(Paragraph(f"Total complaints: {len(complaints)}", styles["Heading3"]))
    doc.build(story); buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=f"complaints_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.pdf")

# ============================================================
# ERROR HANDLERS & BOOTSTRAP
# ============================================================
@app.errorhandler(403)
def err_403(e): return render_template("errors/error.html", code=403, message="You do not have permission to access this page."), 403
@app.errorhandler(404)
def err_404(e): return render_template("errors/error.html", code=404, message="Page not found."), 404
@app.errorhandler(413)
def err_413(e): return render_template("errors/error.html", code=413, message="File size must be less than 5 MB."), 413
@app.errorhandler(500)
def err_500(e):
    db.session.rollback()
    try: return render_template("errors/error.html", code=500, message="A server error has occurred."), 500
    except Exception: return "<h1 style='text-align:center; margin-top:50px;'>500 - Internal Server Error</h1>", 500

def bootstrap():
    with app.app_context():
        # ⚠️ ডাটাবেস নতুন করে তৈরি করার জন্য (শুধু একবার রান হবে)
        db.drop_all() 
        db.create_all() 
        
        # ১. ডিফল্ট অ্যাডমিন তৈরি
        if not User.query.filter_by(role="admin").first():
            admin = User(name="Mahinur Rahman", email="mahinurrahman1631@gmail.com", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            
        # ২. ডিফল্ট অফিসার তৈরি
        if not User.query.filter_by(role="officer").first():
            officer = User(name="Demo Officer", email="officer@cms.local", role="officer", department="Roads & Highways")
            officer.set_password("officer123")
            db.session.add(officer)
            
        # ৩. আপনার চাওয়া ডিফল্ট ইউজার তৈরি (t@gmail.com)
        if not User.query.filter_by(email="t@gmail.com").first():
            test_user = User(name="Test User", email="t@gmail.com", phone="01712345678", role="user")
            test_user.set_password("user123")
            db.session.add(test_user)
            
        # ক্যাটাগরি তৈরি
        if Category.query.count() == 0:
            for name, desc in [("Road & Infrastructure", "Roads, drains, bridges related"), 
                               ("Electricity", "Power supply and lines related"), 
                               ("Water Supply", "Water and sewerage"), 
                               ("Sanitation", "Garbage and cleanliness"), 
                               ("Others", "Other complaints")]:
                db.session.add(Category(name=name, description=desc))
                
        db.session.commit()

if __name__ == "__main__":
    bootstrap()
    app.run(debug=True)