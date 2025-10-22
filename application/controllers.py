from flask import Flask, request, render_template, redirect, url_for, jsonify, flash, session, send_file, abort, Response
from flask import current_app as app
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from .models import Login, Patient, Appointment, Treatment, Doctor, Department, Admin
from .database import db
from sqlalchemy.exc import IntegrityError
import base64
from datetime import datetime, date, time, timedelta
import io
import imghdr
from sqlalchemy import and_

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'login_page' # type: ignore
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id: str):
    return Login.query.filter_by(username=user_id).first()


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify(status='OK'), 200

@app.route('/', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == '1'

        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('login.html')

        login = Login.query.filter_by(username=username).first()
        if login is None or login.password != password:
            # Note: If passwords changed to hashed passwords later, replace this comparison with a hash check.
            flash('Invalid username or password', 'error')
            return render_template('login.html')

        # If the account is blacklisted, do not allow login
        try:
            if getattr(login, 'blacklisted', False):
                flash('You are blacklisted', 'error')
                return render_template('login.html')
        except Exception:
            pass

        # Successful authentication
        login_user(login, remember=remember)
        flash('Login successful', 'success')

        # Redirect by role.
        if login.role == 0:
            return redirect(url_for('admin_dashboard'))
        elif login.role == 1:
            return redirect(url_for('doctor_dashboard'))
        else:
            return redirect(url_for('patient_dashboard'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('login_page'))


def role_required(role_id: int):
    """Simple decorator factory to ensure current_user has required role."""
    def decorator(func):
        @login_required
        def wrapper(*args, **kwargs):
            if not hasattr(current_user, 'role') or int(current_user.role) != role_id:
                flash('Unauthorized', 'error')
                return redirect(url_for('login_page'))
            return func(*args, **kwargs)
        # Preserve function identity
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


@app.route('/admin')
@role_required(0)
def admin_dashboard():
    # Render admin dashboard with admin_js and basic lists
    login = Login.query.filter_by(username=current_user.get_id()).first()
    admin = login.user_info if login else None
    if not admin:
        flash('Admin profile not found', 'error')
        return redirect(url_for('login_page'))

    admin_js = admin.to_dict() if admin else None
    # counts and lists will be fetched via AJAX from the page
    return render_template('admin.html', admin=admin, admin_js=admin_js)


@app.route('/admin/metrics', methods=['GET'])
@role_required(0)
def admin_metrics():
    # Provide counts: doctors, patients, upcoming appointments, past appointments
    total_doctors = Doctor.query.count()
    total_patients = Patient.query.count()
    today = datetime.now().date().isoformat()
    appts = Appointment.query.all()
    upcoming = 0
    past = 0
    now_dt = datetime.now()
    for a in appts:
        try:
            dt = datetime.strptime(f"{a.date} {a.time}", "%Y-%m-%d %H:%M")
        except Exception:
            try:
                dt = datetime.strptime(a.date, "%Y-%m-%d")
            except Exception:
                dt = now_dt
        if dt >= now_dt:
            upcoming += 1
        else:
            past += 1
    return jsonify({'ok': True, 'doctors': total_doctors, 'patients': total_patients, 'upcoming': upcoming, 'past': past})


@app.route('/admin_calendar/<date_str>', methods=['GET'])
@role_required(0)
def admin_calendar(date_str: str):
    # date_str expected YYYY-MM-DD -> build 7 days starting from date_str
    try:
        start = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        start = datetime.now().date()
    days = [(start + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    # build slots
    slots = []
    cur = datetime.strptime('09:00', '%H:%M')
    end = datetime.strptime('20:00', '%H:%M')
    while cur <= end:
        slots.append(cur.strftime('%H:%M'))
        cur += timedelta(minutes=30)

    # Query appointments within range
    appts = Appointment.query.filter(Appointment.date.in_(days)).all()
    # Map (date, time) -> list of appointments
    slot_map = {}
    for a in appts:
        if a.status == 'Cancelled':
            continue
        key = (a.date, a.time)
        slot_map.setdefault(key, []).append({
            'id': a.id,
            'patient_id': a.patient_id,
            'patient_name': f"{a.patient.f_name} {a.patient.l_name}" if a.patient else None,
            'doctor_id': a.doctor_id,
            'doctor_name': f"{a.doctor.f_name} {a.doctor.l_name}" if a.doctor else None,
            'status': a.status
        })

    availability = []
    for day in days:
        day_slots = []
        for t in slots:
            key = (day, t)
            items = slot_map.get(key, [])
            day_slots.append({'time': t, 'appointments': items})
        availability.append({'date': day, 'slots': day_slots})
    return jsonify({'ok': True, 'availability': availability})


@app.route('/admin/patients', methods=['GET'])
@role_required(0)
def admin_patients():
    # Optional filtering by doctor_id (returns patients who have appointments with that doctor)
    doctor_id = request.args.get('doctor_id')
    if doctor_id:
        try:
            did = int(doctor_id)
        except Exception:
            return jsonify({'ok': False, 'error': 'Invalid doctor id'}), 400

        # Find patient ids who have appointments with this doctor
        appts = Appointment.query.filter_by(doctor_id=did).all()
        patient_ids = sorted({a.patient_id for a in appts if a.patient_id})
        patients = Patient.query.filter(Patient.id.in_(patient_ids)).order_by(Patient.id.asc()).all() if patient_ids else []
    else:
        patients = Patient.query.order_by(Patient.id.asc()).all()

    out = []
    for p in patients:
        pd = p.to_dict(include_image=False)
        login_row = Login.query.filter_by(username=p.username).first()
        pd['blacklisted'] = bool(login_row.blacklisted) if login_row else False
        out.append(pd)
    return jsonify({'ok': True, 'patients': out})


@app.route('/admin/patient/add', methods=['POST'])
@role_required(0)
def admin_add_patient():
    f_name = request.form.get('f_name', '').strip()
    l_name = request.form.get('l_name', '').strip()
    ph_no = request.form.get('ph_no', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    if not all([f_name, l_name, ph_no, username, password]):
        return jsonify({'ok': False, 'error': 'All fields required'}), 400
    if Login.query.filter_by(username=username).first():
        return jsonify({'ok': False, 'error': 'Username already exists'}), 409
    try:
        patient = Patient(username=username, f_name=f_name, l_name=l_name, ph_no=int(ph_no), created_at=datetime.now())
        prof = request.files.get('profile_pic')
        if prof and prof.filename:
            patient.profile_pic = prof.read()
        db.session.add(patient)
        login_row = Login(username=username, password=password, role=2)
        db.session.add(login_row)
        db.session.commit()
        return jsonify({'ok': True, 'patient': patient.to_dict(include_image=False)})
    except ValueError:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Phone must be numeric'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/admin/patient/<int:patient_id>', methods=['GET'])
@role_required(0)
def admin_get_patient(patient_id: int):
    p = Patient.query.filter_by(id=patient_id).first()
    if not p:
        return jsonify({'ok': False, 'error': 'Patient not found'}), 404
    pd = p.to_dict(include_image=False)
    login_row = Login.query.filter_by(username=p.username).first()
    pd['blacklisted'] = bool(login_row.blacklisted) if login_row else False
    return jsonify({'ok': True, 'patient': pd})


@app.route('/admin/patient/<int:patient_id>/edit', methods=['POST'])
@role_required(0)
def admin_edit_patient(patient_id: int):
    p = Patient.query.filter_by(id=patient_id).first()
    if not p:
        return jsonify({'ok': False, 'error': 'Patient not found'}), 404
    f_name = request.form.get('f_name', '').strip()
    l_name = request.form.get('l_name', '').strip()
    ph_no = request.form.get('ph_no', '').strip()
    username = request.form.get('username', '').strip()
    if not all([f_name, l_name, ph_no, username]):
        return jsonify({'ok': False, 'error': 'All fields required'}), 400
    try:
        # If username changed, update Login table as well
        old_username = p.username
        if username != old_username:
            login_row = Login.query.filter_by(username=old_username).first()
            if login_row:
                # update primary key username
                login_row.username = username
            p.username = username
        p.f_name = f_name
        p.l_name = l_name
        p.ph_no = int(ph_no)
        prof = request.files.get('profile_pic')
        if prof and prof.filename:
            p.profile_pic = prof.read()
        db.session.commit()
        return jsonify({'ok': True, 'patient': p.to_dict(include_image=False)})
    except ValueError:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Phone must be numeric'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/admin/patient/<int:patient_id>/delete', methods=['POST'])
@role_required(0)
def admin_delete_patient(patient_id: int):
    p = Patient.query.filter_by(id=patient_id).first()
    if not p:
        return jsonify({'ok': False, 'error': 'Patient not found'}), 404
    try:
        # delete login row too
        login_row = Login.query.filter_by(username=p.username).first()
        if login_row:
            db.session.delete(login_row)
        db.session.delete(p)
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/admin/doctors', methods=['GET'])
@role_required(0)
def admin_doctors():
    docs = Doctor.query.order_by(Doctor.id.asc()).all()
    out = []
    for d in docs:
        dd = d.to_dict()
        login_row = Login.query.filter_by(username=d.username).first()
        dd['blacklisted'] = bool(login_row.blacklisted) if login_row else False
        out.append(dd)
    return jsonify({'ok': True, 'doctors': out})


@app.route('/admin/departments', methods=['GET'])
@role_required(0)
def admin_departments():
    deps = Department.query.order_by(Department.department_id.asc()).all()
    return jsonify({'ok': True, 'departments': [d.to_dict() for d in deps]})


@app.route('/doctor/<int:doctor_id>', methods=['POST', 'DELETE'])
@role_required(0)
def admin_edit_delete_doctor(doctor_id: int):
    d = Doctor.query.filter_by(id=doctor_id).first()
    if not d:
        return jsonify({'ok': False, 'error': 'Doctor not found'}), 404

    if request.method == 'DELETE':
        # prevent deletion if appointments exist
        existing = Appointment.query.filter_by(doctor_id=doctor_id).first()
        if existing:
            return jsonify({'ok': False, 'error': 'Cannot delete doctor with existing appointments'}), 409
        try:
            login_row = Login.query.filter_by(username=d.username).first()
            if login_row:
                db.session.delete(login_row)
            db.session.delete(d)
            db.session.commit()
            return jsonify({'ok': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'ok': False, 'error': str(e)}), 500

    # POST -> edit
    f_name = request.form.get('f_name', '').strip()
    l_name = request.form.get('l_name', '').strip()
    ph_no = request.form.get('ph_no', '').strip()
    username = request.form.get('username', '').strip()
    specialization_id = request.form.get('specialization_id')
    if not all([f_name, l_name, ph_no, username]):
        return jsonify({'ok': False, 'error': 'All fields required'}), 400
    try:
        old_username = d.username
        if username != old_username:
            # ensure uniqueness
            if Login.query.filter_by(username=username).first():
                return jsonify({'ok': False, 'error': 'Username already in use'}), 409
            login_row = Login.query.filter_by(username=old_username).first()
            if login_row:
                login_row.username = username
            d.username = username
        d.f_name = f_name
        d.l_name = l_name
        d.ph_no = int(ph_no)
        if specialization_id:
            try:
                d.specialization_id = int(specialization_id)
            except Exception:
                d.specialization_id = None
        prof = request.files.get('profile_pic')
        if prof and prof.filename:
            d.profile_pic = prof.read()
        db.session.commit()
        return jsonify({'ok': True, 'doctor': d.to_dict()})
    except ValueError:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Phone must be numeric'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/doctor/add', methods=['POST'])
@role_required(0)
def admin_add_doctor():
    f_name = request.form.get('f_name', '').strip()
    l_name = request.form.get('l_name', '').strip()
    ph_no = request.form.get('ph_no', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    specialization_id = request.form.get('specialization_id')
    if not all([f_name, l_name, ph_no, username, password]):
        return jsonify({'ok': False, 'error': 'All fields required'}), 400
    if Login.query.filter_by(username=username).first():
        return jsonify({'ok': False, 'error': 'Username already exists'}), 409
    try:
        # Ensure a department is selected (empty or default option is not allowed)
        if not specialization_id or str(specialization_id).strip() == '':
            return jsonify({'ok': False, 'error': 'Kindly select a department'}), 400
        try:
            spec_id_int = int(specialization_id)
        except Exception:
            return jsonify({'ok': False, 'error': 'Invalid department selection'}), 400

        # Set created_at so new doctors have a registration timestamp
        d = Doctor(username=username, f_name=f_name, l_name=l_name, ph_no=int(ph_no), created_at=datetime.now())
        d.specialization_id = spec_id_int
        prof = request.files.get('profile_pic')
        if prof and prof.filename:
            d.profile_pic = prof.read()
        db.session.add(d)
        login_row = Login(username=username, password=password, role=1)
        db.session.add(login_row)
        db.session.commit()
        return jsonify({'ok': True, 'doctor': d.to_dict()})
    except ValueError:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Phone must be numeric'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500



@app.route('/admin/blacklist/patient/<int:patient_id>', methods=['POST'])
@role_required(0)
def admin_blacklist_patient(patient_id: int):
    p = Patient.query.filter_by(id=patient_id).first()
    if not p:
        return jsonify({'ok': False, 'error': 'Patient not found'}), 404
    action = request.form.get('action') or request.args.get('action')
    if action not in (None, 'add', 'remove'):
        return jsonify({'ok': False, 'error': 'Invalid action'}), 400
    login_row = Login.query.filter_by(username=p.username).first()
    if not login_row:
        return jsonify({'ok': False, 'error': 'Login row not found for patient'}), 404
    try:
        if action == 'remove':
            login_row.blacklisted = False
        else:
            login_row.blacklisted = True
        db.session.commit()
        return jsonify({'ok': True, 'blacklisted': bool(login_row.blacklisted)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/admin/blacklist/doctor/<int:doctor_id>', methods=['POST'])
@role_required(0)
def admin_blacklist_doctor(doctor_id: int):
    d = Doctor.query.filter_by(id=doctor_id).first()
    if not d:
        return jsonify({'ok': False, 'error': 'Doctor not found'}), 404
    action = request.form.get('action') or request.args.get('action')
    if action not in (None, 'add', 'remove'):
        return jsonify({'ok': False, 'error': 'Invalid action'}), 400
    login_row = Login.query.filter_by(username=d.username).first()
    if not login_row:
        return jsonify({'ok': False, 'error': 'Login row not found for doctor'}), 404
    try:
        if action == 'remove':
            login_row.blacklisted = False
        else:
            login_row.blacklisted = True
        db.session.commit()
        return jsonify({'ok': True, 'blacklisted': bool(login_row.blacklisted)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/department/<int:dept_id>', methods=['POST', 'DELETE'])
@role_required(0)
def admin_edit_delete_department(dept_id: int):
    dep = Department.query.filter_by(department_id=dept_id).first()
    if not dep:
        return jsonify({'ok': False, 'error': 'Department not found'}), 404

    if request.method == 'DELETE':
        # prevent deletion if doctors are registered
        if dep.doctors and len(dep.doctors) > 0:
            return jsonify({'ok': False, 'error': 'Cannot delete department with registered doctors'}), 409
        try:
            db.session.delete(dep)
            db.session.commit()
            return jsonify({'ok': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'ok': False, 'error': str(e)}), 500

    # POST -> edit
    name = request.form.get('department_name', '').strip()
    desc = request.form.get('description', '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'Department name required'}), 400
    try:
        dep.department_name = name
        dep.description = desc
        prof = request.files.get('dep_pic')
        if prof and prof.filename:
            dep.dep_pic = prof.read()
        db.session.commit()
        return jsonify({'ok': True, 'department': dep.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/department/add', methods=['POST'])
@role_required(0)
def admin_add_department():
    name = request.form.get('department_name', '').strip()
    desc = request.form.get('description', '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'Department name required'}), 400
    try:
        dep = Department(department_name=name, description=desc)
        prof = request.files.get('dep_pic')
        if prof and prof.filename:
            dep.dep_pic = prof.read()
        db.session.add(dep)
        db.session.commit()
        return jsonify({'ok': True, 'department': dep.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/admin_update_profile', methods=['POST'])
@role_required(0)
def admin_update_profile():
    login = Login.query.filter_by(username=current_user.get_id()).first()
    admin = login.user_info if login else None
    if not admin:
        return jsonify({'ok': False, 'error': 'Admin not found'}), 404

    f_name = request.form.get('f_name', '').strip()
    l_name = request.form.get('l_name', '').strip()
    username = request.form.get('username', '').strip()
    if not all([f_name, l_name, username]):
        return jsonify({'ok': False, 'error': 'All fields required'}), 400
    try:
        old_username = admin.username
        if username != old_username:
            if Login.query.filter_by(username=username).first():
                return jsonify({'ok': False, 'error': 'Username already in use'}), 409
            login_row = Login.query.filter_by(username=old_username).first()
            if login_row:
                login_row.username = username
            admin.username = username
        admin.f_name = f_name
        admin.l_name = l_name
        prof = request.files.get('profile_pic')
        if prof and prof.filename:
            admin.profile_pic = prof.read()
        db.session.commit()
        # If we updated the login username for the currently logged-in admin, refresh the session
        try:
            if login_row:
                # re-login the user so Flask-Login session knows new id
                login_user(login_row)
        except Exception:
            pass
        return jsonify({'ok': True, 'admin': admin.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/doctor')
@role_required(1)
def doctor_dashboard():
    # Render the doctor dashboard page and provide doctor JS data
    login = Login.query.filter_by(username=current_user.get_id()).first()
    doctor = login.user_info if login else None
    if not doctor:
        flash('Doctor profile not found', 'error')
        return redirect(url_for('login_page'))

    doctor_js = doctor.to_dict() if doctor else None
    # include department name for template convenience
    if doctor_js is not None:
        try:
            doctor_js['department'] = doctor.department.department_name if doctor.department else None
        except Exception:
            doctor_js['department'] = None

    # provide list of departments for display (e.g., populate department name)
    departments = Department.query.all()
    departments_js = [d.to_dict() for d in departments]

    return render_template('doctor.html', doctor=doctor, doctor_js=doctor_js, departments_js=departments_js)



@app.route('/doctor_update_profile', methods=['POST'])
@role_required(1)
def doctor_update_profile():
    login = Login.query.filter_by(username=current_user.get_id()).first()
    doctor = login.user_info if login else None
    if not doctor:
        return jsonify({'ok': False, 'error': 'Doctor not found'}), 404

    f_name = request.form.get('f_name', '').strip()
    l_name = request.form.get('l_name', '').strip()
    ph_no = request.form.get('ph_no', '').strip()

    # Only allow those fields to be updated
    if not all([f_name, l_name, ph_no]):
        return jsonify({'ok': False, 'error': 'All fields required'}), 400

    try:
        doctor.f_name = f_name
        doctor.l_name = l_name
        doctor.ph_no = int(ph_no)
        prof = request.files.get('profile_pic')
        if prof and prof.filename:
            doctor.profile_pic = prof.read()
        db.session.commit()
        # return updated doctor dict (include department name)
        d = doctor.to_dict()
        try:
            d['department'] = doctor.department.department_name if doctor.department else None
        except Exception:
            d['department'] = None
        return jsonify({'ok': True, 'doctor': d})
    except ValueError:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Phone must be numeric'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/doctor_calendar/<int:doctor_id>', methods=['GET'])
@role_required(1)
def doctor_calendar(doctor_id: int):
    # Return availability for next 7 days including booked info with patient details
    d = Doctor.query.filter_by(id=doctor_id).first()
    if not d:
        return jsonify({'ok': False, 'error': 'Doctor not found'}), 404

    today = datetime.now().date()
    days = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]

    # Build time slots 09:00-20:00 30-min
    slots = []
    cur = datetime.strptime('09:00', '%H:%M')
    end = datetime.strptime('20:00', '%H:%M')
    while cur <= end:
        slots.append(cur.strftime('%H:%M'))
        cur += timedelta(minutes=30)

    # Query appointments for doctor in these days
    appts = Appointment.query.filter(and_(Appointment.doctor_id == doctor_id, Appointment.date.in_(days))).all()
    appt_map = {(a.date, a.time): a for a in appts if a.status != 'Cancelled'}

    availability = []
    for day in days:
        day_slots = []
        for t in slots:
            key = (day, t)
            if key in appt_map:
                a = appt_map[key]
                patient = a.patient
                patient_name = f"{patient.f_name} {patient.l_name}" if patient else None
                day_slots.append({'time': t, 'booked': True, 'appointment_id': a.id, 'patient_id': patient.id if patient else None, 'patient_name': patient_name, 'status': a.status})
            else:
                day_slots.append({'time': t, 'booked': False})
        availability.append({'date': day, 'slots': day_slots})

    return jsonify({'ok': True, 'doctor_id': doctor_id, 'availability': availability})


@app.route('/doctor_patients/<int:doctor_id>', methods=['GET'])
@role_required(1)
def doctor_patients(doctor_id: int):
    # Return unique patients who have appointments with this doctor
    d = Doctor.query.filter_by(id=doctor_id).first()
    if not d:
        return jsonify({'ok': False, 'error': 'Doctor not found'}), 404

    appts = Appointment.query.filter_by(doctor_id=doctor_id).all()
    patient_ids = sorted({a.patient_id for a in appts if a.patient_id})
    patients = Patient.query.filter(Patient.id.in_(patient_ids)).all() if patient_ids else []
    patients_js = []
    for p in patients:
        pdata = p.to_dict(include_image=False)
        # find latest appointment for this patient with this doctor
        latest = Appointment.query.filter_by(doctor_id=doctor_id, patient_id=p.id).order_by(Appointment.date.desc(), Appointment.time.desc()).first()
        if latest:
            pdata['latest_appointment'] = {'id': latest.id, 'date': latest.date, 'time': latest.time, 'status': latest.status}
        else:
            pdata['latest_appointment'] = None
        patients_js.append(pdata)
    return jsonify({'ok': True, 'patients': patients_js})


@app.route('/patient_appointments/<int:patient_id>', methods=['GET'])
@role_required(1)
def patient_appointments(patient_id: int):
    p = Patient.query.filter_by(id=patient_id).first()
    if not p:
        return jsonify({'ok': False, 'error': 'Patient not found'}), 404
    # Only patients associated with current doctor should be viewable: ensure current_user is doctor
    login = Login.query.filter_by(username=current_user.get_id()).first()
    doc = login.user_info if login else None
    if not doc:
        return jsonify({'ok': False, 'error': 'Doctor profile not found'}), 403

    # Check if patient has appointment with this doctor
    related = Appointment.query.filter_by(doctor_id=doc.id, patient_id=p.id).all()
    if not related:
        # Still allow viewing if doctor is admin? For now restrict
        return jsonify({'ok': False, 'error': 'Patient not associated with you'}), 403

    # Build appointment list sorted descending (today first)
    appts = Appointment.query.filter_by(patient_id=p.id).order_by(Appointment.date.desc(), Appointment.time.desc()).all()
    appt_list = []
    for a in appts:
        appt_list.append({'id': a.id, 'date': a.date, 'time': a.time, 'status': a.status})

    return jsonify({'ok': True, 'patient': p.to_dict(include_image=False), 'appointments': appt_list})


@app.route('/appointment/<int:appt_id>/complete', methods=['POST'])
@role_required(1)
def appointment_complete(appt_id: int):
    a = Appointment.query.filter_by(id=appt_id).first()
    if not a:
        return jsonify({'ok': False, 'error': 'Appointment not found'}), 404
    # ensure current doctor owns this appointment
    login = Login.query.filter_by(username=current_user.get_id()).first()
    doc = login.user_info if login else None
    if not doc or a.doctor_id != doc.id:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403
    try:
        a.status = 'Completed'
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/treatment/<int:appt_id>/edit', methods=['POST'])
@role_required(1)
def treatment_edit(appt_id: int):
    # Accept JSON payload with diagnosis, prescription, notes
    data = request.get_json() or {}
    diagnosis = data.get('diagnosis')
    prescription = data.get('prescription')
    notes = data.get('notes')

    a = Appointment.query.filter_by(id=appt_id).first()
    if not a:
        return jsonify({'ok': False, 'error': 'Appointment not found'}), 404
    login = Login.query.filter_by(username=current_user.get_id()).first()
    doc = login.user_info if login else None
    if not doc or a.doctor_id != doc.id:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403

    tr = Treatment.query.filter_by(id=appt_id).first()
    try:
        if not tr:
            tr = Treatment(id=appt_id, diagnosis=diagnosis, prescription=prescription, notes=notes)
            db.session.add(tr)
        else:
            tr.diagnosis = diagnosis
            tr.prescription = prescription
            tr.notes = notes
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/patient')
@role_required(2)
def patient_dashboard():
    # Get patient info
    login = Login.query.filter_by(username=current_user.get_id()).first()
    patient = login.user_info

    # Fetch appointments for patient
    appts = Appointment.query.filter_by(patient_id=patient.id).all() if patient else []

    # Prepare upcoming and past lists
    now = datetime.now()
    upcoming = []
    past = []
    for a in appts:
        try:
            dt = datetime.strptime(f"{a.date} {a.time}", "%Y-%m-%d %H:%M")
        except Exception:
            # fallback when time stored as e.g. '09:00'
            try:
                dt = datetime.strptime(a.date, "%Y-%m-%d")
            except Exception:
                dt = now
        if dt.date() < now.date() or (dt.date() == now.date() and dt < now):
            past.append((dt, a))
        else:
            upcoming.append((dt, a))

    # Sort past desc, upcoming asc
    past.sort(key=lambda x: x[0], reverse=True)
    upcoming.sort(key=lambda x: x[0])

    # Departments and doctors
    departments = Department.query.all()
    doctors = Doctor.query.all()

    # Treatments mapping (assume Treatment.id == Appointment.id if present)
    treatments = {t.id: t for t in Treatment.query.all()}

    # Prepare profile pic (base64) or None
    profile_b64 = None
    if patient and getattr(patient, 'profile_pic', None):
        profile_b64 = base64.b64encode(patient.profile_pic).decode('utf-8')

    # Convert objects to JSON-serializable structures for use with template JS
    patient_js = patient.to_dict(include_image=False) if patient else None
    # include profile_b64 separately if available
    if patient_js is not None:
        patient_js['profile_b64'] = profile_b64

    departments_js = [d.to_dict() for d in departments]
    doctors_js = [d.to_dict() for d in doctors]
    upcoming_js = [a.to_dict() for _, a in upcoming]
    past_js = [a.to_dict() for _, a in past]

    # Data for availability: default choose first dept and its first doctor (if any)
    return render_template('patient.html', patient=patient, patient_js=patient_js, profile_b64=profile_b64,
                           upcoming=[a for _, a in upcoming], past=[a for _, a in past],
                           departments=departments, doctors=doctors, treatments=treatments,
                           departments_js=departments_js, doctors_js=doctors_js, upcoming_js=upcoming_js, past_js=past_js)


@app.route('/appointment/<int:appt_id>/details', methods=['GET'])
@login_required
def appointment_details(appt_id):
    appt = Appointment.query.filter_by(id=appt_id).first()
    if not appt:
        return jsonify({'ok': False, 'error': 'Appointment not found'}), 404
    # Ensure current user owns the appointment (if patient)
    if hasattr(current_user, 'role') and int(current_user.role) == 2:
        patient = current_user.user_info
        if not patient or appt.patient_id != patient.id:
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 403

    tr = Treatment.query.filter_by(id=appt.id).first()
    return jsonify({'ok': True, 'diagnosis': tr.diagnosis if tr else None,
                    'prescription': tr.prescription if tr else None,
                    'notes': tr.notes if tr else None})


@app.route('/appointment/<int:appt_id>/cancel', methods=['POST'])
@login_required
def appointment_cancel(appt_id):
    appt = Appointment.query.filter_by(id=appt_id).first()
    if not appt:
        return jsonify({'ok': False, 'error': 'Appointment not found'})
    patient = current_user.user_info
    if not patient or appt.patient_id != patient.id:
        return jsonify({'ok': False, 'error': 'Unauthorized'})
    try:
        appt.status = 'Cancelled'
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/department/<int:dept_id>', methods=['GET'])
@login_required
def department_info(dept_id):
    d = Department.query.filter_by(department_id=dept_id).first()
    if not d:
        return jsonify({'ok': False, 'error': 'Department not found'}), 404
    doctors_list = [{'id': doc.id, 'f_name': doc.f_name, 'l_name': doc.l_name} for doc in d.doctors]
    return jsonify({'ok': True, 'department_name': d.department_name, 'description': d.description, 'doctors': doctors_list})


@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    patient = current_user.user_info
    if not patient:
        return jsonify({'ok': False, 'error': 'Patient not found'})
    f_name = request.form.get('f_name', '').strip()
    l_name = request.form.get('l_name', '').strip()
    ph_no = request.form.get('ph_no', '').strip()
    if not all([f_name, l_name, ph_no]):
        return jsonify({'ok': False, 'error': 'All fields required'})
    try:
        patient.f_name = f_name
        patient.l_name = l_name
        patient.ph_no = int(ph_no)
        # optional profile pic update
        prof = request.files.get('profile_pic')
        if prof and prof.filename:
            patient.profile_pic = prof.read()
        db.session.commit()
        return jsonify({'ok': True})
    except ValueError:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Phone must be numeric'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/avatar/<int:patient_id>')
@login_required
def avatar(patient_id: int):
    """Return profile image bytes for patient or a 302 to placeholder if missing.

    This route uses simple image type detection and returns a Response with proper
    Content-Type. It intentionally avoids exposing raw file system paths.
    """
    p = Patient.query.filter_by(id=patient_id).first()
    if not p or not getattr(p, 'profile_pic', None):
        # Redirect to the local default avatar image
        return redirect(url_for('static', filename='Images/Default_Pic.webp'))

    img_bytes = p.profile_pic
    # Try to detect image type
    try:
        kind = imghdr.what(None, h=img_bytes)
    except Exception:
        kind = None
    content_type = f'image/{kind}' if kind else 'application/octet-stream'
    return Response(img_bytes, mimetype=content_type)


@app.route('/doctor_avatar/<int:doctor_id>')
@login_required
def doctor_avatar(doctor_id: int):
    d = Doctor.query.filter_by(id=doctor_id).first()
    if not d or not getattr(d, 'profile_pic', None):
        # Redirect to the local default avatar image for doctors
        return redirect(url_for('static', filename='Images/Default_Pic.webp'))
    img_bytes = d.profile_pic
    try:
        kind = imghdr.what(None, h=img_bytes)
    except Exception:
        kind = None
    content_type = f'image/{kind}' if kind else 'application/octet-stream'
    return Response(img_bytes, mimetype=content_type)


@app.route('/admin_avatar/<int:admin_id>')
@login_required
def admin_avatar(admin_id: int):
    a = Admin.query.filter_by(id=admin_id).first()
    if not a or not getattr(a, 'profile_pic', None):
        return redirect(url_for('static', filename='Images/Default_Pic.webp'))
    img_bytes = a.profile_pic
    try:
        kind = imghdr.what(None, h=img_bytes)
    except Exception:
        kind = None
    content_type = f'image/{kind}' if kind else 'application/octet-stream'
    return Response(img_bytes, mimetype=content_type)


@app.route('/doctor/<int:doctor_id>', methods=['GET'])
@login_required
def doctor_info(doctor_id: int):
    d = Doctor.query.filter_by(id=doctor_id).first()
    if not d:
        return jsonify({'ok': False, 'error': 'Doctor not found'}), 404
    dept = d.department.department_name if d.department else None
    return jsonify({'ok': True, 'id': d.id, 'username': d.username, 'f_name': d.f_name, 'l_name': d.l_name,
                    'ph_no': d.ph_no, 'department': dept,
                    'avatar_url': url_for('doctor_avatar', doctor_id=d.id)})


@app.route('/availability/<int:doctor_id>', methods=['GET'])
@login_required
def doctor_availability(doctor_id: int):
    d = Doctor.query.filter_by(id=doctor_id).first()
    if not d:
        return jsonify({'ok': False, 'error': 'Doctor not found'}), 404

    # Build next 7 days including today
    days = []
    today = datetime.now().date()
    for i in range(7):
        dt = today + timedelta(days=i)
        days.append(dt.strftime('%Y-%m-%d'))

    # Build slots from 09:00 to 20:00 in 30-min steps
    slots = []
    start = datetime.strptime('09:00', '%H:%M')
    end = datetime.strptime('20:00', '%H:%M')
    cur = start
    while cur <= end:
        slots.append(cur.strftime('%H:%M'))
        cur += timedelta(minutes=30)

    # Query existing appointments for this doctor in the range
    appts = Appointment.query.filter(and_(Appointment.doctor_id == doctor_id, Appointment.date.in_(days))).all()
    booked = set((a.date, a.time) for a in appts if a.status != 'Cancelled')

    # Prepare availability structure: list of days each with list of slots
    availability = []
    for day in days:
        day_slots = []
        for t in slots:
            is_booked = (day, t) in booked
            day_slots.append({'time': t, 'booked': is_booked})
        availability.append({'date': day, 'slots': day_slots})

    return jsonify({'ok': True, 'doctor_id': doctor_id, 'availability': availability})


@app.route('/book_appointment', methods=['POST'])
@login_required
def book_appointment():
    data = request.get_json() or request.form
    try:
        doctor_id = int(data.get('doctor_id'))
        date_str = data.get('date')
        time_str = data.get('time')
    except Exception:
        return jsonify({'ok': False, 'error': 'Missing parameters'}), 400

    # Validate inputs
    d = Doctor.query.filter_by(id=doctor_id).first()
    if not d:
        return jsonify({'ok': False, 'error': 'Doctor not found'}), 404
    # Validate date format
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        datetime.strptime(time_str, '%H:%M')
    except Exception:
        return jsonify({'ok': False, 'error': 'Invalid date/time format'}), 400

    patient = current_user.user_info
    if not patient:
        return jsonify({'ok': False, 'error': 'Patient not found'}), 403

    # Check slot availability
    exists = Appointment.query.filter_by(doctor_id=doctor_id, date=date_str, time=time_str).first()
    if exists and exists.status != 'Cancelled':
        return jsonify({'ok': False, 'error': 'Slot already booked'}), 409

    # Create appointment
    try:
        appt = Appointment(patient_id=patient.id, doctor_id=doctor_id, date=date_str, time=time_str, status='Booked')
        db.session.add(appt)
        db.session.commit()
        return jsonify({'ok': True, 'appointment_id': appt.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Collect form data
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        f_name = request.form.get('f_name', '').strip()
        l_name = request.form.get('l_name', '').strip()
        ph_no = request.form.get('ph_no', '').strip()

        # Basic validation
        if not all([username, password, confirm_password, f_name, l_name, ph_no]):
            flash('All fields are required', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')

        # Save to DB: create Patient and Login entries
        try:
            # Explicitly set created_at so 'member since' is populated on registration
            patient = Patient(username=username, f_name=f_name, l_name=l_name, ph_no=int(ph_no), created_at=datetime.now())
            # Handle optional profile picture
            profile_file = request.files.get('profile_pic')
            if profile_file and profile_file.filename:
                # Read bytes and store in patient.profile_pic
                patient.profile_pic = profile_file.read()

            db.session.add(patient)
            # The Login row stores username, password and role (2 for patient)
            login_row = Login(username=username, password=password, role=2)
            db.session.add(login_row)
            db.session.commit()
        except ValueError:
            db.session.rollback()
            flash('Phone number must be numeric', 'error')
            return render_template('register.html')
        except IntegrityError as e:
            db.session.rollback()
            # Most likely username already exists in Login or Patient
            flash('Username already registered', 'error')
            return render_template('register.html')
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'error')
            return render_template('register.html')

        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('login_page'))

    return render_template('register.html')