import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

from flask import Flask, jsonify, redirect, render_template, request, session, send_from_directory

APP_SECRET = os.environ.get("BLUEK9_SECRET", "change-me")
USERNAME = os.environ.get("BLUEK9_USERNAME", "bluek9")
PASSWORD = os.environ.get("BLUEK9_PASSWORD", "warhammer")

DEFAULT_TARGETS = [
    {
        "bd_address": "AA:BB:CC:DD:EE:FF",
        "name": "Test Target",
        "manufacturer": "Acme",
    }
]

PHONE_NUMBERS = ["+15551234567"]

app = Flask(__name__, static_folder="static", template_folder="static")
app.secret_key = APP_SECRET


def utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class DeviceSeen:
    def __init__(
        self,
        bd_address: str,
        name: str,
        manufacturer: str,
        rssi: int,
        emitter_location: Optional[Dict[str, float]] = None,
        system_location: Optional[Dict[str, float]] = None,
        device_type: str = "Unknown",
    ):
        self.bd_address = bd_address
        self.name = name
        self.manufacturer = manufacturer
        self.first_seen = utc_now()
        self.last_seen = self.first_seen
        self.rssi = rssi
        self.emitter_location = emitter_location
        self.system_location = system_location
        self.is_target = False
        self.device_type = device_type
        self.alerted = False

    def to_dict(self):
        return {
            "bd_address": self.bd_address,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "rssi": self.rssi,
            "emitter_location": self.emitter_location,
            "system_location": self.system_location,
            "device_type": self.device_type,
            "is_target": self.is_target,
        }


class Detector:
    def __init__(self):
        self.devices: Dict[str, DeviceSeen] = {}
        self.targets: List[Dict[str, str]] = DEFAULT_TARGETS.copy()
        self.logs: List[str] = []
        self.running = True
        self.system_location: Optional[Dict[str, float]] = None
        self.scan_proc: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.thread.start()

    def log(self, message: str):
        line = f"{utc_now()} {message}"
        with self.lock:
            self.logs.append(line)
            if len(self.logs) > 500:
                self.logs = self.logs[-500:]
        print(line)

    def _start_scan_process(self):
        try:
            self.scan_proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if self.scan_proc.stdin:
                self.scan_proc.stdin.write("scan on\n")
                self.scan_proc.stdin.flush()
            self.log("Started bluetoothctl scan")
        except FileNotFoundError:
            self.log("bluetoothctl not found. Install BlueZ to perform live scans.")
            self.running = False
            self.scan_proc = None

    def _parse_scan_line(self, line: str):
        match = re.search(r"Device ([0-9A-F:]{17})\s+(.+)", line)
        if not match:
            return
        bd_address, name = match.groups()
        rssi_match = re.search(r"RSSI: (-?\d+)", line)
        rssi = int(rssi_match.group(1)) if rssi_match else -90
        device_type = "LE" if "[LE]" in line else "Classic/LE"
        with self.lock:
            device = self.devices.get(bd_address)
            if not device:
                device = DeviceSeen(
                    bd_address,
                    name.strip() or "Unknown",
                    "Unknown",
                    rssi,
                    emitter_location=self.system_location,
                    system_location=self.system_location,
                    device_type=device_type,
                )
                self.devices[bd_address] = device
                self.log(f"Device discovered: {bd_address} ({device_type})")
            device.last_seen = utc_now()
            device.name = name.strip() or device.name
            device.rssi = rssi
            device.device_type = device_type
            device.system_location = self.system_location
            if device.emitter_location is None and self.system_location:
                device.emitter_location = self.system_location
            device.is_target = any(t["bd_address"].lower() == bd_address.lower() for t in self.targets)
            if device.is_target and not device.alerted:
                device.alerted = True
                self.log(f"Target detected: {bd_address} at RSSI {rssi}")
                self.send_sms(bd_address, device.system_location or {}, device.first_seen, device.last_seen)

    def _scan_loop(self):
        while True:
            if not self.running:
                time.sleep(1)
                continue
            if not self.scan_proc or self.scan_proc.poll() is not None:
                self._start_scan_process()
                if not self.scan_proc:
                    time.sleep(5)
                    continue
            if not self.scan_proc.stdout:
                time.sleep(1)
                continue
            line = self.scan_proc.stdout.readline()
            if not line:
                time.sleep(0.5)
                continue
            self._parse_scan_line(line.strip())

    def list_devices(self):
        with self.lock:
            return [d.to_dict() for d in self.devices.values()]

    def list_logs(self):
        with self.lock:
            return list(self.logs)

    def clear(self):
        with self.lock:
            self.devices.clear()
            self.logs.append(f"{utc_now()} Cleared detection results")

    def add_target(self, target: Dict[str, str]):
        with self.lock:
            self.targets.append(target)
            self.log(f"Added target {target.get('bd_address')}")

    def update_system_location(self, location: Dict[str, float]):
        with self.lock:
            self.system_location = location
            self.log(
                "System location updated to "
                f"({location.get('lat')}, {location.get('lng')}) ±{location.get('accuracy', '?')}m"
            )

    def send_sms(self, bd_address: str, location: Dict[str, float], first_seen: str, last_seen: str):
        lat = location.get("lat")
        lng = location.get("lng")
        coord_text = f"({lat:.4f},{lng:.4f})" if lat is not None and lng is not None else "(unknown)"
        message = f"BLUEK9 Alert: Target {bd_address} detected. System @{coord_text} First: {first_seen} Last: {last_seen}"
        for number in PHONE_NUMBERS[:10]:
            try:
                os.system(f"mmcli -m 0 --messaging-create-sms=\"text='{message}',number='{number}'\"")
                os.system("mmcli -s 0 --send")
                self.log(f"SMS queued for {number}: {message}")
            except Exception as exc:  # pragma: no cover - hardware dependent
                self.log(f"Failed to send SMS to {number}: {exc}")


detector = Detector()


def login_required(fn):
    def wrapper(*args, **kwargs):
        if session.get("user") != USERNAME:
            return redirect("/login")
        return fn(*args, **kwargs)

    wrapper.__name__ = fn.__name__
    return wrapper


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json() or request.form
        user = data.get("username")
        pw = data.get("password")
        if user == USERNAME and pw == PASSWORD:
            session["user"] = user
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Invalid credentials"}), 401
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/devices")
@login_required
def api_devices():
    return jsonify({"devices": detector.list_devices()})


@app.route("/api/logs")
@login_required
def api_logs():
    return jsonify({"logs": detector.list_logs()})


@app.route("/api/clear", methods=["POST"])
@login_required
def api_clear():
    detector.clear()
    return jsonify({"ok": True})


@app.route("/api/targets", methods=["GET", "POST"])
@login_required
def api_targets():
    if request.method == "POST":
        data = request.get_json() or {}
        detector.add_target(data)
        return jsonify({"ok": True})
    return jsonify({"targets": detector.targets})


@app.route("/api/location", methods=["POST"])
@login_required
def api_location():
    data = request.get_json() or {}
    detector.update_system_location(data)
    return jsonify({"ok": True})


@app.route("/assets/<path:path>")
def send_assets(path):
    return send_from_directory("static/assets", path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
