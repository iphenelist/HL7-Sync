"""
hl7_sync.utils.listener_manager
---------------------------------
Manages one subprocess per active Lab Machine.
Each subprocess runs hl7_listener.py forever.

PIDs are tracked in both frappe.cache() (fast path) and the Lab Machine DB
field `listener_pid` (fallback after a Redis restart).
"""

import os
import signal
import subprocess
import sys
import time

import frappe


# ── Cache key helpers ─────────────────────────────────────────────────────────

def _pid_key(machine_name):
    return f"hl7_listener_pid::{machine_name}"


def _get_pid(machine_name):
    pid = frappe.cache().get_value(_pid_key(machine_name))
    if pid is None:
        # Fallback: DB survives Redis restarts
        pid = frappe.db.get_value("Lab Machine", machine_name, "listener_pid")
    return pid


def _set_pid(machine_name, pid):
    frappe.cache().set_value(_pid_key(machine_name), pid)
    frappe.db.set_value("Lab Machine", machine_name, "listener_pid", pid, update_modified=False)


def _clear_pid(machine_name):
    frappe.cache().delete_value(_pid_key(machine_name))
    frappe.db.set_value("Lab Machine", machine_name, "listener_pid", None, update_modified=False)


# ── Process health check ──────────────────────────────────────────────────────

def _is_running(pid):
    """Return True if a process with this PID exists."""
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)   # signal 0 = existence check, no actual signal
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ── Start / stop ──────────────────────────────────────────────────────────────

def start_listener(machine_name):
    """
    Start the HL7 listener for one machine as a background subprocess.
    Returns { success: bool, pid: int|None, error: str|None }
    """
    pid = _get_pid(machine_name)
    if _is_running(pid):
        return {"success": True, "pid": pid, "message": "Already running"}

    site = frappe.local.site
    python = sys.executable   # same Python that runs Frappe

    # Run: python -m hl7_sync.utils.hl7_listener <machine_name> <site>
    cmd = [python, "-m", "hl7_sync.utils.hl7_listener", machine_name, site]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,   # detach from Frappe's process group
        )
        _set_pid(machine_name, proc.pid)
        frappe.db.set_value("Lab Machine", machine_name, "listener_status", "Running")
        frappe.db.commit()
        return {"success": True, "pid": proc.pid}

    except Exception as e:
        frappe.db.set_value("Lab Machine", machine_name, "listener_status", "Error")
        frappe.db.commit()
        return {"success": False, "error": str(e)}


def stop_listener(machine_name):
    """
    Stop the HL7 listener subprocess for one machine.
    Returns { success: bool }
    """
    pid = _get_pid(machine_name)
    if not _is_running(pid):
        _clear_pid(machine_name)
        frappe.db.set_value("Lab Machine", machine_name, "listener_status", "Stopped")
        frappe.db.commit()
        return {"success": True, "message": "Was not running"}

    try:
        os.kill(int(pid), signal.SIGTERM)
        # Wait up to 5 s for the process to release the port before returning
        for _ in range(10):
            if not _is_running(pid):
                break
            time.sleep(0.5)
        _clear_pid(machine_name)
        frappe.db.set_value("Lab Machine", machine_name, "listener_status", "Stopped")
        frappe.db.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Bulk operations ───────────────────────────────────────────────────────────

def start_all_listeners():
    """Start listeners for all active Lab Machines."""
    settings = frappe.get_single("HL7 Settings")
    if not settings.is_enabled:
        return

    machines = frappe.get_all(
        "Lab Machine",
        filters={"is_active": 1},
        fields=["name"]
    )
    results = []
    for m in machines:
        result = start_listener(m.name)
        results.append({"machine": m.name, **result})
    return results


def stop_all_listeners():
    """Stop all running listeners."""
    machines = frappe.get_all("Lab Machine", fields=["name"])
    for m in machines:
        stop_listener(m.name)


def get_all_statuses():
    """
    Return current status for every machine,
    reconciling DB state with actual process state.
    """
    machines = frappe.get_all(
        "Lab Machine",
        fields=["name", "machine_name", "machine_make", "machine_model",
                "port", "listener_status", "last_message_at",
                "last_message_status", "total_messages_received", "is_active"]
    )
    statuses = []
    for m in machines:
        pid = _get_pid(m.name)
        actually_running = _is_running(pid)

        # Reconcile: if DB says Running but process is gone, fix it
        if m.listener_status == "Running" and not actually_running:
            frappe.db.set_value("Lab Machine", m.name, "listener_status", "Stopped")
            frappe.db.commit()
            m.listener_status = "Stopped"

        statuses.append({
            **m,
            "pid": pid if actually_running else None,
        })
    return statuses
