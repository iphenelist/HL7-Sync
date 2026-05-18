import frappe
from frappe.model.document import Document


class HL7Settings(Document):

    def validate(self):
        if self.erpnext_url:
            self.erpnext_url = self.erpnext_url.rstrip("/")

    def get_connection_params(self):
        return {
            "erpnext_url": self.erpnext_url,
            "api_key": self.api_key,
            "api_secret": self.get_password("api_secret"),
            "logs_directory": self.logs_directory or "logs",
            "log_raw_hl7": self.log_raw_hl7,
        }
