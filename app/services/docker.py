"""Docker container monitoring via Unix socket API."""

import json
import socket
from app.config import DOCKER_SOCKET


def _docker_get(path: str) -> dict | list | None:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(DOCKER_SOCKET)
        request = f"GET {path} HTTP/1.1\r\nHost: localhost\r\nAccept: application/json\r\n\r\n"
        sock.sendall(request.encode())

        response = b""
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                # Check if we've received the full response
                if b"\r\n0\r\n\r\n" in response or (b"\r\n\r\n" in response and b"Transfer-Encoding: chunked" not in response):
                    break
            except socket.timeout:
                break
        sock.close()

        # Parse HTTP response
        text = response.decode("utf-8", errors="replace")
        # Split headers and body
        if "\r\n\r\n" not in text:
            return None
        header_part, body = text.split("\r\n\r\n", 1)

        # Handle chunked transfer encoding
        if "Transfer-Encoding: chunked" in header_part:
            # Parse chunked body
            decoded = ""
            remaining = body
            while remaining:
                line_end = remaining.find("\r\n")
                if line_end == -1:
                    break
                size_str = remaining[:line_end].strip()
                if not size_str:
                    remaining = remaining[line_end + 2:]
                    continue
                try:
                    chunk_size = int(size_str, 16)
                except ValueError:
                    break
                if chunk_size == 0:
                    break
                chunk_start = line_end + 2
                decoded += remaining[chunk_start:chunk_start + chunk_size]
                remaining = remaining[chunk_start + chunk_size + 2:]
            body = decoded

        return json.loads(body)
    except Exception as e:
        print(f"[docker] error: {e}")
        return None


def get_containers() -> list[dict]:
    data = _docker_get("/containers/json?all=true")
    if not data or not isinstance(data, list):
        return []
    containers = []
    for c in data:
        names = c.get("Names", [])
        name = names[0].lstrip("/") if names else "unknown"
        state = c.get("State", "unknown")
        status = c.get("Status", "")
        image = c.get("Image", "")
        # Shorten image name
        if "/" in image:
            image = image.split("/")[-1]
        if ":" in image:
            image = image.split(":")[0]
        ports = c.get("Ports", [])
        port_set = set()
        for p in ports:
            pub = p.get("PublicPort")
            priv = p.get("PrivatePort")
            if pub:
                port_set.add(f"{pub}:{priv}")
            elif priv:
                port_set.add(str(priv))
        containers.append({
            "name": name,
            "image": image,
            "state": state,
            "status": status,
            "ports": ", ".join(sorted(port_set)) if port_set else "—",
        })
    return containers
