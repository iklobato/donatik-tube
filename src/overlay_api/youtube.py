"""
YouTube Live: OAuth redirect/callback helpers and push-URL refresh from YouTube API.
"""

import json
import logging
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from config.settings import get_settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def build_connect_url(redirect_uri: str, state: str | None = None) -> str | None:
    """Build Google OAuth redirect URL for YouTube. Returns None if client_id not set."""
    yt = get_settings().youtube
    if not yt.client_id:
        return None
    params = {
        "client_id": yt.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict | None:
    """Exchange authorization code for access_token and refresh_token. Returns dict or None on error."""
    yt = get_settings().youtube
    if not yt.client_id or not yt.client_secret:
        return None
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": yt.client_id,
        "client_secret": yt.client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as e:
        logger.warning("Token exchange failed: %s", e)
        return None


def get_channel_id(access_token: str) -> str | None:
    """Call YouTube API channels.list(mine=true) to get the channel ID for the authenticated user."""
    req = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/channels?part=id&mine=true",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("items", [])
        if items:
            return items[0].get("id")
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Get channel id failed: %s", e)
    return None


def refresh_access_token(refresh_token: str) -> str | None:
    """Get a new access_token using refresh_token. Returns access_token or None."""
    yt = get_settings().youtube
    if not yt.client_id or not yt.client_secret:
        return None
    data = urllib.parse.urlencode({
        "client_id": yt.client_id,
        "client_secret": yt.client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req) as resp:
            out = json.loads(resp.read().decode())
        return out.get("access_token")
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as e:
        logger.warning("Token refresh failed: %s", e)
        return None


def get_ingestion_urls() -> list[str]:
    """
    For each channel in YOUTUBE__REFRESH_TOKENS, refresh token, create/reuse liveStream and liveBroadcast,
    return list of rtmp://ingestionAddress/streamName.
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    yt = get_settings().youtube
    if not yt.client_id or not yt.client_secret or not yt.refresh_tokens.strip():
        return []
    try:
        tokens = json.loads(yt.refresh_tokens)
    except json.JSONDecodeError:
        return []
    if not isinstance(tokens, dict):
        return []

    urls: list[str] = []
    for channel_id, ref_tok in tokens.items():
        if not ref_tok or not isinstance(ref_tok, str):
            continue
        access_token = refresh_access_token(ref_tok)
        if not access_token:
            continue
        creds = Credentials(token=access_token)
        try:
            youtube = build("youtube", "v3", credentials=creds)

            # Create or reuse a live stream; get ingestion info
            stream_list = youtube.liveStreams().list(part="id,cdn", mine=True).execute()
            stream_id = None
            ingestion_address = None
            stream_name = None
            if stream_list.get("items"):
                s = stream_list["items"][0]
                stream_id = s["id"]
                cdn = s.get("cdn", {})
                ing = cdn.get("ingestionInfo", {})
                ingestion_address = ing.get("ingestionAddress")
                stream_name = ing.get("streamName")
            if not stream_id or not ingestion_address or not stream_name:
                # Create new stream (insert returns the resource directly)
                s = youtube.liveStreams().insert(
                    part="snippet,cdn,status",
                    body={
                        "snippet": {"title": "Donatik Live"},
                        "cdn": {"resolution": "1080p", "frameRate": "30fps"},
                    },
                ).execute()
                stream_id = s.get("id")
                cdn = s.get("cdn", {})
                ing = cdn.get("ingestionInfo", {})
                ingestion_address = ing.get("ingestionAddress")
                stream_name = ing.get("streamName")
                if not stream_id or not ingestion_address or not stream_name:
                    continue

            if not ingestion_address or not stream_name:
                continue
            rtmp_url = f"rtmp://{ingestion_address}/{stream_name}"
            urls.append(rtmp_url)

            # Ensure a broadcast is bound to this stream
            broadcast_list = youtube.liveBroadcasts().list(
                part="id,contentDetails",
                broadcastStatus="all",
            ).execute()
            bound_broadcast_id = None
            for b in broadcast_list.get("items", []):
                if b.get("contentDetails", {}).get("boundStreamId") == stream_id:
                    bound_broadcast_id = b["id"]
                    break
            if not bound_broadcast_id:
                # Create broadcast and bind (insert returns the resource directly)
                insert_b = youtube.liveBroadcasts().insert(
                    part="snippet,status",
                    body={
                        "snippet": {"title": "Donatik Live", "scheduledStartTime": "2030-01-01T00:00:00Z"},
                        "status": {"privacyStatus": "unlisted"},
                    },
                ).execute()
                bid = insert_b.get("id")
                if bid:
                    youtube.liveBroadcasts().bind(part="id,contentDetails", id=bid, streamId=stream_id).execute()
        except Exception as e:
            logger.warning("YouTube API for channel %s: %s", channel_id, e)
    return urls


def write_push_conf(urls: list[str]) -> bool:
    """Write Nginx push directives to YOUTUBE__PUSH_CONF_PATH. Returns True on success."""
    yt = get_settings().youtube
    path = yt.push_conf_path
    lines = [f"push {u};" for u in urls]
    if not urls:
        lines = ["# No YouTube push URLs configured"]
    try:
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except OSError as e:
        logger.warning("Write push conf %s: %s", path, e)
        return False


def reload_nginx() -> None:
    """Run docker exec nginx-rtmp nginx -s reload. No-op if not available."""
    try:
        subprocess.run(
            ["docker", "exec", "nginx-rtmp", "nginx", "-s", "reload"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug("Nginx reload skipped: %s", e)


def _youtube_push_refresh_loop() -> None:
    """Background loop: refresh ingestion URLs, write push conf, reload nginx."""
    yt = get_settings().youtube
    if not yt.client_id or not yt.refresh_tokens.strip():
        return
    interval = max(60, yt.refresh_interval_seconds)
    while True:
        time.sleep(interval)
        try:
            urls = get_ingestion_urls()
            if write_push_conf(urls):
                reload_nginx()
        except Exception as e:
            logger.warning("YouTube push refresh: %s", e)


def start_youtube_push_refresh_thread() -> None:
    """Start daemon thread for YouTube push config refresh. No-op if YouTube not configured."""
    yt = get_settings().youtube
    if not yt.client_id or not yt.refresh_tokens.strip():
        return
    t = threading.Thread(target=_youtube_push_refresh_loop, daemon=True)
    t.start()
    logger.info("YouTube push refresh thread started (interval=%ss)", yt.refresh_interval_seconds)
