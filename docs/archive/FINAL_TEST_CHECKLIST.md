# FixIt Pro — Final Testing Checklist (NRPJ740)

Use this checklist before the final report is frozen. Record screenshots/results for the final verification section.

## 1. Automated verification
Run `RUN_TESTS.bat`. The required result is: Django check passes, no missing migrations are reported, and the complete automated test suite passes.

## 2. Tenant workflow
- Log in as `tenant` / `password123`.
- Submit a valid request with title, description, category, priority and location.
- Confirm redirect to Tenant Dashboard and the success message `Request #... submitted successfully.`
- Confirm the request appears in the tenant's list and can be opened.
- Submit an invalid request (for example, omit the room/unit number) and confirm validation prevents creation.
- Upload valid evidence and verify it is attached to the correct request.

## 3. Administrator workflow
- Log in as `admin` / `password123`.
- Confirm the new request is visible.
- Review it and assign it to `staff`.
- Confirm administrator-only information includes the approved hourly rate, labour cost, material cost and total cost.
- Confirm request history/audit information is available.
- Confirm reports/dashboard statistics load.

## 4. Maintenance staff workflow
- Log in as `staff` / `password123`.
- Confirm only assigned jobs are accessible.
- Accept the assigned job, then Start Work.
- Click Start Work, confirm the start timestamp is automatic, then submit one work log containing only the work performed.
- Confirm the success message is exactly `Work log successfully submitted.` and does NOT reveal wage, hourly rate or labour cost.
- Record a material/part used.
- Add resolution notes and mark the job Completed.
- Confirm completion is rejected if no work log or no resolution notes exist.

## 5. Completion and feedback
- Log back in as the tenant.
- Confirm the completed status and resolution can be reviewed.
- Verify the repair and submit feedback.
- Log in as Admin and confirm the final financial summary and request state.

## 6. Email notification
The development configuration uses Django's console email backend by default. Submit a tenant request and confirm a new-maintenance-request email is printed in the VS Code terminal for the active administrator. The automated suite also verifies that an active administrator is addressed by the notification email. Configure real SMTP only after the core workflow is stable.

## 7. Access-control and failure checks
- Tenant cannot access Admin or Staff management pages.
- Staff cannot access the Admin portal or another technician's work records.
- Invalid status jumps are rejected.
- Staff cannot see approved hourly rate/labour-cost information.
- Invalid attachment/work-log data is rejected with a useful message.

## 8. Browser/UI verification
Test the main journeys in current Chrome and Edge. Check responsive layout, navigation, forms, tables, status badges, success/error messages and motion effects. Verify that the interface remains usable with reduced-motion enabled in the operating system/browser.

## 9. Final-release rule
Only mark a capability as **Included** in the final report after it passes its relevant tests. Anything intentionally not delivered should be recorded as Excluded or Deferred rather than described as implemented.

## 8. Redundancy and privacy checks
- Confirm Staff has no `Update Work Order` page/button; workflow actions are Accept Job, Start Work, Awaiting Parts/Resume (when applicable), and Mark Task Complete.
- Confirm Staff never types start/end time and cannot submit more than one work log per request.
- Confirm the Tenant request page contains no financial/cost statement.
- Confirm a Tenant can submit feedback only once for a request; after submission the saved feedback is displayed instead of another form.
- Confirm Admin cannot mark technician work complete on the technician's behalf; completion belongs to the assigned Staff workflow.
