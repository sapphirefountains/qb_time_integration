import frappe
import json

@frappe.whitelist(allow_guest=True)
def qb_timesheet_webhook(*args, **kwargs):
    # 1. Get the raw data sent by QuickBooks
    webhook_data = frappe.request.get_data()

    # 2. Add security verification here (e.g., check a secret token from QuickBooks)
    # if not verify_signature(webhook_data):
    #     frappe.throw("Unauthorized Request")

    try:
        # 3. Parse the data
        data = json.loads(webhook_data)
        timesheet_info = data.get('timesheets')[0] # Example structure

        # 4. Map QuickBooks data to ERPNext fields
        # This is where the core logic will go
        employee_id = get_erpnext_employee(timesheet_info.get('user_id'))
        project_id = get_erpnext_project(timesheet_info.get('jobcode_id'))

        # 5. Create the ERPNext Time Log document
        time_log = frappe.new_doc('Time Log')
        time_log.employee = employee_id
        time_log.project = project_id
        time_log.from_time = timesheet_info.get('start')
        time_log.to_time = timesheet_info.get('end')
        time_log.hours = timesheet_info.get('duration') / 3600 # Assuming duration is in seconds
        time_log.activity_type = "QuickBooks Time Sync" # Or map this from QB
        time_log.insert()
        frappe.db.commit()

        return {"status": "success"}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "QuickBooks Time Webhook Failed")
        return {"status": "error", "message": str(e)}
