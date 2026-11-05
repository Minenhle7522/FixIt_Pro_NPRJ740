# FixIt Pro — Lecturer feedback implementation build

This is a DEVELOPMENT/TESTING build, not a certified final release. Run `python manage.py check`, `python manage.py migrate`, `python manage.py test` and manual role-based checks before submission. No Django runtime test was possible in the preparation environment.

## Changes
- New tenant requests require contractor quotation approval. Legacy requests retain their prior quotation_required value for compatibility.
- Restored quotation/payment forms to the correct Django template content blocks; previously the title blocks incorrectly contained markup.
- SLA response and resolution targets now depend on priority (urgent 15 minutes/4 hours; high 1/24 hours; medium 4/48 hours; low 24/120 hours). These are proposed residence policies, not legal or industry guarantees.
- Separate response and original resolution deadline fields, with an adjustable resolution deadline.
- Contractor enters reason for awaiting parts; landlord can approve the SLA pause; approved waiting time is added when contractor resumes. Original deadline is retained for audit.
- Breached SLAs warn but do not block completion.
- Landlord recent requests are sorted by urgency.
- Existing contractor quotations, payment acknowledgement, tenant approval and tenant intake fields remain.

## Known limitations requiring design/testing decisions
- SLA adjustment currently happens when work resumes, not during an ongoing approved pause; overdue alerts during an active pause are suppressed. Test midnight/date boundaries and pause/reject/re-approve scenarios.
- Historic requests have null original/response deadline fields; new requests get populated. Existing SLA values are preserved.
- The one-work-log model and time-based cost fallback remain for legacy requests. Quotation-required jobs use approved quotation labour; multiple visits/variation orders are not fully modelled.
- Multi-landlord tenancy is not implemented.
- No real payment transfer occurs: payment evidence is recorded and acknowledged.
- All database migrations and end-to-end functionality MUST be verified on a machine with Django installed.

## Suggested manual checks
1. New tenant registration is blocked pending landlord approval. Landlord approves; tenant signs in.
2. Tenant reports blocked shower with incident date, location, access permission, photo and priority. Confirm the room is prefilled.
3. Landlord sees urgent before low-priority issues, reviews and assigns a contractor.
4. Contractor declines a job; landlord can reassign. Repeat and accept.
5. Contractor submits quotation; starting before approval must fail. Landlord approves; start now succeeds.
6. Contractor marks Awaiting Parts with reason; landlord approves pause; resume later; adjusted SLA increases, original deadline stays unchanged.
7. Contractor submits one work log, materials and completion notes. Second log must be rejected; SLA breach must not block completion.
8. Tenant verifies repair or reports it unfixed; landlord closes verified repair.
9. Landlord records payment; contractor confirms or disputes. Tenant cannot see payment details.
10. Verify closed/cancelled jobs cannot accept contractor notes or materials; test password reset and role-based access.
