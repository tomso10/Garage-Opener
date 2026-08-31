"""Garage door GUI — serves the button page and logs page.

Runs on port 80 (no API key needed just to load the pages). All actual
actions (trigger/status/logs) are called client-side against opener.py's
API on port 5000, using the X-API-Key header stored in the browser.

Run directly for testing:
    sudo python3 gui.py

In production, run via gunicorn as its own systemd service (needs a way
to bind port 80 without running the whole process as root — see the
garage-gui.service file's AmbientCapabilities setting):
    gunicorn --bind 0.0.0.0:80 --workers 1 gui:app
"""

from flask import Flask, render_template_string

from templates import BASE_STYLE, INDEX_HTML, KEY_MODAL_HTML, LOGS_HTML, TOAST_SCRIPT

app = Flask(__name__)


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


if __name__ == "__main__":
    # Dev only — binding port 80 directly requires root when run this way.
    app.run(host="0.0.0.0", port=80)
