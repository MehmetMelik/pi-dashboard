"""Operational monitoring of the news backend -> ntfy push alerts.

Runs on the always-up dashboard so it can catch news-firebase being down or
producing no fresh articles — conditions that service can't self-report. Sends
exactly one alert when an incident starts and one recovery message when it
clears (state is kept in-process).
"""

import os
import random
import socket
import sqlite3
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta, timezone

from app.config import (
    DUCKDNS_HOSTNAME, DUCKDNS_MISMATCH_ALERT_MIN, FEED_FAIL_ALERT_HOURS, FEED_HEALTH_DB_PATH,
    NTFY_URL, NTFY_TOPIC, NEWS_STALE_ALERT_MIN, OLLAMA_URL, SUMMARY_STALL_ALERT_MIN,
)
from app.services import summaries
from app.services.pihole import PIHOLE_URL

PIHOLE_HOST = urllib.parse.urlparse(PIHOLE_URL).hostname
DUCKDNS_NAMESERVER = "ns1.duckdns.org"   # ask DuckDNS directly, so no resolver cache hides a stale record

_alerting: dict[str, bool] = {}   # incident name -> currently alerting?
_duckdns_mismatch_since: float | None = None


def _push(title: str, message: str, priority: str = "default", tags: str = "") -> None:
    if not NTFY_TOPIC:
        return
    try:
        url = f"{NTFY_URL.rstrip('/')}/{NTFY_TOPIC}"
        req = urllib.request.Request(url, data=message.encode("utf-8"), method="POST")
        req.add_header("Title", title.encode("ascii", "ignore").decode())  # headers are latin-1
        req.add_header("Priority", priority)
        if tags:
            req.add_header("Tags", tags)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[ops] ntfy push failed: {e}")


def _transition(name: str, bad: bool, alert_title: str, alert_msg: str, recover_msg: str,
                priority: str = "urgent") -> None:
    """One alert on entering the bad state, one recovery on leaving it."""
    was = _alerting.get(name, False)
    if bad and not was:
        _alerting[name] = True
        _push(alert_title, alert_msg, priority=priority, tags="rotating_light")
    elif not bad and was:
        _alerting[name] = False
        _push(f"Recovered: {name}", recover_msg, priority="default", tags="white_check_mark")


def _service_active(unit: str) -> bool:
    try:
        r = subprocess.run(["systemctl", "is-active", unit],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() == "active"
    except Exception:
        return True  # never false-alarm just because the check itself failed


def _dns_a(server: str, name: str, attempts: int = 2) -> list[str] | None:
    """Raw UDP DNS A-query (no dig/dnspython needed). Returns the A records,
    [] for an answer without any, or None if the server never answered. Two
    attempts so a single dropped UDP packet doesn't false-alarm."""
    qname = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    for _ in range(attempts):
        qid = random.randint(0, 0xFFFF)
        packet = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0) + qname + struct.pack(">HH", 1, 1)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(3)
                s.sendto(packet, (server, 53))
                data, _ = s.recvfrom(512)
            rid, flags, qdcount, ancount = struct.unpack(">HHHH", data[:8])
            if rid != qid:
                continue
            if flags & 0x000F:            # any error rcode
                return []
            off = 12
            for _ in range(qdcount):
                off = _skip_name(data, off) + 4
            ips = []
            for _ in range(ancount):
                off = _skip_name(data, off)
                rtype, _cls, _ttl, rdlen = struct.unpack(">HHIH", data[off:off + 10])
                off += 10
                if rtype == 1 and rdlen == 4:
                    ips.append(socket.inet_ntoa(data[off:off + 4]))
                off += rdlen
            return ips
        except Exception:
            pass
    return None


def _skip_name(data: bytes, off: int) -> int:
    """Offset just past a (possibly compressed) DNS name."""
    while data[off]:
        if data[off] & 0xC0 == 0xC0:      # compression pointer ends the name
            return off + 2
        off += data[off] + 1
    return off + 1


def _dns_ok(server: str, name: str = "pi.hole") -> bool:
    """'pi.hole' is answered by Pi-hole itself, so this tests Pi-hole — not the
    upstream/internet."""
    return bool(_dns_a(server, name))


def _public_ip() -> str | None:
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                ip = r.read().decode().strip()
            socket.inet_aton(ip)
            return ip
        except Exception:
            pass
    return None


def _check_duckdns() -> None:
    """Alert when the DuckDNS name hasn't matched the home's public IP for
    DUCKDNS_MISMATCH_ALERT_MIN — the VPN is unreachable from outside meanwhile.
    On 2026-10-18 the ISP changed the IP while DuckDNS was returning 502s, and
    nothing noticed. Short gaps (the 5-minute updater catching up) don't alert."""
    global _duckdns_mismatch_since
    public = _public_ip()
    if public is None:
        return  # our own internet is down; nothing useful to compare
    try:
        published = _dns_a(socket.gethostbyname(DUCKDNS_NAMESERVER), DUCKDNS_HOSTNAME)
    except OSError:
        published = None
    if published is not None and public in published:
        _duckdns_mismatch_since = None
    elif _duckdns_mismatch_since is None:
        _duckdns_mismatch_since = time.time()
    stale_min = 0 if _duckdns_mismatch_since is None else (time.time() - _duckdns_mismatch_since) / 60
    shown = ", ".join(published) if published else "nothing"
    _transition(
        "duckdns", stale_min >= DUCKDNS_MISMATCH_ALERT_MIN,
        "DuckDNS OUT OF DATE",
        f"{DUCKDNS_HOSTNAME} points to {shown}, but the home IP is {public} (for {int(stale_min)} min). "
        "The VPN can't be reached from outside until it updates. Check ~/dev/duckdns/duck.log on the Pi.",
        f"{DUCKDNS_HOSTNAME} matches the home IP again ({public}).",
        priority="high",
    )


def _failing_feeds() -> dict[str, tuple[str, str]] | None:
    """Feeds that have failed every fetch for FEED_FAIL_ALERT_HOURS, as
    {source: (failing_since, last_error)}; None if the DB can't be read."""
    if not os.path.exists(FEED_HEALTH_DB_PATH):
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=FEED_FAIL_ALERT_HOURS)).isoformat()
    try:
        with closing(sqlite3.connect(f"file:{FEED_HEALTH_DB_PATH}?mode=ro", uri=True, timeout=5)) as db:
            rows = db.execute("SELECT source, failing_since, last_error FROM feed_status "
                              "WHERE failing_since IS NOT NULL AND failing_since < ?", (cutoff,)).fetchall()
    except sqlite3.Error:
        return None   # e.g. news-firebase hasn't added the failing_since column yet
    return {source: (since, error) for source, since, error in rows}


def _check_feeds() -> None:
    """One alert per news feed that keeps failing (moved URL, shut-down feed).
    In Oct 2026 Reuters, Nikkei Asia, Medical News Today and CDC were dead for
    weeks with nothing but a log line to show for it."""
    failing = _failing_feeds()
    if failing is None:
        return
    alerting = {name[len("feed: "):] for name, on in _alerting.items() if on and name.startswith("feed: ")}
    for source in failing.keys() | alerting:
        since, error = failing.get(source, ("", ""))
        _transition(
            f"feed: {source}", source in failing,
            f"News feed FAILING: {source}",
            f"{source} has failed every fetch since {since[:16].replace('T', ' ')} UTC ({error}). "
            "Fix or replace its URL in news-firebase/config.py.",
            f"{source} is fetching again (or was removed from the feed list).",
            priority="default",
        )


def _http_ok(url: str) -> bool:
    """True if a web server answers (any status < 500); False only when it's
    unreachable — e.g. FTL silently lost its optional web ports on 2026-10-03."""
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False


def _ollama_ok() -> bool:
    # Answers within the timeout? Catches both "down" and "hung" (which the
    # staleness + heartbeat checks miss, since articles keep flowing).
    try:
        urllib.request.urlopen(f"{OLLAMA_URL.rstrip('/')}/api/tags", timeout=5)
        return True
    except Exception:
        return False


def check_once() -> None:
    if not NTFY_TOPIC:
        return

    # 1. news-firebase service not running
    _transition(
        "news-firebase down", not _service_active("news-firebase.service"),
        "News backend DOWN",
        "news-firebase.service is not active on the Pi.",
        "news-firebase.service is active again.",
    )

    # 2. no fresh articles (service may be 'running' but not doing its job)
    ts = summaries.latest_article_ts()
    if ts is not None:
        age_min = (time.time() - ts) / 60
        _transition(
            "news stale", age_min > NEWS_STALE_ALERT_MIN,
            "News backend STALE",
            f"No new article for {int(age_min)} min (threshold {NEWS_STALE_ALERT_MIN}).",
            "New articles are flowing again.",
        )

    # 3. summariser (Ollama) down or hung — articles keep flowing but lose
    #    ai_summary/region/tags, and breaking-news alerts stop. Neither the
    #    staleness alert nor the dead-man's switch would catch this.
    _transition(
        "ollama down", not _ollama_ok(),
        "Summariser (Ollama) DOWN",
        "Ollama isn't responding — new articles won't get summaries, regions, tags or breaking-news alerts.",
        "Ollama is responding again.",
    )

    # 4. summaries stalled: articles are arriving but none are being summarised
    #    (e.g. Ollama up but the model errors/hangs). Stateless: compare newest
    #    article vs newest summary time.
    art = summaries.latest_article_ts()
    summ = summaries.latest_summary_ts()
    now = time.time()
    window = SUMMARY_STALL_ALERT_MIN * 60
    if art is not None and (now - art) < window:
        stalled = (summ is None) or (now - summ) > window
        _transition(
            "summaries stalled", stalled,
            "Summaries STALLED",
            f"Articles are arriving but none summarised in {SUMMARY_STALL_ALERT_MIN} min.",
            "Summaries are flowing again.",
        )

    # 5. Pi-hole DNS — every LAN device and VPN client resolves through it.
    _transition(
        "pihole dns", not _dns_ok(PIHOLE_HOST),
        "Pi-hole DNS DOWN",
        f"Pi-hole isn't answering DNS on {PIHOLE_HOST} — LAN and VPN devices can't resolve names.",
        "Pi-hole is answering DNS again.",
    )

    # 6. Pi-hole admin UI — FTL's web ports are 'optional', so it can lose its
    #    web server while DNS keeps working (2026-10-03, unnoticed for 11 days).
    _transition(
        "pihole admin", not _http_ok(f"{PIHOLE_URL}/admin/"),
        "Pi-hole admin UI DOWN",
        "Pi-hole's web admin isn't responding (DNS/ad-blocking may still work). Fix: docker restart pihole",
        "Pi-hole admin UI is responding again.",
        priority="high",
    )

    # 7. DuckDNS still points at the home IP — the VPN's only way in from outside.
    if DUCKDNS_HOSTNAME:
        _check_duckdns()

    # 8. A news feed has failed every fetch for FEED_FAIL_ALERT_HOURS.
    _check_feeds()
