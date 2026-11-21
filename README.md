Complaint Management System (CMS Portal)
<p align="center"> <img src="https://img.shields.io/badge/Python-3.8%2B-blue.svg" alt="Python"> <img src="https://img.shields.io/badge/Flask-2.x-green.svg" alt="Flask"> <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"> </p>
📌 Overview
Complaint Management System (CMS Portal) হলো একটি ফুল-স্ট্যাক ওয়েব অ্যাপ্লিকেশন, যা কোনো প্রতিষ্ঠান বা সংস্থার অভিযোগ (Complaint) সংগ্রহ, ট্র্যাকিং, অ্যাসাইনমেন্ট এবং সমাধানের পুরো প্রক্রিয়াটি ডিজিটাল ও স্বয়ংক্রিয় করার জন্য ডিজাইন করা হয়েছে। এটি একটি একাডেমিক প্রজেক্ট হিসেবে System Analysis and Design কোর্সের জন্য তৈরি করা হয়েছে, তবে এর ফিচারগুলো বাস্তব ব্যবহারের উপযোগী।

অ্যাপ্লিকেশনটিতে তিনটি প্রধান রোল রয়েছে — User (সাধারণ ব্যবহারকারী), Officer (অফিসার/রেসপন্ডার) এবং Admin (প্রশাসক)। প্রতিটি রোলের জন্য আলাদা ড্যাশবোর্ড, অনুমতি এবং কার্যকারিতা রয়েছে।

✨ Key Features
🔐 Role-Based Access Control (RBAC) — user, officer, এবং admin এর জন্য আলাদা অনুমতি ও ইন্টারফেস।

🔄 Complaint Lifecycle Management — অভিযোগ তৈরি, ট্র্যাকিং আইডি জেনারেশন, স্ট্যাটাস আপডেট (Pending → In Review → Assigned → In Progress → Resolved/Closed/Rejected)।

⏱️ SLA (Service Level Agreement) Tracking — প্রতিটি অভিযোগের জন্য ডেডলাইন নির্ধারণ এবং স্বয়ংক্রিয় এসক্যালেশন।

👤 Assignment System — অ্যাডমিন দ্বারা অভিযোগ অফিসারকে অ্যাসাইন করা।

🔔 Notifications — স্ট্যাটাস পরিবর্তন বা নতুন অ্যাসাইনমেন্টের জন্য ইন-অ্যাপ নোটিফিকেশন।

📎 File Attachments — অভিযোগের সাথে ছবি, PDF, DOC ইত্যাদি আপলোড (সর্বোচ্চ ৫ MB)।

⭐ Feedback & Rating — সমাধানের পরে ব্যবহারকারী ফিডব্যাক প্রদান করতে পারে।

📄 PDF Report Generation — অভিযোগের বিবরণ ও রিপোর্ট PDF আকারে ডাউনলোড।

🌐 Multi-language Support (Partial) — কিছু টেক্সটের জন্য ট্রান্সলেশন সাপোর্ট (বর্তমানে আংশিক)।

📱 Responsive UI — মোবাইল ও ডেস্কটপে ব্যবহারযোগ্য ইন্টারফেস।

🛠️ Tech Stack
Layer	Technology
Backend	Python 3.8+, Flask
Database	SQLite (ডিফল্ট), MySQL (কনফিগারযোগ্য)
ORM	Flask-SQLAlchemy
Authentication	Flask-Login, Werkzeug Password Hashing
Frontend	HTML5, CSS3, JavaScript (Jinja2 Templates)
File Handling	Werkzeug Secure Filename, UUID
PDF Export	ReportLab (ঐচ্ছিক)
Email (Optional)	Flask-Mail
📁 Project Structure
text
complaint-management-system/
│
├── app.py                 # মূল Flask অ্যাপ্লিকেশন ও রাউট
├── models.py              # SQLAlchemy মডেল (User, Complaint, Category, ইত্যাদি)
├── config.py              # কনফিগারেশন (DB URI, Upload Folder, Secret Key)
├── check_db.py            # ডাটাবেস পরীক্ষার স্ক্রিপ্ট
├── reset_password.html    # পাসওয়ার্ড রিসেট টেমপ্লেট (স্ট্যাটিক)
├── translations.py        # আংশিক ট্রান্সলেশন ডিকশনারি
│
├── templates/
│   ├── base.html          # বেস টেমপ্লেট (লগইন করা ব্যবহারকারীদের জন্য)
│   ├── base_public.html   # পাবলিক বেস টেমপ্লেট
│   ├── index.html         # হোমপেজ
│   ├── detail.html        # অভিযোগের বিস্তারিত পেজ
│   ├── notifications.html # নোটিফিকেশন পেজ
│   │
│   ├── admin/             # অ্যাডমিন-নির্দিষ্ট টেমপ্লেট
│   ├── auth/              # লগইন, রেজিস্ট্রেশন, পাসওয়ার্ড রিসেট
│   ├── complaints/        # অভিযোগ তৈরি ও তালিকা
│   ├── officer/           # অফিসার ড্যাশবোর্ড
│   ├── user/              # ব্যবহারকারী ড্যাশবোর্ড
│   └── errors/            # 403, 404, 500 এরর পেজ
│
├── uploads/               # আপলোড করা ফাইল (রানটাইমে তৈরি)
├── complaints.db          # SQLite ডাটাবেস (প্রথম রানে তৈরি)
├── .gitignore
└── README.md
🚀 Installation & Setup
১. রিপোজিটরি ক্লোন করুন
bash
git clone https://github.com/Mahin01234/complaint-management-system.git
cd complaint-management-system
২. ভার্চুয়াল এনভায়রনমেন্ট তৈরি করুন (রেকমেন্ডেড)
bash
python -m venv venv
Linux / Mac:

bash
source venv/bin/activate
Windows:

bash
venv\Scripts\activate
৩. ডিপেন্ডেন্সি ইনস্টল করুন
requirements.txt না থাকায় নিচের প্যাকেজগুলো ম্যানুয়ালি ইনস্টল করতে হবে:

bash
pip install flask flask-sqlalchemy flask-login werkzeug
ঐচ্ছিক (PDF ও ইমেইলের জন্য):

bash
pip install reportlab flask-mail
৪. ডাটাবেস কনফিগারেশন
ডিফল্টভাবে SQLite ব্যবহার হবে (complaints.db)। config.py ফাইলে SQLALCHEMY_DATABASE_URI পরিবর্তন করে MySQL-ও ব্যবহার করতে পারবেন:

python
# MySQL উদাহরণ
SQLALCHEMY_DATABASE_URI = "mysql+pymysql://username:password@localhost/cms_db"
MySQL ব্যবহার করতে pip install pymysql করতে হবে।

৫. ডাটাবেস ইনিশিয়ালাইজ করুন
প্রথমবার অ্যাপ চালানোর আগে ডাটাবেস টেবিল তৈরি করুন:

bash
python -c "from app import app, db; app.app_context().push(); db.create_all()"
অথবা সরাসরি app.py চালালে অ্যাপ্লিকেশন স্বয়ংক্রিয়ভাবে ডাটাবেস তৈরি করবে (যদি db.create_all() কল করা থাকে)।

৬. অ্যাপ্লিকেশন রান করুন
bash
python app.py
ব্রাউজারে ভিজিট করুন: http://127.0.0.1:5000/

⚙️ Configuration
config.py ফাইলে নিচের সেটিংস পরিবর্তন করতে পারবেন:

Variable	Description
SECRET_KEY	Flask সেশন সিকিউরিটি (প্রোডাকশনে অবশ্যই পরিবর্তন করুন)
SQLALCHEMY_DATABASE_URI	ডাটাবেস কানেকশন স্ট্রিং
UPLOAD_FOLDER	ফাইল আপলোড ডিরেক্টরি
MAX_CONTENT_LENGTH	সর্বোচ্চ আপলোড সাইজ (ডিফল্ট ৫ MB)
ALLOWED_EXTENSIONS	অনুমোদিত ফাইল এক্সটেনশন
MAIL_USERNAME	ইমেইল নোটিফিকেশনের জন্য (ঐচ্ছিক)
⚠️ নোট: SECRET_KEY ডিফল্টভাবে "change-me-in-production-please" আছে। প্রোডাকশনে এটি পরিবর্তন করা বাধ্যতামূলক।

👥 Default Roles & Access
Role	Permissions
User	অভিযোগ তৈরি, নিজের অভিযোগ ট্র্যাক করা, ফিডব্যাক দেওয়া, নোটিফিকেশন দেখা
Officer	অ্যাসাইন করা অভিযোগ দেখা, স্ট্যাটাস আপডেট করা, সমাধান করা
Admin	সব অভিযোগ দেখা, অফিসার অ্যাসাইন করা, ক্যাটাগরি ম্যানেজমেন্ট, এসক্যালেশন, রিপোর্ট
🔑 অ্যাডমিন অ্যাকাউন্ট তৈরি
প্রথমবার চালানোর পর কোনো ডিফল্ট অ্যাডমিন থাকে না। নিচের কমান্ড দিয়ে একটি অ্যাডমিন ইউজার তৈরি করতে পারবেন:

python
python -c "
from app import app, db
from models import User
with app.app_context():
    admin = User(name='Admin', email='admin@example.com', role='admin')
    admin.set_password('admin123')
    db.session.add(admin)
    db.session.commit()
    print('Admin created successfully.')
"
📸 Screenshots
রিপোজিটরিতে থাকা 1.png থেকে 14.4.png পর্যন্ত ফাইলগুলো অ্যাপ্লিকেশনের বিভিন্ন স্ক্রিনের স্ক্রিনশট। নিচে কয়েকটি উল্লেখযোগ্য স্ক্রিনের নাম দেওয়া হলো:

File	Screen
1.png	হোমপেজ / ল্যান্ডিং পেজ
2.png	লগইন পেজ
3.png	রেজিস্ট্রেশন পেজ
4.png	ব্যবহারকারী ড্যাশবোর্ড
5.png	অভিযোগ তৈরির ফর্ম
6.png	অভিযোগের বিস্তারিত ভিউ
7.png	অফিসার ড্যাশবোর্ড
8.png	অ্যাডমিন ড্যাশবোর্ড
9.png	নোটিফিকেশন পেজ
10.png	ফিডব্যাক ফর্ম
11.x.png	রিপোর্ট / অ্যানালিটিক্স
12.x.png	PDF এক্সপোর্ট
13.x.png	এরর পেজ ও অন্যান্য
14.x.png	অ্যাডমিন প্যানেলের বিভিন্ন অংশ
README-তে স্ক্রিনশট যোগ করতে চাইলে নিচের মতো Markdown ব্যবহার করুন:

markdown
![Home Page](1.png)
![User Dashboard](4.png)
🤝 Contributing
এটি একটি একাডেমিক প্রজেক্ট, তবে যেকোনো Suggestions বা Bug Report স্বাগত। Contribution করার আগে অনুগ্রহ করে একটি Issue খুলে আলোচনা করুন।

Fork করুন

Feature Branch তৈরি করুন (git checkout -b feature/AmazingFeature)

Commit করুন (git commit -m 'Add some AmazingFeature')

Push করুন (git push origin feature/AmazingFeature)

Pull Request খুলুন

📄 License
এই প্রজেক্টটি MIT License এর অধীনে লাইসেন্সকৃত। বিস্তারিত জানতে LICENSE ফাইল দেখুন (যদি থাকে) অথবা opensource.org/licenses/MIT ভিজিট করুন।
