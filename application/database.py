from sqlalchemy.ext.declarative import declarative_base
from flask_sqlalchemy import SQLAlchemy

engine = None
db = SQLAlchemy()
Base = declarative_base()