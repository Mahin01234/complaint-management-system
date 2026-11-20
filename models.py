# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

STATUSES = ["Pending", "In Review", "Assigned", "In Progress", "Resolved", "Closed", "Rejected"]
PRIORITIES = ["Low", "Medium", "High", "Urgent"]
ROLES = ["user", "officer", "admin"]

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user", index=True)
    department = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reset_otp = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Complaint(db.Model):
    __tablename__ = "complaints"
    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(30), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    officer_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(200))
    priority = db.Column(db.String(20), default="Medium", index=True)
    status = db.Column(db.String(30), default="Pending", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    sla_deadline = db.Column(db.DateTime, nullable=True, index=True)
    is_escalated = db.Column(db.Boolean, default=False, index=True)
    escalated_at = db.Column(db.DateTime, nullable=True)
    duplicate_of = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=True)
    is_duplicate_flag = db.Column(db.Boolean, default=False, index=True)

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("my_complaints", lazy="dynamic"))
    officer = db.relationship("User", foreign_keys=[officer_id], backref=db.backref("assigned_complaints", lazy="dynamic"))
    category = db.relationship("Category", backref=db.backref("complaints", lazy="dynamic"))
    updates = db.relationship("ComplaintUpdate", back_populates="complaint", cascade="all, delete-orphan")
    attachments = db.relationship("Attachment", back_populates="complaint", cascade="all, delete-orphan")
    assignments = db.relationship("Assignment", back_populates="complaint", cascade="all, delete-orphan")
    feedback = db.relationship("Feedback", back_populates="complaint", uselist=False, cascade="all, delete-orphan")

    @property
    def status_badge(self):
        return {"Pending": "secondary", "In Review": "info", "Assigned": "primary", "In Progress": "warning", "Resolved": "success", "Closed": "dark", "Rejected": "danger"}.get(self.status, "secondary")

    @property
    def priority_badge(self):
        return {"Low": "secondary", "Medium": "info", "High": "warning", "Urgent": "danger"}.get(self.priority, "secondary")

class Assignment(db.Model):
    __tablename__ = "assignments"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    officer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    notes = db.Column(db.Text)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    complaint = db.relationship("Complaint", back_populates="assignments")
    officer = db.relationship("User", foreign_keys=[officer_id])
    assigner = db.relationship("User", foreign_keys=[assigned_by])

class ComplaintUpdate(db.Model):
    __tablename__ = "complaint_updates"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    status = db.Column(db.String(30))
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    complaint = db.relationship("Complaint", back_populates="updates")
    author = db.relationship("User", foreign_keys=[updated_by])

class Attachment(db.Model):
    __tablename__ = "attachments"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    complaint = db.relationship("Complaint", back_populates="attachments")

class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id", ondelete="CASCADE"))
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref=db.backref("notifications", lazy="dynamic"))
    complaint = db.relationship("Complaint")

class Feedback(db.Model):
    __tablename__ = "feedback"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id", ondelete="CASCADE"), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    complaint = db.relationship("Complaint", back_populates="feedback")
    user = db.relationship("User")
    