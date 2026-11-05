# FixIt Pro — Residence Maintenance Request & Management System

NPRJ740 Final Project · Sol Plaatje University · Advanced Diploma in ICT (2026)

FixIt Pro is a Django web application that manages maintenance in a rented residence the way it works in practice:
a verified tenant reports a fault, the landlord prioritises it and assigns a contractor, the cost is agreed through an
approved quotation, visits are confirmed by the tenant, the contractor records the visit, the tenant verifies the repair,
and payment is calculated and evidenced before the landlord closes the request.

## Roles
| Role | What they do |
|---|---|
| **Tenant** | Registers with a landlord-issued lease invitation code, submits and tracks requests, confirms visits, verifies a repair or reports it as not fixed, gives feedback |
| **Landlord / Administrator** | Creates leases and invitation codes, approves tenants, assigns contractors, approves quotations and SLA pauses, proposes visits, records payment (proof upload), closes requests, runs reports |
| **Contractor** (app name `staff`) | Accepts or declines jobs, submits a quotation, proposes visits, saves the contractor visit / access record, completes jobs, confirms or disputes payment |

## Request lifecycle
`Submitted → (Under review) → Assigned → Accepted → In progress ⇄ Awaiting parts → Completed → Verified → Closed`
· Cancel is possible until work starts · A declined job returns to the landlord · "Not fixed" reopens the job and the **same contractor** returns.

## Technology
Python 3.11 · Django 5.0 · SQLite · Bootstrap 5 (CDN) · Pillow (image validation) · python-dotenv.

## Setup (Windows, Python 3.11)
```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python setup.py            # creates the demo accounts below (safe to re-run)
python manage.py runserver
```
Open <http://127.0.0.1:8000/>. `setup_windows.bat` performs the same steps automatically; `RUN_TESTS.bat` runs the checks and tests.
On Linux/macOS use `python3 -m venv venv && source venv/bin/activate` instead.

### Optional configuration (`.env`)
Copy `.env.example` to `.env`. Without email settings, emails (including password-reset links) are **printed in the server window**.
Set `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` (for Gmail an *App password*) to send real email.

## Demo accounts (created by `python setup.py`; password for all: `password123`)
| Username | Role | Notes |
|---|---|---|
| `admin` | Landlord / Administrator | Also a Django superuser (`/admin/`) |
| `tenant` | Tenant | Has a demo lease (Demo Residence, unit A101) |
| `contractor` | Contractor (Mike Contractor) | |
| `contractor2` | Contractor (Sarah Contractor) | |

Change these passwords for any real use.

## Tests
```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test        # 79 automated tests
```

## Repository layout
```
accounts/           custom User model, Lease, login, lease-based registration, password reset
requests_app/       MaintenanceRequest domain models, tenant workflow, forms, services.py, IoT API, tests.py, management/commands
admin_panel/        landlord portal (leases, tenant approval, assignment, quotations, visits, payments, reports)
staff/              contractor portal (jobs, quotation, visit record, completion, payment confirmation)
maintenance_system/ settings, root URLs, context processors, WSGI
templates/          Bootstrap templates grouped by app
docs/               demo/test guide (archive/ holds superseded development notes)
```

## Release identification (for assessment)
Repository URL: *add after pushing* · Release tag: `v1.0-final` · Commit: *add hash*
```bash
git add . && git commit -m "NPRJ740 final submission"
git tag -a v1.0-final -m "Final assessed version"
git push origin main --tags
```
