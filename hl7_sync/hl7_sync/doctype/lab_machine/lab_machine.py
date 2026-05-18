import frappe
from frappe.model.document import Document


class LabMachine(Document):

    def validate(self):
        self._validate_port()

    def _validate_port(self):
        if not (1 <= int(self.port) <= 65535):
            frappe.throw(f"Port must be between 1 and 65535. Got: {self.port}")

        # Check port uniqueness — no two machines can share a port
        existing = frappe.db.get_value(
            "Lab Machine",
            {"port": self.port, "name": ["!=", self.name]},
            "name"
        )
        if existing:
            frappe.throw(
                f"Port {self.port} is already used by machine '{existing}'. "
                "Each machine must have a unique port."
            )

    def update_status(self, status, message_status=None, increment_count=False):
        """Update runtime status fields after each event."""
        self.db_set("listener_status", status)
        if message_status:
            self.db_set("last_message_at", frappe.utils.now_datetime())
            self.db_set("last_message_status", message_status)
        if increment_count:
            frappe.db.sql(
                "UPDATE `tabLab Machine` SET total_messages_received = COALESCE(total_messages_received, 0) + 1 WHERE name = %s",
                self.name,
            )
        frappe.db.commit()

    @frappe.whitelist()
    def start_listener(self):
        """Start this machine's listener manually."""
        from hl7_sync.utils.listener_manager import start_listener
        result = start_listener(self.name)
        return result

    @frappe.whitelist()
    def stop_listener(self):
        """Stop this machine's listener manually."""
        from hl7_sync.utils.listener_manager import stop_listener
        result = stop_listener(self.name)
        return result
