# IITM Hospital Management System — MAD-1 Project

**Package Manager:** `uv`

## Project Overview

This repository contains the IITM Hospital Management System created for the MAD-1 course project. It's a lightweight web application (backend + templated frontend) that provides basic hospital management features such as user authentication, patient and doctor views, and appointment scheduling. The project is implemented in Python using the Flask web framework with RESTful endpoints.

## Key Features

- **Patient & Doctor Views:** templated UI under `templates/` for patient and doctor interactions.
- **Appointments API:** REST resources exposed under `/api/appointments` and public availability endpoints.
- **SQLite Database:** local persistence using `db/HMS_IITM.sqlite3` for development.
- **Modular App Layout:** application logic organized under the `application/` package.

## Tech Stack

- **Language:** Python
- **Web framework:** Flask (+ Flask-RESTful)
- **Database:** SQLite (file: `db/HMS_IITM.sqlite3`)
- **Frontend:** server-rendered Jinja2 templates in `templates/`, static assets in `static/`

## Repository Layout

- `main.py` — application factory and entry point (runs on port 8000 by default).
- `application/` — core package (controllers, API resources, models, db setup, config).
- `templates/` — HTML templates for `admin`, `doctor`, `patient`, etc.
- `static/` — CSS, images and other static assets.
- `db/` — local SQLite database file used for development.
- `api_public_availability.yaml`, `api_user_activity.yaml` — API documentation / specs.

## Quick Start (Windows)

1. Create a virtual environment (recommended) and activate it.

For `cmd.exe`:

```bat
python -m venv .venv
.\.venv\Scripts\activate
```

For PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies.

Install from `pyproject.toml` (if using editable install):

```bat
pip install -e .
```

3. Set any environment variables (optional).

```bat
set FLASK_ENV=development
```

4. Run the application.

```bat
python main.py
```

The app listens on `0.0.0.0:8000` by default. Open `http://localhost:8000` in a browser.

## Configuration

- Configuration objects live in `application/config.py` and `application/config.py` is referenced by `main.py`. By default the app loads `LocalDevelopmentConfig` unless `FLASK_ENV` is set to `testing` or `production` (those are currently unimplemented placeholders).

## Database

- The project uses an SQLite file at `db/HMS_IITM.sqlite3`. For simple local development the file is committed in the `db/` folder — in production you should migrate to a managed DB and add proper migrations.

## API Documentation

- Basic API specs are provided in `api_public_availability.yaml` and `api_user_activity.yaml` for reference. The REST endpoints are defined in `application/api_appointments.py` and registered in `main.py`.

## Package Manager

- This project uses the `uv` Python package manager to manage dependencies and run project scripts. References to "UV" in project notes refer to the `uv` package manager (not a person).

## License

This project is licenced under [MIT License](LICENSE)
