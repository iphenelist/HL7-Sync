frappe.ui.form.on("Lab Machine", {
    refresh(frm) {
        if (frm.is_new()) return;

        const status = frm.doc.listener_status;

        // Start button
        if (status !== "Running") {
            frm.add_custom_button(__("Start Listener"), function () {
                frappe.show_alert({ message: __("Starting listener..."), indicator: "blue" });
                frm.call("start_listener").then(r => {
                    if (r.message && r.message.success) {
                        frappe.show_alert({ message: __("Listener started on port {0}", [frm.doc.port]), indicator: "green" });
                    } else {
                        frappe.show_alert({ message: __("Failed: ") + (r.message && r.message.error || "Unknown error"), indicator: "red" });
                    }
                    frm.reload_doc();
                });
            }, __("Actions"));
        }

        // Stop button
        if (status === "Running") {
            frm.add_custom_button(__("Stop Listener"), function () {
                frappe.confirm(
                    __("Stop listener for {0}?", [frm.doc.machine_name]),
                    () => {
                        frm.call("stop_listener").then(r => {
                            frappe.show_alert({
                                message: r.message && r.message.success ? __("Listener stopped.") : __("Could not stop listener."),
                                indicator: r.message && r.message.success ? "orange" : "red"
                            });
                            frm.reload_doc();
                        });
                    }
                );
            }, __("Actions"));
        }

        // View logs button
        frm.add_custom_button(__("View Logs"), function () {
            frappe.set_route("List", "Lab Machine Log", { machine: frm.doc.name });
        }, __("Actions"));

        // Color the status indicator
        const indicator = frm.get_field("listener_status");
        if (indicator && indicator.$wrapper) {
            const colors = { "Running": "green", "Stopped": "orange", "Error": "red" };
            const color = colors[frm.doc.listener_status] || "gray";
            indicator.$wrapper.find(".control-value").css("color", color);
        }
    }
});
