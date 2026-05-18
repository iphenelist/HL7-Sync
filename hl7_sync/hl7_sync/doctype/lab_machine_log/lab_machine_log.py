import frappe
from frappe.model.document import Document


class LabMachineLog(Document):
    pass


def create_log(machine_name, machine_make, machine_model,
               status, raw_hl7=None, erpnext_record=None, error_message=None):
    """Helper — create a log entry after each message received."""
    log = frappe.get_doc({
        "doctype": "Lab Machine Log",
        "machine": machine_name,
        "received_at": frappe.utils.now_datetime(),
        "status": status,
        "machine_make": machine_make,
        "machine_model": machine_model,
        "raw_hl7_message": raw_hl7,
        "erpnext_record": erpnext_record,
        "error_message": error_message,
    })
    log.insert(ignore_permissions=True)
    frappe.db.commit()
    return log
