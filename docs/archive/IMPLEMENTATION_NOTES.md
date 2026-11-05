# FixIt Pro — real-world contractor workflow build

## Implemented in this code package
- **Tenant approval**: new self-registered tenants are inactive until the landlord verifies tenancy and approves them under Admin Dashboard → Verify Tenants. Existing demo accounts remain active. Verify the tenant agreement and unit outside the app; the app does not authenticate documents.
- **Incident date**: optional date/time when a fault was first noticed, separate from automatic submission timestamp.
- **Contractor quotations**: newly submitted tenant requests require a quotation. Assigned contractor accepts the job, submits labour/material estimate, landlord approves/rejects it, and the contractor can only start after approval. Legacy requests retain the previous flow (`quotation_required=False`). Contractor's own quotation is visible to them; approved totals appear in landlord portal.
- **Costs**: for new quote-required jobs, labour cost uses the approved fixed quotation amount instead of elapsed clock time. Materials use actual recorded item costs. Quotes are estimates, not actual transfers. The system does not integrate with a bank.
- **Assignment decline**: assigned contractor can decline with a reason; request is reopened and landlord is notified for reassignment.
- **Payment evidence**: landlord records amount, date, reference, optional proof; contractor independently confirms receipt or disputes. A recorded payment is NOT proof that money moved; confirmation and uploaded evidence are distinct records.
- **Password recovery**: Django reset-by-email and authenticated password change. Development email backend may only print links to the terminal.
- **State guards**: prevent additional notes/evidence on completed/closed/cancelled jobs; block admin editing terminal jobs.

## Installation on Windows (VS Code PowerShell)
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python setup.py
python manage.py test
python manage.py runserver
```
Existing test users can be seeded using `setup.py`. New self-registered tenant accounts require landlord activation.

## Important limitations before final submission
- This build has been **syntax-checked**, but could not run Django migrations or runtime tests in the authoring environment because Django was unavailable and dependency installation was blocked. Run `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py migrate`, and `python manage.py test` on your PC. Report errors for correction.
- Quotation approval uses a **fixed agreed labour amount**, rather than timesheet-derived pay. If scope changes, reject and resubmit a quote before work begins. The original one-work-log-per-request model remains.
- The current request model stores only the latest assigned contractor; a reopened/reassigned repair can involve multiple work cycles. Full multi-visit accounting would require a separate WorkOrder/RepairVisit model. Avoid reassigning completed paid work without reviewing historical records.
- Payment proof files use Django's development media storage. **Do not upload real bank statements or personal financial documents to a publicly accessible development server.** Production use requires private authenticated file delivery, secure storage and appropriate retention rules.
- No banking transfer or multi-landlord data isolation is implemented. Real-world deployment would also require proper email SMTP configuration, security review, HTTPS, backup and deployment hardening.
- SLA calculation still uses existing priority-based elapsed deadlines; a full SLA pause/resume and contractor rejection timer model is not yet implemented. This is not a finished production system.
- Update the report/diagrams only after final features and tests are verified.
