"""Shared helpers for reset_demo.py and rehearse.py: serve the dummy sites, reset the demo, run the observer."""
import contextlib
import io
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PORT = 8000
EXPECTED_PAGES = 100            # 20 companies x 5 pages


def server_up():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("localhost", PORT)) == 0


@contextlib.contextmanager
def site_server():
    """Make sure the dummy sites are being served; start (and later stop) the server if they are not."""
    if server_up():
        yield
        return
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--directory", str(ROOT / "demo_sites")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(20):
            if server_up():
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(f"could not start the demo site server on port {PORT}")
        yield
    finally:
        proc.terminate()


def script(name):
    subprocess.run([sys.executable, str(ROOT / "demo_scripts" / name)], check=True, capture_output=True, cwd=ROOT)


def run_observer():
    """One observer run. Returns (counts, printed output)."""
    from observer import db, pipeline
    conn = db.connect()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            counts = pipeline.run_observer(conn)
    finally:
        conn.close()
    return counts, buf.getvalue()


def reset():
    """Sites back to baseline, local history wiped, demo entries cleared in Attio, fresh baseline taken."""
    from observer import airtable, attio, db
    script("generate_demo_sites.py")
    db.DB_PATH.unlink(missing_ok=True)
    cleared = (attio.clear_entries() if attio.enabled() else 0) + (airtable.clear_rows() if airtable.enabled() else 0)
    counts, _ = run_observer()
    if counts != {"new": EXPECTED_PAGES}:
        raise RuntimeError(f"baseline run was not clean: {counts}")
    return cleared
