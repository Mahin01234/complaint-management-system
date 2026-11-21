# Complaint Management System (CMS Portal)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Flask-2.x-green?logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/Database-SQLite%20%7C%20MySQL-lightgrey" alt="Database">
  <img src="https://img.shields.io/badge/License-Academic-orange" alt="Academic Project">
</p>

A web-based **Complaint Management System** developed as an individual project for the **System Analysis and Design** course. The system helps users submit complaints, track their status, and communicate with responsible officers through a centralized platform.

## 📌 Project Overview

The Complaint Management System (CMS) is designed to simplify the complaint-handling process. It provides separate dashboards and features for users, officers, and administrators.

The system supports complaint submission, assignment, status tracking, notifications, feedback, and report generation.

## ✨ Key Features

- **User Management:** Registration, login, and role-based access control.
- **Complaint Submission:** Users can submit complaints with descriptions and attachments.
- **Complaint Tracking:** Track complaints through different stages.
- **Complaint Assignment:** Officers can manage and respond to assigned complaints.
- **Status Management:** Update complaint statuses.
- **Notifications:** In-app notifications for important updates.
- **SLA Tracking:** Track complaint deadlines and escalation.
- **Feedback System:** Users can provide feedback and ratings.
- **Reports and Analytics:** Generate complaint reports and PDF exports.
- **Responsive Interface:** Access the system from different screen sizes.

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming |
| Flask | Web framework |
| Flask-SQLAlchemy | Database ORM |
| Flask-Login | User authentication |
| SQLite | Default database |
| MySQL | Optional database |
| HTML5 | Page structure |
| CSS3 | Styling |
| JavaScript | Frontend interactions |
| Jinja2 | Template engine |
| Werkzeug | Password hashing |
| ReportLab | Optional PDF generation |
| Flask-Mail | Optional email functionality |

## 👥 User Roles

| Role | Responsibilities |
|---|---|
| User | Submit complaints, track status, receive notifications, and provide feedback |
| Officer / Responder | View assigned complaints, update status, and respond to complaints |
| Admin | Manage users, officers, complaints, assignments, and system activities |

## 📋 Complaint Status

A complaint can move through the following statuses:

`Pending → In Review → Assigned → In Progress → Resolved / Closed / Rejected`

## ⚙️ Prerequisites

Before running the project, make sure you have installed:

- Python 3.8 or higher
- pip
- Git
- A modern web browser
- MySQL (optional — only if you want to use MySQL instead of SQLite)

The project uses SQLite by default.

## 🚀 Quick Start

Follow these steps to run the project locally:

```bash
git clone https://github.com/Mahin01234/complaint-management-system.git
cd complaint-management-system
```

Install the required dependencies:

```bash
pip install flask flask-sqlalchemy flask-login werkzeug
```

Initialize the database:

```bash
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

Run the application:

```bash
python app.py
```

Open your browser and visit:

```text
http://127.0.0.1:5000/
```

## 📥 Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Mahin01234/complaint-management-system.git
```

### 2. Navigate into the Project Directory

```bash
cd complaint-management-system
```

### 3. Create a Virtual Environment (Recommended)

```bash
python -m venv venv
```

Activate the virtual environment.

**Windows:**

```bash
venv\Scripts\activate
```

**Linux / macOS:**

```bash
source venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install flask flask-sqlalchemy flask-login werkzeug
```

Optional packages:

```bash
pip install reportlab flask-mail
```

For MySQL connectivity, install:

```bash
pip install pymysql
```

### 5. Initialize the Database

```bash
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

### 6. Run the Application

```bash
python app.py
```

Visit `http://127.0.0.1:5000/` in your browser.

## 🔐 Creating an Admin Account

If your project does not already have an admin account, you can create one using a separate Python script.

Create a file named `create_admin.py` in the project root:

```python
from getpass import getpass

from app import app, db
from models import User

with app.app_context():
    name = input("Enter admin name: ")
    email = input("Enter admin email: ")
    password = getpass("Enter admin password: ")

    admin = User(
        name=name,
        email=email,
        role="admin"
    )
    admin.set_password(password)

    db.session.add(admin)
    db.session.commit()

    print("Admin account created successfully!")
```

Run the script:

```bash
python create_admin.py
```

> 💡 **Tip:** Add `create_admin.py` to your `.gitignore` file. Never store real passwords or default credentials in source code or commit them to a public repository.

## 🔐 Creating Officer Accounts

Officers can be created in one of two ways, depending on the features available in your application.

**Option A — Through the Admin Panel (Recommended)**

If the Admin Panel supports officer creation:

1. Log in as an admin.
2. Navigate to **Manage Users → Add Officer**.
3. Fill in the officer's details and submit the form.

**Option B — Manually via Python Script**

Create a file named `create_officer.py` in the project root:

```python
from getpass import getpass

from app import app, db
from models import User

with app.app_context():
    name = input("Officer name: ")
    email = input("Officer email: ")
    password = getpass("Officer password: ")

    officer = User(
        name=name,
        email=email,
        role="officer"
    )
    officer.set_password(password)

    db.session.add(officer)
    db.session.commit()

    print("Officer account created successfully!")
```

Run the script:

```bash
python create_officer.py
```

> 💡 **Security Tip:** Add `create_officer.py` to your `.gitignore` file. Do not commit account-creation scripts containing hardcoded credentials to a public repository.

**Note:** The scripts above assume that the `User` model accepts `name`, `email`, and `role` fields and provides a `set_password()` method. Check your `models.py` before running them.

## 🔧 Configuration

The application settings can be managed through `config.py`.

| Setting | Description |
|---|---|
| `SECRET_KEY` | Flask session security key |
| `SQLALCHEMY_DATABASE_URI` | Database connection URL |
| `UPLOAD_FOLDER` | Location for uploaded files |
| `MAX_CONTENT_LENGTH` | Maximum upload size |
| `ALLOWED_EXTENSIONS` | Permitted attachment file types |
| `MAIL_USERNAME` | Email account for optional mail functionality |

For production use, set a strong secret key and keep credentials outside publicly accessible source code.

> 💡 **Best Practice:** For local development, consider storing secrets in a `.env` file and loading them with `python-dotenv`. Never commit `.env` to Git. This requires installing and configuring `python-dotenv` in your application.

## 🧪 Verify Installation

After starting the application:

1. Open `http://127.0.0.1:5000/`.
2. Check that the homepage loads correctly.
3. Register a user account.
4. Log in and submit a test complaint.
5. Verify that the complaint appears in the dashboard.
6. Test the available complaint-management features using the appropriate user roles.

## 📁 Project Structure

```text
complaint-management-system/
│
├── app.py
├── models.py
├── config.py
├── check_db.py              # Utility script to inspect the database
├── translations.py
├── reset_password.html      # Static password reset template
│
├── templates/
│   ├── base.html
│   ├── base_public.html
│   ├── index.html
│   ├── detail.html
│   ├── notifications.html
│   │
│   ├── admin/
│   ├── auth/
│   ├── complaints/
│   ├── officer/
│   ├── user/
│   └── errors/
│
├── screenshots/
│   ├── 1.png
│   ├── 2.png
│   ├── 3.png
│   └── ...
│
├── uploads/                 # Uploaded complaint attachments
├── complaints.db            # Created when the database is initialized
└── .gitignore               # Excludes venv/, *.db, uploads/, etc.
```

**Note:** The `create_admin.py` and `create_officer.py` scripts are created locally when needed. Keep both excluded from Git using `.gitignore`.

## 🖼️ Screenshots

The following screenshots demonstrate the main interfaces of the system. Place the corresponding image files inside the `screenshots/` directory.

| Page | Preview |
|---|---|
| Home Page | ![Home Page](screenshots/1.png) |
| Login Page | ![Login Page](screenshots/2.png) |
| Registration Page | ![Registration Page](screenshots/3.png) |
| User Dashboard | ![User Dashboard](screenshots/4.png) |
| Complaint Creation | ![Complaint Creation](screenshots/5.png) |
| Complaint Details | ![Complaint Details](screenshots/6.png) |
| Officer Dashboard | ![Officer Dashboard](screenshots/7.png) |
| Admin Dashboard | ![Admin Dashboard](screenshots/8.png) |
| Notifications | ![Notifications](screenshots/9.png) |
| Feedback | ![Feedback](screenshots/10.png) |

Additional screenshots cover reports, PDF exports, error pages, and administration sections (`11.1.png`, `11.2.png`, and onward through the available `14.x.png` images).

## 🎯 Project Objectives

- Develop a centralized complaint-management platform.
- Simplify complaint submission and tracking.
- Improve communication between users and responsible officers.
- Provide role-based access and complaint management.
- Demonstrate practical implementation of System Analysis and Design concepts.

## 🐛 Troubleshooting

| Problem | Solution |
|---|---|
| `ModuleNotFoundError: No module named 'flask'` | Install the required packages using `pip install flask flask-sqlalchemy flask-login werkzeug`. |
| `sqlite3.OperationalError: no such table` | Run the database initialization command again. |
| Port 5000 already in use | Stop the process using port 5000 or run `flask run --port=5001`. |
| `SECRET_KEY` warning | Set a secure secret key in `config.py`. |

## 📌 Version

**Current Version:** `v1.0.0`

## 🤝 Contributing

Contributions, suggestions, and improvements are welcome.

1. Fork the repository.
2. Create a new branch.
3. Make your changes.
4. Submit a pull request.

## 🙏 Acknowledgments

- Course instructor and academic advisors
- Flask and SQLAlchemy documentation
- Open-source community

## 📄 License

This project is intended for academic and educational purposes. Add a `LICENSE` file to the repository if you want to distribute it under a specific open-source license.

## ⚠️ Disclaimer

This project was developed for academic purposes as part of the System Analysis and Design course. While it implements real-world features, it may require additional security hardening and testing before production deployment.

## 👨‍💻 Author

**Mahinur Rahman Mahin**

- GitHub: [Mahin01234](https://github.com/Mahin01234)
- Project Repository: [Complaint Management System](https://github.com/Mahin01234/complaint-management-system)

---

⭐ **If you like this project, don't forget to star ⭐ the repository!**
