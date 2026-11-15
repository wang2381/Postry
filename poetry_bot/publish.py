"""Upload the video to a public URL (Cloudinary) and publish it as an
Instagram Story via the Instagram Graph API."""
import hashlib
import os
import time
from pathlib import Path

import requests

GRAPH = "https://graph.facebook.com/v21.0"


def _need(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise SystemExit(f"Missing {name} in .env (see .env.example)")
    return v


def upload_public(video: Path) -> str:
    """Instagram fetches the video from a URL, so it must be publicly reachable."""
    cloud, key, secret = _need("CLOUDINARY_CLOUD_NAME"), _need("CLOUDINARY_API_KEY"), _need("CLOUDINARY_API_SECRET")
    ts = str(int(time.time()))
    sig = hashlib.sha1(f"timestamp={ts}{secret}".encode()).hexdigest()
    with open(video, "rb") as f:
        r = requests.post(f"https://api.cloudinary.com/v1_1/{cloud}/video/upload",
                          data={"api_key": key, "timestamp": ts, "signature": sig},
                          files={"file": f}, timeout=300)
    r.raise_for_status()
    return r.json()["secure_url"]


def _check(r: requests.Response) -> dict:
    if not r.ok:
        raise RuntimeError(f"Instagram API error {r.status_code}: {r.text}")
    return r.json()


def post_story(video_url: str) -> str:
    ig_id, token = _need("IG_USER_ID"), _need("IG_ACCESS_TOKEN")
    container = _check(requests.post(f"{GRAPH}/{ig_id}/media", data={
        "media_type": "STORIES", "video_url": video_url, "access_token": token}, timeout=60))["id"]

    for _ in range(60):  # wait for Instagram to finish processing (~5 min max)
        st = _check(requests.get(f"{GRAPH}/{container}", params={
            "fields": "status_code,status", "access_token": token}, timeout=60))
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing failed: {st}")
        time.sleep(5)
    else:
        raise RuntimeError("Timed out waiting for Instagram to process the video")

    return _check(requests.post(f"{GRAPH}/{ig_id}/media_publish", data={
        "creation_id": container, "access_token": token}, timeout=60))["id"]
