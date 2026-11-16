"""Minimal fal.ai client (queue REST API): submit -> poll -> fetch result -> download."""
import os
import time
from pathlib import Path

import requests

QUEUE = "https://queue.fal.run"


def _headers() -> dict:
    key = os.getenv("FAL_KEY")
    if not key:
        raise SystemExit("Missing FAL_KEY in .env")
    return {"Authorization": f"Key {key}", "Content-Type": "application/json"}


def run(endpoint: str, payload: dict, timeout: float = 900, poll: float = 4) -> dict:
    """Run a fal model and return its JSON result. Use the URLs from the submit
    response as-is (they omit the sub-path of the endpoint)."""
    r = requests.post(f"{QUEUE}/{endpoint}", json=payload, headers=_headers(), timeout=60)
    if not r.ok:
        raise RuntimeError(f"fal submit failed {r.status_code}: {r.text[:500]}")
    job = r.json()
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = requests.get(job["status_url"], headers=_headers(), timeout=60)
        s.raise_for_status()
        st = s.json()
        if st.get("status") == "COMPLETED":
            if st.get("error"):
                raise RuntimeError(f"fal job failed: {st['error']}")
            res = requests.get(job["response_url"], headers=_headers(), timeout=120)
            if not res.ok:
                raise RuntimeError(f"fal result failed {res.status_code}: {res.text[:500]}")
            return res.json()
        time.sleep(poll)
    raise TimeoutError(f"fal job {job['request_id']} timed out")


def download(url: str, dest: str | Path) -> Path:
    dest = Path(dest)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return dest
