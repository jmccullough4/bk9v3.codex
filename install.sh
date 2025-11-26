#!/usr/bin/env bash
set -euo pipefail

command -v python3 >/dev/null || { echo "python3 required"; exit 1; }
command -v pip >/dev/null || { echo "pip required"; exit 1; }

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

AUDIO_PATH="static/assets/alert.wav"
if [ ! -f "$AUDIO_PATH" ]; then
  echo "Downloading alert tone..."
  curl -L -o "$AUDIO_PATH" https://github.com/kevinstadler/notification-sounds/raw/master/assets/beep_short.wav || {
    echo "Download failed, generating fallback tone";
    python - <<'PY'
import math, wave, struct
framerate=44100; freq=880; length=0.4; volume=0.5
samples=int(framerate*length)
with wave.open('static/assets/alert.wav','w') as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(framerate)
    for i in range(samples):
        val=int(volume*32767*math.sin(2*math.pi*freq*(i/framerate)))
        wf.writeframes(struct.pack('<h', val))
PY
  }
fi

cat <<'EOF'
Installation complete.
Activate with: source .venv/bin/activate
Run locally:   python app.py
Docker build:  docker compose up --build
EOF
