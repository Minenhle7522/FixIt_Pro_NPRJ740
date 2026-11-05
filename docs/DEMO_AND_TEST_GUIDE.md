# Lease-linked tenant registration and appointments

1. Run `python manage.py migrate`, then `python setup.py` for the demo accounts.
2. Log in as admin/password123 and open `/admin-panel/leases/` (if the app prefix differs, use the Admin dashboard link or inspect `maintenance_system/urls.py`). Create a lease with the tenant email, residence, room, floor and dates. Share its invitation code privately.
3. Register a new tenant using the exact lease email and invitation code; the tenant does not select a room. Approve them under pending tenants. Login should be blocked until approval.
4. Login as the tenant. Submit a request; verify residence and room come from the approved lease, while problem area remains editable.
5. Admin opens request detail and proposes a future appointment. Tenant opens request detail to confirm or request a new time. A proposed visit is NOT a confirmed visit.
6. Existing demo tenant receives a demo verified lease via setup.py.

Important limitations: appointment status is stored and visible to landlord and tenant; contractor visit attendance, automated reminder emails, emergency entry, lease document uploads, and automatic SLA adjustments for tenant availability are NOT implemented. Existing requests are retained without a lease FK. Run full Django tests locally before submission.

## Final workflow (what to click when you test)
1. **Landlord** (admin): Leases -> create lease for the tenant's email (copy the invitation code). Pending tenants -> approve after the tenant registers.
2. **Tenant**: register with the invitation code and the SAME email. After approval: submit a request. Ticking *safety risk* raises the priority to at least High and flags it to the landlord (notification, email, dashboard).
3. **Landlord**: assign a contractor (tick *Emergency call-out* on an URGENT request if work must start before the quote is approved).
4. **Contractor**: Accept -> submit a quotation (labour = the price; materials and hours optional). **Landlord**: approve, or reject WITH A REASON; the contractor revises and resubmits (revision 2, 3...).
5. **Visit** (only after the contractor accepted): the **contractor** offers his availability to the landlord; the **landlord** picks a time that suits the tenant and proposes it. The **tenant** confirms, or says "I cannot make this time" (reason required) and the landlord proposes another. Work cannot start until the tenant has confirmed, and then only from 30 minutes before the visit time.
6. **Contractor**: Start Work -> save the visit / access record. If *No access*, the landlord and tenant are notified and a new tenant-confirmed visit is needed before the record can be changed to *Access gained*. Upload a work photo (JPG/PNG), then Mark complete.
7. **Tenant**: "Fixed" or "Not fixed". Not fixed: the landlord is notified, the SAME contractor stays, the landlord presses *Alert contractor*; the contractor **offers availability to the landlord**, the landlord sends it to the tenant, the tenant confirms.
8. **Landlord**: after the tenant verifies, record the payment (amount calculated, proof uploaded). **Contractor** confirms receipt. The landlord can close only once the contractor is paid in full. A closed request can be reopened by the tenant for 7 days.

## Forgot password (tenant, contractor or landlord)
1. On the sign-in page click **Forgot password?** and enter the email on the account.
2. An email is sent with the username and a one-time link (valid 1 hour). In development it is **printed in the server window** (console); to send real email copy `.env.example` to `.env` and fill in `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` (Gmail needs an App Password).
3. Open the link, choose a new password (it must pass the password rules), then sign in. The old password stops working and the link cannot be reused.
4. Tenants still awaiting landlord approval, and unknown emails, receive no email (the page looks the same either way).

## Verified build notes
- `python manage.py check`, `makemigrations --check --dry-run` and `python manage.py test` (113 ) all pass.
- Demo logins after `python setup.py`: admin / contractor / contractor2 / tenant, all password `password123`.
- Fixes in this build: missing import that stopped the server, duplicated model fields, contractor form lease-code bug, pending-login message, appointment panels inside the page title, duplicate quotation/payment forms, one-work-log-per-request constraint (now per visit round), emergency quote review, calculated payments.

- Demo data: after `python setup.py` run `python demo_data.py` to stage nine requests across every stage (quotation pending/rejected, in progress, completed, verified-awaiting-payment, emergency, no-access, closed).

## Robustness rules (added after review)
- **Start only at the visit:** after the tenant confirms, the contractor can press Start Work from 30 minutes before the visit time (emergency call-outs are exempt).
- **Contractor not responding:** an assignment not accepted after 24 h, or an accepted job with no visit after 48 h, shows a warning to the landlord and a reminder notification (Dashboard > process SLA, or `python manage.py check_sla`). Before work starts the landlord can **Replace contractor** (reason required; visits and unanswered quotations are cancelled, tenant and old contractor are told).
- **SLA fairness:** while a visit proposal waits for the tenant, the SLA clock is paused; the waiting time is added to the deadline when the tenant answers.
- **Production safety:** with `DJANGO_DEBUG=0` the system refuses to start unless `DJANGO_SECRET_KEY` and `FIXIT_IOT_API_KEY` are set to private values, and cookies become HTTPS-only.
