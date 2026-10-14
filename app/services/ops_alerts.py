"""Operational monitoring of the news backend -> ntfy push alerts.

Runs on the always-up dashboard so it can catch news-firebase being down or
producing no fresh articles — conditions that service can't self-report. Sends
exactly one alert when an incident starts and one recovery message when it
clears (state is kept in-process).
"""

import random
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from app.config import (
    NTFY_URL, NTFY_TOPIC, NEWS_STALE_ALERT_MIN, OLLAMA_URL, SUMMARY_STALL_ALERT_MIN,
)
from app.services import summaries
from app.services.pihole import PIHOLE_URL

PIHOLE_HOST = urllib.parse.urlparse(PIHOLE_URL).hostname

_alerting: dict[str, bool] = {}   # incident name -> currently alerting?


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


def _dns_ok(server: str, name: str = "pi.hole", attempts: int = 2) -> bool:
    """Raw UDP DNS A-query (no dig/dnspython needed). 'pi.hole' is answered by
    Pi-hole itself, so this tests Pi-hole — not the upstream/internet. Two
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
            rid, flags, _qd, ancount = struct.unpack(">HHHH", data[:8])
            if rid == qid and (flags & 0x000F) == 0 and ancount > 0:   # NOERROR + answer
                return True
        except Exception:
            pass
    return False


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
