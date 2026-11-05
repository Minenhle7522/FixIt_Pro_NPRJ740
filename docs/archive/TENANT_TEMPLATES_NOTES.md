# Tenant registration and maintenance intake update

- Tenant registration now presents landlord verification clearly. The existing admin Pending Tenants screen approves users. This is **approval-based registration**, not an invitation-link system.
- Tenant email uniqueness validation added.
- Maintenance form shows the registered tenant room and prevents changing it on request submission (server-side and UI).
- Added entry permission, preferred visit time and safety risk flag; stored in the database using migration `requests_app.0008_tenant_intake_fields`.
- Existing incident timestamp, urgency, photo, category, location and description are retained.
- Emergency guidance is displayed; submitting a request is **not** an emergency dispatch mechanism.
- Existing role routes and contractor quotation/payment features are preserved.

## Run on Windows

```
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

## Verification status
Python syntax was checked. Django was not installed in the packaging environment, so migration execution and functional/end-to-end tests have **not** been run. Verify registration, landlord approval, room immutability and request submission in the actual Django app.
