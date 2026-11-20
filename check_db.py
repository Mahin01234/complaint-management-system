from app import app, db
from models import Assignment

with app.app_context():
    assignments = Assignment.query.all()
    print(f"Total Assignments in DB: {len(assignments)}")
    for a in assignments:
        print(f"Complaint ID: {a.complaint_id}, Officer ID: {a.officer_id}, Assigned At: {a.assigned_at}")
        