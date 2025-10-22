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
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    department = db.relationship("Department", back_populates="doctors")

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'specialization_id': self.specialization_id,
            'f_name': self.f_name,
            'l_name': self.l_name,
            'ph_no': self.ph_no,
            # Do not include raw binary; convert when needed
            'has_profile_pic': bool(self.profile_pic),
            'created_at': self.created_at.isoformat()
        }

class Department(db.Model):
    __tablename__ = 'Department'
    department_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    department_name = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    doctors_registered = db.Column(db.Integer, default=0)
    dep_pic = db.Column(db.LargeBinary)  # Store image as binary

    doctors = db.relationship("Doctor", back_populates="department")

    def to_dict(self):
        return {
            'department_id': self.department_id,
            'department_name': self.department_name,
            'description': self.description,
            'doctors_registered': self.doctors_registered,
            #Note: Do not include raw binary; convert when needed
            'has_profile_pic': bool(self.dep_pic),
        }

class Patient(db.Model):
    __tablename__ = 'Patient'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String, unique=True, nullable=False)
    f_name = db.Column(db.String, nullable=False)
    l_name = db.Column(db.String, nullable=False)
    ph_no = db.Column(db.Integer, nullable=False)
    profile_pic = db.Column(db.LargeBinary)  # Store image as binary
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self, include_image=False):
        """Return a JSON-serializable representation of Patient.

        If include_image is True, profile_pic will be returned as base64 string (or None).
        """
        # Serialize created_at as date-only (YYYY-MM-DD) for UI friendliness
        created_date = None
        if getattr(self, 'created_at', None):
            try:
                created_date = self.created_at.date().isoformat()
            except Exception:
                try:
                    created_date = self.created_at.isoformat()
                except Exception:
                    created_date = None

        data = {
            'id': self.id,
            'username': self.username,
            'f_name': self.f_name,
            'l_name': self.l_name,
            'ph_no': self.ph_no,
            'created_at': created_date,
        }
        if include_image:
            try:
                import base64
                data['profile_b64'] = base64.b64encode(self.profile_pic).decode('utf-8') if self.profile_pic else None
            except Exception:
                data['profile_b64'] = None
        else:
            data['has_profile_pic'] = bool(self.profile_pic)
        return data

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

    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'doctor_id': self.doctor_id,
            'date': self.date,
            'time': self.time,
            'status': self.status,
        }

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
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'f_name': self.f_name,
            'l_name': self.l_name,
            #Note: Do not include raw binary; convert when needed
            'has_profile_pic': bool(self.profile_pic),
            'created_at': self.created_at.isoformat()
        }

class Treatment(db.Model):
    __tablename__ = 'Treatment'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    diagnosis = db.Column(db.String)
    prescription = db.Column(db.String)
    notes = db.Column(db.String)


