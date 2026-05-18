import frappe


@frappe.whitelist()
def get_dashboard_data():
    """Return all data needed to render the HL7 dashboard."""
    from hl7_sync.utils.listener_manager import get_all_statuses

    machines = get_all_statuses()

    recent_logs = frappe.get_all(
        "Lab Machine Log",
        fields=["name", "machine", "received_at", "status",
                "machine_make", "machine_model", "erpnext_record"],
        order_by="received_at desc",
        limit=50
    )

    total_today = frappe.db.count(
        "Lab Machine Log",
        {"received_at": [">=", frappe.utils.today()]}
    )
    failed_today = frappe.db.count(
        "Lab Machine Log",
        {"received_at": [">=", frappe.utils.today()], "status": "Failed"}
    )
    running_count = sum(1 for m in machines if m.get("listener_status") == "Running")

    stats = {
        "total_machines": len(machines),
        "running": running_count,
        "total_today": total_today,
        "failed_today": failed_today,
    }

    return {"machines": machines, "recent_logs": recent_logs, "stats": stats}


@frappe.whitelist()
def start_all():
    """Start all active machine listeners."""
    from hl7_sync.utils.listener_manager import start_all_listeners
    return start_all_listeners()


@frappe.whitelist()
def stop_all():
    """Stop all running listeners."""
    from hl7_sync.utils.listener_manager import stop_all_listeners
    stop_all_listeners()
    return {"success": True}


@frappe.whitelist()
def start_machine(machine_name):
    from hl7_sync.utils.listener_manager import start_listener
    return start_listener(machine_name)


@frappe.whitelist()
def stop_machine(machine_name):
    from hl7_sync.utils.listener_manager import stop_listener
    return stop_listener(machine_name)
