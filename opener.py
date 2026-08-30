import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template_string, request
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
relay_1 = OutputDevice(RELAY_PIN_1)
relay_2 = OutputDevice(RELAY_PIN_2)

RELAYS = {
    "1": relay_1,
    "2": relay_2,
}


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


# ---- Web GUI ----
# Shared page shell: top bar with a "View Logs" link and a settings (API key) button.
# The API key is entered once in the browser and saved to localStorage, then sent
# as the X-API-Key header on every fetch() call from either page.

BASE_STYLE = """
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #111418;
            color: #f2f2f2;
            min-height: 100vh;
        }
        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px;
            background: #1a1e24;
            border-bottom: 1px solid #2a2f37;
        }
        header h1 {
            font-size: 18px;
            margin: 0;
            font-weight: 600;
        }
        header nav a, header nav button {
            color: #cfd3d8;
            text-decoration: none;
            background: none;
            border: 1px solid #3a4048;
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 14px;
            cursor: pointer;
            margin-left: 8px;
        }
        header nav a:hover, header nav button:hover { background: #232830; }
        main { padding: 24px 16px 40px; max-width: 900px; margin: 0 auto; }
        #toast {
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%);
            padding: 12px 20px;
            border-radius: 10px;
            font-size: 14px;
            display: none;
            z-index: 50;
            max-width: 90%;
            text-align: center;
        }
        #toast.show { display: block; }
        #toast.success { background: #1f4d2c; color: #bdf5c8; border: 1px solid #2f7a44; }
        #toast.error { background: #4d1f1f; color: #f5bdbd; border: 1px solid #7a2f2f; }

        .modal-backdrop {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.6);
            align-items: center;
            justify-content: center;
            z-index: 100;
        }
        .modal-backdrop.show { display: flex; }
        .modal {
            background: #1a1e24;
            border: 1px solid #2a2f37;
            border-radius: 14px;
            padding: 24px;
            width: 90%;
            max-width: 380px;
        }
        .modal h2 { margin-top: 0; font-size: 16px; }
        .modal input {
            width: 100%;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid #3a4048;
            background: #111418;
            color: #f2f2f2;
            font-size: 15px;
            margin: 10px 0 16px;
        }
        .modal .row { display: flex; gap: 10px; justify-content: flex-end; }
        .modal button {
            padding: 10px 16px;
            border-radius: 8px;
            border: none;
            font-size: 14px;
            cursor: pointer;
        }
        .modal .save { background: #3d7bfd; color: white; }
        .modal .cancel { background: #2a2f37; color: #cfd3d8; }
    </style>
"""

TOAST_SCRIPT = """
    <script>
        function getApiKey() { return localStorage.getItem('garageApiKey') || ''; }
        function setApiKey(key) { localStorage.setItem('garageApiKey', key); }

        function showToast(message, isError) {
            const el = document.getElementById('toast');
            el.textContent = message;
            el.className = 'show ' + (isError ? 'error' : 'success');
            clearTimeout(window._toastTimer);
            window._toastTimer = setTimeout(() => { el.className = ''; }, 3000);
        }

        function openKeyModal() {
            document.getElementById('apiKeyInput').value = getApiKey();
            document.getElementById('keyModal').classList.add('show');
        }
        function closeKeyModal() {
            document.getElementById('keyModal').classList.remove('show');
        }
        function saveKeyModal() {
            const val = document.getElementById('apiKeyInput').value.trim();
            setApiKey(val);
            closeKeyModal();
            showToast('API key saved', false);
        }

        // Prompt for a key on first visit if none is saved yet.
        window.addEventListener('DOMContentLoaded', () => {
            if (!getApiKey()) openKeyModal();
        });
    </script>
"""

KEY_MODAL_HTML = """
    <div class="modal-backdrop" id="keyModal">
        <div class="modal">
            <h2>API Key</h2>
            <input type="password" id="apiKeyInput" placeholder="Paste your API key" autocomplete="off">
            <div class="row">
                <button class="cancel" onclick="closeKeyModal()">Cancel</button>
                <button class="save" onclick="saveKeyModal()">Save</button>
            </div>
        </div>
    </div>
"""

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <title>Garage Doors</title>
    {{ base_style|safe }}
    <style>
        .buttons {
            display: flex;
            flex-direction: column;
            gap: 20px;
            margin-top: 12px;
        }
        .door-btn {
            width: 100%;
            padding: 48px 20px;
            font-size: 24px;
            font-weight: 700;
            color: white;
            border: none;
            border-radius: 20px;
            cursor: pointer;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 12px;
            transition: transform 0.08s ease, opacity 0.2s ease;
            -webkit-tap-highlight-color: transparent;
        }
        .door-btn:active { transform: scale(0.97); }
        .door-btn:disabled { opacity: 0.6; cursor: default; }
        .door-btn.one { background: linear-gradient(135deg, #3d7bfd, #2a5fd0); }
        .door-btn.two { background: linear-gradient(135deg, #ff8a3d, #d96a1f); }
        .door-btn svg { width: 56px; height: 56px; }
        @media (min-width: 640px) {
            .buttons { flex-direction: row; }
        }
    </style>
</head>
<body>
    <header>
        <h1>🚪 Garage Doors</h1>
        <nav>
            <a href="/logs-view">View Logs</a>
            <button onclick="openKeyModal()">Key</button>
        </nav>
    </header>
    <main>
        <div class="buttons">
            <button class="door-btn one" id="btn1" onclick="triggerDoor('1', this)">
                <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6"/></svg>
                Garage 1
            </button>
            <button class="door-btn two" id="btn2" onclick="triggerDoor('2', this)">
                <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6"/></svg>
                Garage 2
            </button>
        </div>
    </main>
    <div id="toast"></div>
    {{ key_modal|safe }}
    {{ toast_script|safe }}
    <script>
        async function triggerDoor(door, btn) {
            const key = getApiKey();
            if (!key) { openKeyModal(); return; }
            btn.disabled = true;
            const original = btn.innerHTML;
            btn.innerHTML = 'Triggering...';
            try {
                const res = await fetch('/trigger/' + door, {
                    method: 'POST',
                    headers: { 'X-API-Key': key }
                });
                if (res.status === 401) {
                    showToast('Invalid API key', true);
                    openKeyModal();
                } else if (!res.ok) {
                    showToast('Error: ' + res.status, true);
                } else {
                    showToast('Garage ' + door + ' triggered', false);
                }
            } catch (err) {
                showToast('Network error: ' + err.message, true);
            } finally {
                btn.disabled = false;
                btn.innerHTML = original;
            }
        }
    </script>
</body>
</html>
"""

LOGS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Garage Logs</title>
    {{ base_style|safe }}
    <style>
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #2a2f37; }
        th { color: #9aa1ab; font-weight: 600; }
        .ok { color: #8fe0a3; }
        .fail { color: #f28b8b; }
        .controls { display: flex; gap: 10px; margin-bottom: 16px; align-items: center; }
        .controls button {
            background: #3d7bfd; color: white; border: none;
            padding: 8px 14px; border-radius: 8px; cursor: pointer; font-size: 14px;
        }
        .controls input {
            width: 80px; padding: 8px; border-radius: 8px; border: 1px solid #3a4048;
            background: #111418; color: #f2f2f2;
        }
        .empty { color: #9aa1ab; padding: 20px 0; }
    </style>
</head>
<body>
    <header>
        <h1>📋 Request Logs</h1>
        <nav>
            <a href="/">Doors</a>
            <button onclick="openKeyModal()">Key</button>
        </nav>
    </header>
    <main>
        <div class="controls">
            <label for="limit">Limit</label>
            <input type="number" id="limit" value="50" min="1" max="200">
            <button onclick="loadLogs()">Refresh</button>
        </div>
        <div id="logsWrap"><p class="empty">Loading...</p></div>
    </main>
    <div id="toast"></div>
    {{ key_modal|safe }}
    {{ toast_script|safe }}
    <script>
        async function loadLogs() {
            const key = getApiKey();
            if (!key) { openKeyModal(); return; }
            const limit = document.getElementById('limit').value || 50;
            const wrap = document.getElementById('logsWrap');
            try {
                const res = await fetch('/logs?limit=' + limit, { headers: { 'X-API-Key': key } });
                if (res.status === 401) {
                    showToast('Invalid API key', true);
                    openKeyModal();
                    return;
                }
                const data = await res.json();
                if (!data.length) {
                    wrap.innerHTML = '<p class="empty">No log entries yet.</p>';
                    return;
                }
                let rows = data.map(e => `
                    <tr>
                        <td>${new Date(e.timestamp).toLocaleString()}</td>
                        <td>${e.ip || ''}</td>
                        <td>${e.action || ''}</td>
                        <td>${e.door ?? ''}</td>
                        <td class="${e.success ? 'ok' : 'fail'}">${e.success ? 'OK' : 'FAIL'}</td>
                        <td>${e.detail || ''}</td>
                    </tr>
                `).join('');
                wrap.innerHTML = `
                    <table>
                        <thead><tr><th>Time</th><th>IP</th><th>Action</th><th>Door</th><th>Result</th><th>Detail</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                `;
            } catch (err) {
                showToast('Network error: ' + err.message, true);
            }
        }
        window.addEventListener('DOMContentLoaded', () => {
            if (getApiKey()) loadLogs();
        });
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(
        INDEX_HTML, base_style=BASE_STYLE, key_modal=KEY_MODAL_HTML, toast_script=TOAST_SCRIPT
    )


@app.route("/logs-view")
def logs_view():
    return render_template_string(
        LOGS_HTML, base_style=BASE_STYLE, key_modal=KEY_MODAL_HTML, toast_script=TOAST_SCRIPT
    )


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
