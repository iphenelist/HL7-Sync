frappe.pages["hl7-dashboard"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "HL7 Lab Machine Dashboard",
        single_column: true,
    });

    // ── Toolbar buttons ───────────────────────────────────────────────────
    page.add_menu_item(__("HL7 Settings"), () => frappe.set_route("Form", "HL7 Settings"));
    page.add_menu_item(__("Add Machine"), () => frappe.set_route("Form", "Lab Machine", "new-lab-machine"));

    page.add_inner_button(__("Start All"), () => {
        frappe.confirm(__("Start listeners for all active machines?"), () => {
            frappe.show_alert({ message: __("Starting all listeners..."), indicator: "blue" });
            frappe.call({
                method: "hl7_sync.page.hl7_dashboard.hl7_dashboard.start_all",
                callback(r) {
                    frappe.show_alert({ message: __("All listeners started."), indicator: "green" });
                    load();
                }
            });
        });
    }, __("Actions"));

    page.add_inner_button(__("Stop All"), () => {
        frappe.confirm(__("Stop all running listeners?"), () => {
            frappe.call({
                method: "hl7_sync.page.hl7_dashboard.hl7_dashboard.stop_all",
                callback() {
                    frappe.show_alert({ message: __("All listeners stopped."), indicator: "orange" });
                    load();
                }
            });
        });
    }, __("Actions"));

    // ── Canvas ────────────────────────────────────────────────────────────
    $(wrapper).find(".layout-main-section").html(`
        <div id="hl7-dashboard" style="padding:20px">
            <div id="hl7-stats" class="row" style="margin-bottom:24px"></div>
            <div id="hl7-machines" style="margin-bottom:32px"></div>
            <div id="hl7-logs"></div>
        </div>
    `);

    // ── Load ──────────────────────────────────────────────────────────────
    function load() {
        frappe.call({
            method: "hl7_sync.page.hl7_dashboard.hl7_dashboard.get_dashboard_data",
            callback(r) {
                if (!r.message) return;
                const { machines, recent_logs, stats } = r.message;
                render_stats(stats);
                render_machines(machines);
                render_logs(recent_logs);
            }
        });
    }

    // ── Stats ─────────────────────────────────────────────────────────────
    function render_stats(s) {
        const cards = [
            { label: "Total Machines", value: s.total_machines, color: "blue" },
            { label: "Listeners Running", value: s.running, color: "green" },
            { label: "Messages Today", value: s.total_today, color: "orange" },
            { label: "Failed Today", value: s.failed_today, color: "red" },
        ];
        $("#hl7-stats").html(cards.map(c => `
            <div class="col-sm-3">
                <div class="card" style="padding:16px;border-left:4px solid var(--${c.color}-500,#888);margin-bottom:12px">
                    <div style="font-size:28px;font-weight:600">${c.value}</div>
                    <div style="color:var(--text-muted);font-size:13px">${c.label}</div>
                </div>
            </div>
        `).join(""));
    }

    // ── Machines ──────────────────────────────────────────────────────────
    function render_machines(machines) {
        if (!machines.length) {
            $("#hl7-machines").html(`<p class="text-muted">${__("No machines configured. Add one to get started.")}</p>`);
            return;
        }

        const e = frappe.utils.escape_html;
        const rows = machines.map(m => {
            const running = m.listener_status === "Running";
            const status_badge = `<span class="indicator-pill ${running ? "green" : m.listener_status === "Error" ? "red" : "gray"}">${e(m.listener_status || "Stopped")}</span>`;
            const active_badge = m.is_active
                ? `<span class="indicator-pill green">${__("Active")}</span>`
                : `<span class="indicator-pill gray">${__("Disabled")}</span>`;

            const action_btn = running
                ? `<button class="btn btn-xs btn-danger" onclick="stop_machine(${JSON.stringify(m.name)})">Stop</button>`
                : `<button class="btn btn-xs btn-success" onclick="start_machine(${JSON.stringify(m.name)})">Start</button>`;

            return `<tr>
                <td><a href="/app/lab-machine/${e(m.name)}">${e(m.machine_name || m.name)}</a></td>
                <td>${e(m.machine_make || "")}</td>
                <td>${e(m.machine_model || "")}</td>
                <td>${e(String(m.port || ""))}</td>
                <td>${active_badge}</td>
                <td>${status_badge}</td>
                <td>${m.last_message_at ? frappe.datetime.str_to_user(m.last_message_at) : "—"}</td>
                <td>${m.total_messages_received || 0}</td>
                <td>${action_btn}</td>
            </tr>`;
        }).join("");

        $("#hl7-machines").html(`
            <h6 style="margin-bottom:12px">${__("Machines")}</h6>
            <table class="table table-bordered table-hover">
                <thead><tr>
                    <th>${__("Machine")}</th>
                    <th>${__("Make")}</th>
                    <th>${__("Model")}</th>
                    <th>${__("Port")}</th>
                    <th>${__("Active")}</th>
                    <th>${__("Listener")}</th>
                    <th>${__("Last Message")}</th>
                    <th>${__("Total Msgs")}</th>
                    <th>${__("Action")}</th>
                </tr></thead>
                <tbody>${rows}</tbody>
            </table>
        `);
    }

    // ── Logs ──────────────────────────────────────────────────────────────
    function render_logs(logs) {
        if (!logs.length) {
            $("#hl7-logs").html(`<p class="text-muted">${__("No messages received yet.")}</p>`);
            return;
        }

        const e = frappe.utils.escape_html;
        const rows = logs.map(l => {
            const badge = `<span class="indicator-pill ${l.status === "Success" ? "green" : "red"}">${e(l.status)}</span>`;
            return `<tr>
                <td><a href="/app/lab-machine-log/${e(l.name)}">${e(l.name)}</a></td>
                <td>${e(l.machine || "—")}</td>
                <td>${frappe.datetime.str_to_user(l.received_at)}</td>
                <td>${badge}</td>
                <td>${e(l.machine_make || "")}</td>
                <td>${e(l.machine_model || "")}</td>
                <td>${e(l.erpnext_record || "—")}</td>
            </tr>`;
        }).join("");

        $("#hl7-logs").html(`
            <h6 style="margin-bottom:12px">${__("Recent Messages")}</h6>
            <table class="table table-bordered table-hover">
                <thead><tr>
                    <th>${__("Log ID")}</th>
                    <th>${__("Machine")}</th>
                    <th>${__("Received At")}</th>
                    <th>${__("Status")}</th>
                    <th>${__("Make")}</th>
                    <th>${__("Model")}</th>
                    <th>${__("ERPNext Record")}</th>
                </tr></thead>
                <tbody>${rows}</tbody>
            </table>
        `);
    }

    // ── Per-machine controls (called from table buttons) ──────────────────
    window.start_machine = function (name) {
        frappe.show_alert({ message: __("Starting {0}...", [name]), indicator: "blue" });
        frappe.call({
            method: "hl7_sync.page.hl7_dashboard.hl7_dashboard.start_machine",
            args: { machine_name: name },
            callback(r) {
                const ok = r.message && r.message.success;
                frappe.show_alert({
                    message: ok ? __("{0} started.", [name]) : __("Failed to start {0}.", [name]),
                    indicator: ok ? "green" : "red"
                });
                load();
            }
        });
    };

    window.stop_machine = function (name) {
        frappe.call({
            method: "hl7_sync.page.hl7_dashboard.hl7_dashboard.stop_machine",
            args: { machine_name: name },
            callback() { frappe.show_alert({ message: __("{0} stopped.", [name]), indicator: "orange" }); load(); }
        });
    };

    // ── Initial load + auto-refresh every 30 seconds ─────────────────────
    load();
    setInterval(load, 30000);
};
