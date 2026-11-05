# FixIt Pro - Final Workflow Notes

## Final role workflow
Tenant submits -> Admin reviews/assigns -> Staff accepts -> Staff starts work -> Staff submits one work log and optional work evidence/materials -> Staff completes -> Tenant confirms Fixed or Not Fixed -> Admin closes only after successful tenant verification.

## Business rules implemented
- Tenant is not required/allowed to upload completion evidence. The tenant verifies the outcome.
- Staff may upload work evidence.
- A verified repair cannot be assigned/reassigned. Admin closes it.
- If tenant reports Not Fixed, the request is reopened, Admin is notified, and assignment returns to Admin.
- Staff start/completion timestamps are automatic.
- Labour/material/total costs are server-calculated. Admin does not manually type calculated totals.
- Approved hourly rate is admin-controlled and locks after work has started.
- Tenant feedback is limited to one submission per request.
- New requests email active Admin users and create in-system Admin notifications.
- Reopened/not-fixed requests email Admin and create in-system Admin notifications.
- Status changes create in-system notifications.

## Stable demo logins
- tenant / password123
- staff / password123
- staff2 / password123
- admin / password123

`setup.py` is idempotent and resets these demo credentials to the documented values each time it runs.

## Verification note
Python source compilation and static workflow checks were completed in the packaging environment. Full Django runtime tests must be run on the target Windows/VS Code environment because Django packages could not be installed in the packaging environment (network package access unavailable).
