from flask import Flask, request, render_template, redirect, url_for, jsonify, flash, session
from flask import current_app as app
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from .models import Login, Patient
from .database import db
from sqlalchemy.exc import IntegrityError

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
            # Note: If passwords changed to hashed passwords later, replace this comparison with a hash check.``
            flash('Invalid username or password', 'error')
            return render_template('login.html')

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
    return render_template('placeholder.html', title='Admin Dashboard', message='Welcome, Admin!')


@app.route('/doctor')
@role_required(1)
def doctor_dashboard():
    return render_template('placeholder.html', title='Doctor Dashboard', message='Welcome, Doctor!')


@app.route('/patient')
@role_required(2)
def patient_dashboard():
    return render_template('placeholder.html', title='Patient Dashboard', message='Welcome, Patient!')


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
            patient = Patient(username=username, f_name=f_name, l_name=l_name, ph_no=int(ph_no))
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