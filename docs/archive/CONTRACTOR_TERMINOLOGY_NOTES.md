# Contractor terminology update

The third user role is now displayed as **Contractor** in the Django role choices and user-facing template text. Existing `role='staff'` records and internal URLs, view names, template variables, and model fields are intentionally retained for compatibility with the current database and existing automated tests. The landlord is the Admin.

Apply: `python manage.py migrate` after installing dependencies.

This is a terminology and compatibility update, not a verified end-to-end implementation of all contractor workflow scenarios. Test quotation approval, payment acknowledgement, permissions and navigation before submission.
