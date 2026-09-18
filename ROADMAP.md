# Pi Dashboard — Roadmap

## Phase 1: Homelab Monitoring Widgets

### 1.1 Pi-hole Stats Widget
- [ ] Query Pi-hole API (`http://10.2.0.3/admin/api.php`)
- [ ] Show: queries today, blocked %, top blocked domains
- [ ] Background refresh every 5 minutes
- [ ] Partial template with stats cards

### 1.2 WireGuard Status Widget
- [ ] Parse `wg show` output or wg-easy API
- [ ] Show: connected clients, last handshake times
- [ ] Indicate if MacBook / travel router is connected
- [ ] Background refresh every 60 seconds

### 1.3 Service Health Widget
- [ ] Green/red indicators for: Gitea, Ollama, Open WebUI, Pi-hole, wg-easy
- [ ] Health checks via HTTP pings or socket checks
- [ ] Background refresh every 60 seconds

## Phase 2: Visual & UX Improvements

### 2.1 Dark/Light Mode Toggle
- [ ] CSS variables for light theme
- [ ] Toggle button in header
- [ ] Auto-switch based on time of day (optional)
- [ ] Persist preference in localStorage

### 2.2 Drag-and-Drop Widget Reordering
- [ ] Integrate lightweight drag-and-drop library (SortableJS)
- [ ] Save layout order to localStorage
- [ ] Restore layout on page load

### 2.3 Market Sparkline Charts
- [ ] Fetch intraday/24h price data from Yahoo Finance
- [ ] Render mini SVG sparklines in each ticker card
- [ ] Keep it lightweight — inline SVG, no charting library

## Phase 3: Nice-to-Have Features

### 3.1 Speed Test Widget
- [ ] Run periodic speed tests (speedtest-cli or fast.com API)
- [ ] Show: download, upload, ping
- [ ] Less frequent refresh (every 30–60 minutes)

### 3.2 RSS Feed Widget
- [ ] Configurable custom RSS feeds beyond existing news
- [ ] Separate card for user-defined feeds

### 3.3 Bookmarks / Quick Links Widget
- [ ] One-click links to: Gitea, Pi-hole admin, Open WebUI, wg-easy
- [ ] Configurable in config.py
- [ ] Simple grid of icon + label links
