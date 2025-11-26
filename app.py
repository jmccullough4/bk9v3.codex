import json
import os
import random
import threading
import time
from datetime import datetime
from typing import Dict, List

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
    def __init__(self, bd_address: str, name: str, manufacturer: str, rssi: int, emitter_location: Dict[str, float]):
        self.bd_address = bd_address
        self.name = name
        self.manufacturer = manufacturer
        self.first_seen = utc_now()
        self.last_seen = self.first_seen
        self.rssi = rssi
        self.emitter_location = emitter_location
        self.system_location = emitter_location.copy()
        self.is_target = False
        self.device_type = random.choice(["LE", "Classic"])

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
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def log(self, message: str):
        line = f"{utc_now()} {message}"
        with self.lock:
            self.logs.append(line)
            if len(self.logs) > 500:
                self.logs = self.logs[-500:]
        print(line)

    def _random_location(self):
        base_lat, base_lng = 37.7749, -122.4194
        return {
            "lat": base_lat + random.uniform(-0.01, 0.01),
            "lng": base_lng + random.uniform(-0.01, 0.01),
            "accuracy": random.randint(20, 120),
        }

    def _run(self):
        while True:
            if self.running:
                loc = self._random_location()
                bd = "{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}".format(
                    *[random.randint(0, 255) for _ in range(6)]
                )
                name = random.choice(["Sensor", "Beacon", "Headset", "Tracker"])
                manufacturer = random.choice(["Apple", "Samsung", "Sony", "Garmin", "Unknown"])
                rssi = random.randint(-90, -20)
                device = self.devices.get(bd) or DeviceSeen(bd, name, manufacturer, rssi, loc)
                device.last_seen = utc_now()
                device.rssi = rssi
                device.emitter_location = loc
                device.system_location = self._random_location()
                device.is_target = any(t["bd_address"].lower() == bd.lower() for t in self.targets)
                self.devices[bd] = device
                if device.is_target:
                    self.log(f"Target detected: {bd} at RSSI {rssi}")
            time.sleep(3)

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

    def send_sms(self, bd_address: str, location: Dict[str, float], first_seen: str, last_seen: str):
        message = f"BLUEK9 Alert: Target {bd_address} detected. System @({location.get('lat'):.4f},{location.get('lng'):.4f}) First: {first_seen} Last: {last_seen}"
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


@app.route("/api/simulate_alert", methods=["POST"])
@login_required
def api_simulate_alert():
    data = request.get_json() or {}
    bd = data.get("bd_address", "")
    loc = data.get("location") or detector._random_location()
    detector.send_sms(bd, loc, utc_now(), utc_now())
    return jsonify({"ok": True})


@app.route("/assets/<path:path>")
def send_assets(path):
    return send_from_directory("static/assets", path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
