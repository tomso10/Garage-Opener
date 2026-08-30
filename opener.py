import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from gpiozero import OutputDevice

# Load variables from .env file (GARAGE_API_KEY=...)
load_dotenv()

API_KEY = os.environ.get("GARAGE_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "GARAGE_API_KEY is not set. Add it to your .env file or systemd EnvironmentFile."
    )

RELAY_PIN_1 = 17  # adjust to whichever GPIO pin relay 1 is wired to
RELAY_PIN_2 = 27  # adjust to whichever GPIO pin relay 2 is wired to
PULSE_SECONDS = 0.5  # how long to hold the relay closed

LED_PATH = "/sys/class/leds/led0/brightness"  # onboard ACT LED; set trigger to "none" first (see setup notes)
LED_FLASH_COUNT = 3
LED_ON_SECONDS = 0.15
LED_OFF_SECONDS = 0.15

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "opener.log")          # human-readable log
JSON_LOG_FILE = os.path.join(BASE_DIR, "opener_log.jsonl")  # structured log, one JSON object per line
MAX_LOG_ENTRIES_RETURNED = 200  # cap how many entries the /logs endpoint returns at once

# ---- Logging setup: prints to terminal (and journalctl under systemd) and saves to a file ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # GUI (port 80) is a different origin than this API (port 5000)
relay_1 = OutputDevice(RELAY_PIN_1)
relay_2 = OutputDevice(RELAY_PIN_2)

RELAYS = {
    "1": relay_1,
    "2": relay_2,
}


def flash_led(times=LED_FLASH_COUNT, on_time=LED_ON_SECONDS, off_time=LED_OFF_SECONDS):
    """Blink the Pi's onboard ACT LED to visually confirm a trigger signal
    was received. Fails silently if the LED path isn't writable (e.g. the
    udev rule/trigger mode hasn't been set up yet) so it never blocks the
    actual relay trigger."""
    try:
        for _ in range(times):
            with open(LED_PATH, "w") as f:
                f.write("1")
            time.sleep(on_time)
            with open(LED_PATH, "w") as f:
                f.write("0")
            time.sleep(off_time)
    except (FileNotFoundError, PermissionError, OSError):
        pass


def record_event(action, door, ip, success=True, detail=None):
    """Log an event to the terminal/log file, and append a structured
    record to the JSON log file so it can be queried via /logs."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip": ip,
        "action": action,
        "door": door,
        "success": success,
    }
    if detail:
        entry["detail"] = detail

    logging.info(
        "action=%s door=%s ip=%s success=%s%s",
        action, door, ip, success, f" detail={detail}" if detail else "",
    )

    with open(JSON_LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def check_api_key(action, door):
    """Constant-time comparison to avoid timing attacks. Logs both
    successful and failed auth attempts."""
    supplied = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(supplied, API_KEY):
        record_event(action, door, request.remote_addr, success=False, detail="bad or missing API key")
        abort(401)


@app.route("/trigger/<door>", methods=["POST"])
def trigger(door):
    check_api_key("trigger", door)
    relay = RELAYS.get(door)
    if relay is None:
        record_event("trigger", door, request.remote_addr, success=False, detail="unknown door")
        abort(404, description=f"Unknown door '{door}'. Use '1' or '2'.")

    flash_led()  # visual confirmation that a valid open/close signal was received

    relay.on()
    time.sleep(PULSE_SECONDS)
    relay.off()

    record_event("trigger", door, request.remote_addr, success=True)
    return {"status": "triggered", "door": door}, 200


@app.route("/status/<door>", methods=["GET"])
def status(door):
    check_api_key("status", door)
    relay = RELAYS.get(door)
    if relay is None:
        record_event("status", door, request.remote_addr, success=False, detail="unknown door")
        abort(404, description=f"Unknown door '{door}'. Use '1' or '2'.")

    record_event("status", door, request.remote_addr, success=True)
    return {"door": door, "relay_on": relay.is_active}, 200


@app.route("/logs", methods=["GET"])
def logs():
    """Return recent request history as JSON. Requires the same API key.
    Optional query param: ?limit=N (default/max 200, most recent first)."""
    check_api_key("logs", door=None)

    try:
        limit = min(int(request.args.get("limit", MAX_LOG_ENTRIES_RETURNED)), MAX_LOG_ENTRIES_RETURNED)
    except ValueError:
        limit = MAX_LOG_ENTRIES_RETURNED

    entries = []
    if os.path.exists(JSON_LOG_FILE):
        with open(JSON_LOG_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue  # skip any malformed line rather than failing the whole request

    # Most recent first
    entries.reverse()
    return jsonify(entries[:limit])

# ---- Swagger / OpenAPI docs ----
# Served locally via flask-swagger-ui (bundles its own JS/CSS, no CDN needed on the Pi).
SWAGGER_URL = "/docs"
API_SPEC_URL = "/openapi.json"

OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "info": {
        "title": "Garage Door Opener API",
        "version": "1.0.0",
        "description": "Trigger relays to open/close garage doors, check relay status, and view request logs.",
    },
    "components": {
        "securitySchemes": {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
            }
        }
    },
    "security": [{"ApiKeyAuth": []}],
    "paths": {
        "/trigger/{door}": {
            "post": {
                "summary": "Pulse the relay for the given door",
                "parameters": [
                    {
                        "name": "door",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "enum": ["1", "2"]},
                    }
                ],
                "responses": {
                    "200": {"description": "Triggered successfully"},
                    "401": {"description": "Missing or invalid API key"},
                    "404": {"description": "Unknown door"},
                },
            }
        },
        "/status/{door}": {
            "get": {
                "summary": "Check whether the relay for the given door is currently active",
                "parameters": [
                    {
                        "name": "door",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "enum": ["1", "2"]},
                    }
                ],
                "responses": {
                    "200": {"description": "Current relay state"},
                    "401": {"description": "Missing or invalid API key"},
                    "404": {"description": "Unknown door"},
                },
            }
        },
        "/logs": {
            "get": {
                "summary": "Fetch recent request history",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "default": MAX_LOG_ENTRIES_RETURNED},
                    }
                ],
                "responses": {
                    "200": {"description": "List of recent log entries, most recent first"},
                    "401": {"description": "Missing or invalid API key"},
                },
            }
        },
    },
}


@app.route(API_SPEC_URL)
def openapi_spec():
    return jsonify(OPENAPI_SPEC)


swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_SPEC_URL,
    config={
        "app_name": "Garage Door Opener API",
        "validatorUrl": None,  # disable the external online validator; it can't reach a private LAN address
    },
)
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)


if __name__ == "__main__":
    # Dev only. In production, run via gunicorn instead:
    #   gunicorn --bind 0.0.0.0:5000 --workers 1 opener:app
    app.run(host="0.0.0.0", port=5000)
