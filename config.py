# config.py
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = "change-me-in-production-please"
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "complaints.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    ALLOWED_EXTENSIONS = {
        "png", "jpg", "jpeg", "gif", "webp", "bmp", "svg",
        "pdf", "txt", "doc", "docx",
    }

    # মেইল সেটিংস আপাতত বন্ধ রাখা হলো
    MAIL_USERNAME = None
    # MAIL_SERVER = 'smtp.gmail.com'
    # MAIL_PORT = 587
    # MAIL_USE_TLS = True
    # MAIL_PASSWORD = 'xxxxxxxxxxxxxxxx'
    # MAIL_DEFAULT_SENDER = 'mahinurrahman1631@gmail.com'