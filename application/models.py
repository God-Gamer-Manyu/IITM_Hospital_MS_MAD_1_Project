"""
Defines the tables of the database for the application.

Note: in login table, the 'role' field, 0 - Admin, 1 - Doctor, 2 - Patient
Note: in appointment table, the 'status' field, 0 - Booked, 1 - Compeleted, 2 - Cancelled
"""
from .database import db
from flask_login import UserMixin


class Doctor(db.Model):
    __tablename__ = 'Doctor'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String, unique=True, nullable=False)
    specialization_id = db.Column(db.Integer, db.ForeignKey('Department.department_id'))
    f_name = db.Column(db.String, nullable=False)
    l_name = db.Column(db.String, nullable=False)
    ph_no = db.Column(db.Integer, nullable=False)
    profile_pic = db.Column(db.LargeBinary)  # Store image as binary

    department = db.relationship("Department", back_populates="doctors")

class Department(db.Model):
    __tablename__ = 'Department'
    department_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    department_name = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    doctors_registered = db.Column(db.Integer, default=0)

    doctors = db.relationship("Doctor", back_populates="department")

class Patient(db.Model):
    __tablename__ = 'Patient'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String, unique=True, nullable=False)
    f_name = db.Column(db.String, nullable=False)
    l_name = db.Column(db.String, nullable=False)
    ph_no = db.Column(db.Integer, nullable=False)
    profile_pic = db.Column(db.LargeBinary)  # Store image as binary

class Appointment(db.Model):
    __tablename__ = 'Appointment'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('Patient.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('Doctor.id'))
    date = db.Column(db.String, nullable=False)
    time = db.Column(db.String, nullable=False)
    status = db.Column(db.String)

    doctor = db.relationship("Doctor")
    patient = db.relationship("Patient")

class Login(UserMixin, db.Model):
    __tablename__ = 'Login'
    username = db.Column(db.String, primary_key=True)
    password = db.Column(db.String, nullable=False)
    role = db.Column(db.Integer, nullable=False)  # 0 = Admin, 1 = Doctor, 2 = Patient

    def get_id(self):
        """Return the unique id for Flask-Login.

        Our primary key is `username`, so return that.
        """
        return str(self.username)

    @property
    def user_info(self) -> 'Admin | Doctor | Patient | None':
        """
        Example usage:

        login = session.query(Login).filter_by(username='dr_smith').first()

        user = login.user_info

        print(f"Logged in as: {user.f_name} {user.l_name}")
        """
        if self.role == 0:
            return Admin.query.filter_by(username=self.username).first()
        elif self.role == 1:
            return Doctor.query.filter_by(username=self.username).first()
        elif self.role == 2:
            return Patient.query.filter_by(username=self.username).first()
        return None

class Admin(db.Model):
    __tablename__ = 'Admin'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String, unique=True, nullable=False)
    f_name = db.Column(db.String, nullable=False)
    l_name = db.Column(db.String, nullable=False)
    profile_pic = db.Column(db.LargeBinary)  # Store image as binary

class Treatment(db.Model):
    __tablename__ = 'Treatment'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    diagnosis = db.Column(db.String)
    prescription = db.Column(db.String)
    notes = db.Column(db.String)


