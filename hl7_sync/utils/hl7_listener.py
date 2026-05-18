"""
hl7_sync.utils.hl7_listener
-----------------------------
Async HL7/MLLP listener — one instance per Lab Machine.

Mirrors the original hl7_listener.py logic but:
 - reads config from Frappe DocTypes (not local_config.py)
 - logs to Lab Machine Log DocType
 - updates Lab Machine status fields
 - runs as a subprocess so it doesn't block Frappe's event loop
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

import frappe
import requests

# ── these are only available if hl7 is installed ─────────────────────────────
try:
    import aiorun
    import hl7
    from hl7.mllp import start_hl7_server
    HL7_AVAILABLE = True
except ImportError:
    HL7_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Listener class
# ─────────────────────────────────────────────────────────────────────────────

class HL7Listener:
    """
    Async HL7/MLLP listener for a single Lab Machine.
    Instantiate one per machine, then call run().
    """

    def __init__(self, machine_name, machine_make, machine_model,
                 port, encoding,
                 erpnext_url, api_key, api_secret,
                 logs_directory, log_raw_hl7=True):
        self.machine_name = machine_name
        self.machine_make = machine_make
        self.machine_model = machine_model
        self.port = port
        self.encoding = encoding
        self.erpnext_url = erpnext_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.logs_directory = logs_directory
        self.log_raw_hl7 = log_raw_hl7

        os.makedirs(logs_directory, exist_ok=True)
        self.error_logger = self._setup_logger(
            f"hl7_{machine_name}",
            os.path.join(logs_directory, f"{machine_name}_error.log")
        )

    # ── Async server ──────────────────────────────────────────────────────────

    async def _handle_connection(self, hl7_reader, hl7_writer):
        """Called for every incoming TCP connection from a lab machine."""
        peername = hl7_writer.get_extra_info("peername")
        self.error_logger.info(f"Connection established: {peername}")

        try:
            while not hl7_writer.is_closing():
                hl7_message = await hl7_reader.readmessage()
                str_hl7 = str(hl7_message).replace("\r", "\n")

                self._process_message(str_hl7)

                # Always send ACK back — required by MLLP spec
                hl7_writer.writemessage(hl7_message.create_ack())
                await hl7_writer.drain()

        except asyncio.IncompleteReadError:
            if not hl7_writer.is_closing():
                hl7_writer.close()
                await hl7_writer.wait_closed()

        self.error_logger.info(f"Connection closed: {peername}")

    async def _main(self):
        try:
            async with await start_hl7_server(
                self._handle_connection,
                port=self.port,
                encoding=self.encoding
            ) as hl7_server:
                self.error_logger.info(
                    f"HL7 listener started on port {self.port} "
                    f"for {self.machine_name}"
                )
                await hl7_server.serve_forever()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.error_logger.error(f"Listener error: {e}", exc_info=True)
            raise

    def run(self):
        """Block and run the listener forever (call from subprocess)."""
        if not HL7_AVAILABLE:
            print("ERROR: hl7 library not installed. Run: bench pip install hl7 aiorun")
            sys.exit(1)
        aiorun.run(self._main(), stop_on_unhandled_errors=True)

    # ── Message processing ────────────────────────────────────────────────────

    def _process_message(self, str_hl7):
        """Send the received HL7 message to ERPNext and log the result."""
        timestamp = str(datetime.now())
        status_code, result = self._send_to_erpnext(str_hl7, timestamp)

        success = status_code == 200
        self._write_frappe_log(
            status="Success" if success else "Failed",
            raw_hl7=str_hl7 if self.log_raw_hl7 else None,
            erpnext_record=result if success else None,
            error_message=None if success else result,
        )
        self._update_machine_status(
            message_status="Success" if success else "Failed"
        )

    def _send_to_erpnext(self, str_hl7, timestamp):
        """
        POST HL7 message to ERPNext Lab Machine Message DocType.
        Returns (status_code, record_name_or_error_str).
        """
        url = f"{self.erpnext_url}/api/resource/Lab Machine Message"
        headers = {
            "Authorization": f"token {self.api_key}:{self.api_secret}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        data = {
            "date_and_time": timestamp,
            "machine_make": self.machine_make,
            "machine_model": self.machine_model,
            "message": str_hl7,
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=15)
            if response.status_code == 200:
                record_name = response.json()["data"]["name"]
                self.error_logger.info(f"Posted to ERPNext: {record_name}")
                return 200, record_name
            else:
                error_str = self._parse_error(response)
                self.error_logger.error(
                    f"ERPNext API error {response.status_code}: {error_str}"
                )
                return response.status_code, error_str
        except requests.RequestException as e:
            self.error_logger.error(f"HTTP request failed: {e}")
            return 500, str(e)

    # ── Frappe integration (called from subprocess via frappe.init) ───────────

    def _write_frappe_log(self, status, raw_hl7=None,
                          erpnext_record=None, error_message=None):
        """Write a Lab Machine Log record via Frappe ORM."""
        try:
            from hl7_sync.hl7_sync.doctype.lab_machine_log.lab_machine_log import create_log
            create_log(
                machine_name=self.machine_name,
                machine_make=self.machine_make,
                machine_model=self.machine_model,
                status=status,
                raw_hl7=raw_hl7,
                erpnext_record=erpnext_record,
                error_message=error_message,
            )
        except Exception as e:
            self.error_logger.error(f"Could not write Frappe log: {e}")

    def _update_machine_status(self, message_status):
        """Update Lab Machine runtime status fields."""
        try:
            machine = frappe.get_doc("Lab Machine", self.machine_name)
            machine.update_status(
                status="Running",
                message_status=message_status,
                increment_count=True
            )
        except Exception as e:
            self.error_logger.error(f"Could not update machine status: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_error(response):
        try:
            error_json = response.json()
            if "exc" in error_json:
                return json.loads(error_json["exc"])[0]
            return json.dumps(error_json)
        except Exception:
            return str(response.__dict__)

    @staticmethod
    def _setup_logger(name, log_file):
        formatter = logging.Formatter("%(asctime)s\t%(levelname)s\t%(message)s")
        handler = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=50)
        handler.setFormatter(formatter)
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        if not logger.hasHandlers():
            logger.addHandler(handler)
        return logger


# ─────────────────────────────────────────────────────────────────────────────
# Entry point for subprocess
# ─────────────────────────────────────────────────────────────────────────────

def run_listener_subprocess(machine_name, site_name):
    """
    Entry point called when this module is run as a subprocess:
        python -m hl7_sync.utils.hl7_listener <machine_name> <site_name>

    Initialises Frappe, loads config, starts the listener.
    """
    frappe.init(site=site_name)
    frappe.connect()

    try:
        machine = frappe.get_doc("Lab Machine", machine_name)
        settings = frappe.get_single("HL7 Settings")
        params = settings.get_connection_params()

        listener = HL7Listener(
            machine_name=machine.name,
            machine_make=machine.machine_make,
            machine_model=machine.machine_model,
            port=machine.port,
            encoding=machine.encoding or "latin-1",
            erpnext_url=params["erpnext_url"],
            api_key=params["api_key"],
            api_secret=params["api_secret"],
            logs_directory=params["logs_directory"],
            log_raw_hl7=params["log_raw_hl7"],
        )

        machine.update_status("Running")
        listener.run()

    except Exception as e:
        frappe.log_error(title=f"HL7 Listener Failed: {machine_name}", message=str(e))
        try:
            frappe.db.set_value("Lab Machine", machine_name, "listener_status", "Error")
            frappe.db.commit()
        except Exception:
            pass
    finally:
        frappe.destroy()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m hl7_sync.utils.hl7_listener <machine_name> <site_name>")
        sys.exit(1)
    run_listener_subprocess(sys.argv[1], sys.argv[2])
