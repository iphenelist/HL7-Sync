"""
hl7_sync.scheduled_tasks.watchdog
-----------------------------------
Called every minute by Frappe scheduler.
Checks if all active machine listeners are running;
restarts any that have crashed.
"""

import frappe


def check_listeners():
    """
    Scheduler entry point — runs every minute.
    Restarts any active listener that has stopped unexpectedly.
    """
    try:
        settings = frappe.get_single("HL7 Settings")
    except Exception:
        return   # app not configured yet

    if not settings.is_enabled:
        return

    from hl7_sync.utils.listener_manager import (
        _get_pid, _is_running, start_listener
    )

    machines = frappe.get_all(
        "Lab Machine",
        filters={"is_active": 1},
        fields=["name", "listener_status"]
    )

    for m in machines:
        pid = _get_pid(m.name)
        if not _is_running(pid):
            frappe.logger("hl7_sync").warning(
                f"HL7 Watchdog: listener for {m.name} not running — restarting."
            )
            start_listener(m.name)


def start_all_listeners():
    """
    Called once on app init (hooks.py on_app_init).
    Starts all active listeners fresh.
    """
    try:
        from hl7_sync.utils.listener_manager import start_all_listeners as _start_all
        _start_all()
    except Exception as e:
        frappe.log_error(
            title="HL7 Sync: failed to start listeners on boot",
            message=str(e)
        )
