import os
base_dir = os.path.abspath(os.path.dirname(__file__))

class Config:
    DEBUG = False
    SQLITE_DB_DIR = None
    SQLALCHEMY_DATABASE_URI = None
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = None

class LocalDevelopmentConfig(Config):
    DEBUG = True
    SQLITE_DB_DIR = os.path.join(base_dir, '../db')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(SQLITE_DB_DIR, "HMS_IITM.sqlite3")}'
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret')