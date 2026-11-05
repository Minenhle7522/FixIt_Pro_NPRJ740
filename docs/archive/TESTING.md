# FixIt Pro — NRPJ740 Testing Evidence

## Purpose
This testing record supports the software quality and verification requirements of the NRPJ740 Advanced Diploma Project. It covers authentication, role-based access, maintenance workflow, SLA logic, evidence uploads, notifications, reporting, and embedded-system interoperability.

## Automated test execution
Command:

```powershell
python manage.py test
```

Latest controlled test run:

- **28 tests executed**
- **28 passed**
- **0 failed**
- Django system check: **0 issues**
- Migration consistency check: **No changes detected**
- Static collection check: **126 static files copied successfully**

## Functional test matrix

| ID | Area | Test | Expected result |
|---|---|---|---|
| TC-01 | Home | Open landing page | FixIt Pro landing page loads |
| TC-02 | Registration | Register tenant with valid data | Tenant account is created and redirected to tenant portal |
| TC-03 | Login | Login as tenant | Tenant dashboard is opened |
| TC-04 | Login | Login as staff | Staff dashboard is opened |
| TC-05 | Login | Login as administrator | Admin dashboard is opened |
| TC-06 | Access control | Tenant opens admin/staff portal | Access is denied/redirected |
| TC-07 | Access control | Staff opens admin portal | Access is denied/redirected |
| TC-08 | Request | Tenant submits maintenance request | Request is stored with SLA deadline and notification |
| TC-09 | Request | Tenant views own request | Request details and status history are displayed |
| TC-10 | Evidence | Upload PDF/image attachment | Attachment is stored against the request |
| TC-11 | Assignment | Admin assigns active staff member | Assignment and audit information are recorded |
| TC-12 | Workflow | Move request through valid statuses | Status changes are accepted and history recorded |
| TC-13 | Workflow | Attempt invalid status transition | Transition is rejected |
| TC-14 | Staff | Staff accepts assigned job | Status becomes Accepted |
| TC-15 | Staff | Staff records diagnosis/notes and submits work log | Work information is stored |
| TC-16 | Completion | Staff completes repair | Completion timestamp and resolution are stored |
| TC-17 | Verification | Tenant verifies completed repair | Status becomes Verified |
| TC-18 | Feedback | Tenant submits rating/comment | Feedback is stored against request |
| TC-19 | Closure | Admin closes verified request | Status becomes Closed |
| TC-20 | SLA | Overdue request is processed | Request is marked SLA breached |
| TC-21 | Notification | User marks notification as read | Notification changes to read |
| TC-22 | Reporting | Admin generates detailed report | Report displays filtered request data |
| TC-23 | Staff work log | Staff submits work performed after Start Work; date/time are captured automatically | Work log is stored and confirmation contains no wage/cost |
| TC-24 | Financial security | Staff opens own work-order page | Hourly rate and labour cost are not displayed |
| TC-25 | Financial calculation | System records 2.5 elapsed work hours at admin-approved R250/hour | System calculates R625 labour cost server-side |
| TC-26 | Work-log validation | Staff attempts a second work-log submission | Submission is rejected and the original work log is preserved |
| TC-27 | Ownership | Staff attempts to log work against another technician's request | Access is denied and no work log is created |
| TC-28 | IoT security | Sensor sends invalid API key | Request is rejected with HTTP 401 |
| TC-29 | IoT integration | Registered sensor sends valid event | Sensor reading and maintenance request are created |
| TC-30 | IoT validation | Unknown sensor sends event | Request is rejected with HTTP 404 |
| TC-31 | IoT validation | Sensor sends non-numeric reading | Request is rejected with HTTP 400 |

## Manual demonstration checklist

Before the final presentation, execute this sequence on the Windows development machine and capture screenshots/video evidence:

1. Start the application.
2. Open the FixIt Pro landing page.
3. Log in as the demo tenant.
4. Submit a new urgent plumbing/electrical request.
5. Upload a valid photo.
6. Confirm the generated request ID and SLA deadline.
7. Log in as administrator.
8. Locate the new request.
9. Assign it to `staff`.
10. Confirm the staff notification.
11. Log in as maintenance staff.
12. Accept the job.
13. Change status to In Progress.
14. Add diagnosis and work notes.
15. Click Start Work, confirm the start timestamp is automatic, then submit one work log containing only the work performed.
16. Record any parts/materials used.
17. Confirm the staff portal does not display wage/labour-cost information.
18. Complete the repair.
19. Log in as tenant.
20. Verify the repair or reopen it if demonstrating the exception workflow.
21. Submit service feedback.
22. Log in as administrator and close the verified request.
23. Generate a detailed report.
24. Demonstrate the IoT endpoint using the registered `WLS-001` sensor.
25. Confirm the sensor reading and automatically generated maintenance request.


## Evidence to retain for the final report

- Screenshots of each major GUI screen.
- Screenshot of successful request submission.
- Screenshot of admin assignment.
- Screenshot of staff work update.
- Screenshot of completed/verified request.
- Screenshot of notifications.
- Screenshot of reports.
- Screenshot of IoT request/response.
- Test command output showing all automated tests passed.
- Final database/ERD matching the implemented models.
