import hmac
import os
import time

from dotenv import load_dotenv
from flask import Flask, abort, request
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

app = Flask(__name__)
relay_1 = OutputDevice(RELAY_PIN_1)
relay_2 = OutputDevice(RELAY_PIN_2)

RELAYS = {
    "1": relay_1,
    "2": relay_2,
}


def check_api_key():
    """Constant-time comparison to avoid timing attacks."""
    supplied = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(supplied, API_KEY):
        abort(401)


@app.route("/trigger/<door>", methods=["POST"])
def trigger(door):
    check_api_key()
    relay = RELAYS.get(door)
    if relay is None:
        abort(404, description=f"Unknown door '{door}'. Use '1' or '2'.")
    relay.on()
    time.sleep(PULSE_SECONDS)
    relay.off()
    return {"status": "triggered", "door": door}, 200


@app.route("/status/<door>", methods=["GET"])
def status(door):
    check_api_key()
    relay = RELAYS.get(door)
    if relay is None:
        abort(404, description=f"Unknown door '{door}'. Use '1' or '2'.")
    return {"door": door, "relay_on": relay.is_active}, 200


if __name__ == "__main__":
    # Dev only. In production, run via gunicorn instead:
    #   gunicorn --bind 0.0.0.0:5000 --workers 1 opener:app
    app.run(host="0.0.0.0", port=5000)
