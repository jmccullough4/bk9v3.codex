# BlueK9 Client (prototype)

A Flask + Mapbox web UI to prototype the BlueK9 Bluetooth survey client. The UI focuses on situational awareness, target highlighting, alerting, and dockerized deployment.

## Features
- Login with `bluek9/warhammer` (override via env vars).
- Mapbox map with dark/streets/satellite styles, GPS follow toggle, CEP overlay, and emitter markers.
- Simulated Classic/LE detections with survey table, live log, and target highlighting (red rows + alert tone).
- Target deck management, SMS alert hook using `mmcli`, and audio alert when a target appears.
- Clear results button, optional CEP ring, and mission log feed.
- Dockerfile + `docker-compose.yml` for containerized runs.

## Running locally
```bash
./install.sh
source .venv/bin/activate
python app.py
```

Then open http://localhost:5000 and login.

## Docker
```bash
docker compose up --build
```

## Notes
- The detector currently simulates Bluetooth sightings; integrate BlueZ tools in `Detector._run` for real hardware.
- SMS requires a configured `mmcli` modem and US numbers in `PHONE_NUMBERS`.
