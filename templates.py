"""Shared HTML/CSS/JS templates for the garage door GUI.

Used by gui.py (served on port 80). Fetch calls target API_BASE
(the same host on port 5000, where opener.py serves the actual API).
"""

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
        const API_BASE = window.location.protocol + '//' + window.location.hostname + ':5000';
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
                const res = await fetch(API_BASE + '/trigger/' + door, {
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
                const res = await fetch(API_BASE + '/logs?limit=' + limit, { headers: { 'X-API-Key': key } });
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
