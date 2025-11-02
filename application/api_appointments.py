from flask_restful import Resource
from flask import request, jsonify
from flask_login import current_user, login_required
from .models import Appointment, Doctor, Patient, Login
from .database import db
from datetime import datetime, timedelta
from sqlalchemy import and_


def _serialize_appt(a: Appointment) -> dict:
    try:
        dname = f"{a.doctor.f_name} {a.doctor.l_name}" if a.doctor else None
    except Exception:
        dname = None
    try:
        pname = f"{a.patient.f_name} {a.patient.l_name}" if a.patient else None
    except Exception:
        pname = None
    out = a.to_dict() if hasattr(a, 'to_dict') else {
        'id': a.id, 'patient_id': a.patient_id, 'doctor_id': a.doctor_id,
        'date': a.date, 'time': a.time, 'status': a.status
    }
    out['doctor_name'] = dname
    out['patient_name'] = pname
    # include doctor contact when available
    try:
        out['doctor_contact'] = a.doctor.ph_no if a.doctor else None
    except Exception:
        out['doctor_contact'] = None
    return out


class AppointmentListResource(Resource):
    method_decorators = [login_required]

    def get(self):
        # Query params: doctor_id, patient_id
        q_doctor = request.args.get('doctor_id')
        q_patient = request.args.get('patient_id')

        # Admin: can view all or filtered
        role = getattr(current_user, 'role', None)
        if role is not None:
            try:
                role = int(role)
            except Exception:
                role = None

        appts = []
        if role == 0:
            # admin
            query = Appointment.query
            if q_doctor:
                try:
                    query = query.filter_by(doctor_id=int(q_doctor))
                except Exception:
                    return {'ok': False, 'error': 'invalid doctor_id'}, 400
            if q_patient:
                try:
                    query = query.filter_by(patient_id=int(q_patient))
                except Exception:
                    return {'ok': False, 'error': 'invalid patient_id'}, 400
            appts = query.order_by(Appointment.date.desc(), Appointment.time.desc()).all()
        elif role == 1:
            # doctor: only appointments for this doctor
            login = Login.query.filter_by(username=current_user.get_id()).first()
            doctor = login.user_info if login else None
            if not doctor:
                return {'ok': False, 'error': 'Doctor profile not found'}, 403
            appts = Appointment.query.filter_by(doctor_id=doctor.id).order_by(Appointment.date.desc(), Appointment.time.desc()).all()
        else:
            # patient: only own appointments
            login = Login.query.filter_by(username=current_user.get_id()).first()
            patient = login.user_info if login else None
            if not patient:
                return {'ok': False, 'error': 'Patient profile not found'}, 403
            appts = Appointment.query.filter_by(patient_id=patient.id).order_by(Appointment.date.desc(), Appointment.time.desc()).all()

        out = [_serialize_appt(a) for a in appts]
        return {'ok': True, 'appointments': out}

    def post(self):
        # Create appointment. Expect JSON: doctor_id, date(YYYY-MM-DD), time(HH:MM), optional patient_id (admin)
        data = request.get_json(force=True) if request.is_json else request.get_json(silent=True) or request.form
        try:
            doctor_id = int(data.get('doctor_id'))
            date_str = data.get('date')
            time_str = data.get('time')
        except Exception:
            return {'ok': False, 'error': 'Missing or invalid parameters'}, 400

        # validate date/time
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            datetime.strptime(time_str, '%H:%M')
        except Exception:
            return {'ok': False, 'error': 'Invalid date or time format'}, 400

        doc = Doctor.query.filter_by(id=doctor_id).first()
        if not doc:
            return {'ok': False, 'error': 'Doctor not found'}, 404

        role = getattr(current_user, 'role', None)
        try:
            role = int(role)
        except Exception:
            role = None

        if role == 2:
            # patient creating for self
            login = Login.query.filter_by(username=current_user.get_id()).first()
            patient = login.user_info if login else None
            if not patient:
                return {'ok': False, 'error': 'Patient profile not found'}, 403
            patient_id = patient.id
        else:
            # admin or doctor can create but must specify patient_id
            pid = data.get('patient_id')
            if not pid:
                return {'ok': False, 'error': 'patient_id required for this user'}, 400
            try:
                patient_id = int(pid)
            except Exception:
                return {'ok': False, 'error': 'invalid patient_id'}, 400
            if not Patient.query.filter_by(id=patient_id).first():
                return {'ok': False, 'error': 'Patient not found'}, 404

        # Check availability
        exists = Appointment.query.filter_by(doctor_id=doctor_id, date=date_str, time=time_str).first()
        if exists and exists.status != 'Cancelled':
            return {'ok': False, 'error': 'Slot already booked'}, 409

        try:
            appt = Appointment(patient_id=patient_id, doctor_id=doctor_id, date=date_str, time=time_str, status='Booked')
            db.session.add(appt)
            db.session.commit()
            return {'ok': True, 'appointment': _serialize_appt(appt)}, 201
        except Exception as e:
            db.session.rollback()
            return {'ok': False, 'error': str(e)}, 500


class AppointmentResource(Resource):
    method_decorators = [login_required]

    def get(self, appt_id: int):
        a = Appointment.query.filter_by(id=appt_id).first()
        if not a:
            return {'ok': False, 'error': 'Appointment not found'}, 404

        role = getattr(current_user, 'role', None)
        try:
            role = int(role)
        except Exception:
            role = None

        # Ownership checks
        if role == 2:
            # patient can only view own
            login = Login.query.filter_by(username=current_user.get_id()).first()
            patient = login.user_info if login else None
            if not patient or a.patient_id != patient.id:
                return {'ok': False, 'error': 'Unauthorized'}, 403
        elif role == 1:
            login = Login.query.filter_by(username=current_user.get_id()).first()
            doctor = login.user_info if login else None
            if not doctor or a.doctor_id != doctor.id:
                return {'ok': False, 'error': 'Unauthorized'}, 403

        return {'ok': True, 'appointment': _serialize_appt(a)}

    def put(self, appt_id: int):
        # Update/reschedule appointment. Accept JSON with date/time
        a = Appointment.query.filter_by(id=appt_id).first()
        if not a:
            return {'ok': False, 'error': 'Appointment not found'}, 404

        role = getattr(current_user, 'role', None)
        try:
            role = int(role)
        except Exception:
            role = None

        # Only patient (owner) or admin can reschedule; doctors cannot change patient bookings here
        if role == 2:
            login = Login.query.filter_by(username=current_user.get_id()).first()
            patient = login.user_info if login else None
            if not patient or a.patient_id != patient.id:
                return {'ok': False, 'error': 'Unauthorized'}, 403
        elif role != 0:
            return {'ok': False, 'error': 'Unauthorized'}, 403

        data = request.get_json(force=True) if request.is_json else request.get_json(silent=True) or request.form
        date_str = data.get('date')
        time_str = data.get('time')
        if not date_str or not time_str:
            return {'ok': False, 'error': 'date and time required'}, 400
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            datetime.strptime(time_str, '%H:%M')
        except Exception:
            return {'ok': False, 'error': 'Invalid date/time format'}, 400

        # Check new slot availability (exclude self)
        exists = Appointment.query.filter(and_(Appointment.doctor_id == a.doctor_id, Appointment.date == date_str, Appointment.time == time_str, Appointment.id != a.id)).first()
        if exists and exists.status != 'Cancelled':
            return {'ok': False, 'error': 'Slot already booked'}, 409

        try:
            a.date = date_str
            a.time = time_str
            a.status = data.get('status', a.status)
            db.session.commit()
            return {'ok': True, 'appointment': _serialize_appt(a)}
        except Exception as e:
            db.session.rollback()
            return {'ok': False, 'error': str(e)}, 500

    def delete(self, appt_id: int):
        # Soft cancel the appointment (set status Cancelled)
        a = Appointment.query.filter_by(id=appt_id).first()
        if not a:
            return {'ok': False, 'error': 'Appointment not found'}, 404

        role = getattr(current_user, 'role', None)
        try:
            role = int(role)
        except Exception:
            role = None

        if role == 2:
            login = Login.query.filter_by(username=current_user.get_id()).first()
            patient = login.user_info if login else None
            if not patient or a.patient_id != patient.id:
                return {'ok': False, 'error': 'Unauthorized'}, 403
        elif role == 1:
            login = Login.query.filter_by(username=current_user.get_id()).first()
            doctor = login.user_info if login else None
            if not doctor or a.doctor_id != doctor.id:
                return {'ok': False, 'error': 'Unauthorized'}, 403
        # admin can cancel any

        try:
            a.status = 'Cancelled'
            db.session.commit()
            return {'ok': True}
        except Exception as e:
            db.session.rollback()
            return {'ok': False, 'error': str(e)}, 500


class PublicDoctorAvailabilityResource(Resource):
    """Public endpoint: returns booked/free slots for a given doctor.

    Query params:
      - start: YYYY-MM-DD (default today)
      - days: integer number of days (default 7, max 30)

    Response: { ok: True, doctor_id, availability: [{date, slots:[{time, booked}]}] }
    This endpoint intentionally exposes only boolean booked info (no patient details).
    """

    def get(self, doctor_id: int):
        # Validate doctor exists
        doc = Doctor.query.filter_by(id=doctor_id).first()
        if not doc:
            return {'ok': False, 'error': 'Doctor not found'}, 404

        start_str = request.args.get('start')
        days_q = request.args.get('days')
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
            else:
                start = datetime.now().date()
        except Exception:
            return {'ok': False, 'error': 'Invalid start date, expected YYYY-MM-DD'}, 400

        try:
            days = int(days_q) if days_q else 7
        except Exception:
            days = 7
        if days < 1:
            days = 1
        if days > 30:
            days = 30

        days_list = [(start + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)]

        # Build time slots 09:00-20:00 30-min
        slots = []
        cur = datetime.strptime('09:00', '%H:%M')
        end = datetime.strptime('20:00', '%H:%M')
        while cur <= end:
            slots.append(cur.strftime('%H:%M'))
            cur += timedelta(minutes=30)

        # Query appointments for doctor in range, exclude cancelled
        appts = Appointment.query.filter(and_(Appointment.doctor_id == doctor_id, Appointment.date.in_(days_list))).all()
        booked = set((a.date, a.time) for a in appts if a.status != 'Cancelled')

        availability = []
        for day in days_list:
            day_slots = []
            for t in slots:
                day_slots.append({'time': t, 'booked': (day, t) in booked})
            availability.append({'date': day, 'slots': day_slots})

        return {'ok': True, 'doctor_id': doctor_id, 'availability': availability}
