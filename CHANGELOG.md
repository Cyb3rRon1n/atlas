# Changelog

All notable changes to Lanxang. Versions follow [semantic versioning](https://semver.org); the
Docker image is published as `ghcr.io/cyb3rron1n/lanxang:<version>` for every release.

## Unreleased

### Fixed
- The speed test card labels its low point "Slowest, 30 days" (it counted tests, not days).

## 1.5.2 - 2026-11-21

### Added
- A daily internet speed test (opt-in: `internet.speed_test`, or the Setup tab's *Internet speed test* card):
  download, upload and ping against Cloudflare's public speed test after 04:00 local time, shown on Home with the
  slowest download of the last 30 days. `lanxang internet speed --force` runs one now.
- Home shows the wired devices that moved the most data in the last 24 hours, from the switch port counters the
  cabling map already reads.

### Security
- Every page now tells browsers not to show it inside another site's frame (`X-Frame-Options: DENY`,
  `frame-ancestors 'none'`), so a hidden Approve button can't be placed under a decoy page.
- The built-in sign-in forgets failed attempts once they are older than five minutes, so guesses from many addresses
  can't keep growing its memory.

### Fixed
- The weak Wi-Fi row only suggests 5 GHz when one of the devices is on 2.4 GHz.

## 1.5.1 - 2026-11-20

### Added
- Home shows a row when devices have a weak Wi-Fi signal (-70 dBm or worse, from UniFi or the router): each one's
  signal, band and access point. It is information only and never turns Home amber.

### Changed
- Cable problems name what is plugged into the port: "Link went down and up: Desk PC (core-switch gi5)" in alerts,
  on Home and on the Cabling page.
- Removed `requirements.txt`. Nothing installed from it; `pip install -e .` (or the Docker image) is the way.

### Fixed
- Behind a reverse proxy, the built-in sign-in counted every visitor's wrong passwords as one, so five wrong guesses
  from anyone locked everyone out for five minutes. Requests from a private address now count the address in the
  proxy's `X-Forwarded-For`.
- Home's Services strip missed an outage that crossed midnight (failures split between two days never reached the
  limit on either). A run of failures now counts across midnight and marks both days.

## 1.5.0 - 2026-11-20

A design pass: Home becomes a briefing of what's wrong and what changed since your last visit, Coverage says whether you can trust the device list and how to see more, and Overview and Uptime get trend lines and a status line.

### Changed
- Scan history (each source's runs) is kept for 8 days instead of the last 50 runs, so Coverage can show a week.
- Home is now a briefing, top to bottom: a status line ("1 thing needs a look", with when the last scan ran, and
  "No recent scan" when scans have stopped, "Scans are failing" when every source's latest scan failed, and
  "Couldn't read posture / alerts" instead of all-clear when a part it rests on can't be read), the problems as rows with their buttons (replacing the Needs attention
  table), the getting-started steps, **Since you were here** (what changed since your last visit, newest first, with
  a link to all of it in Activity) beside the Ask Lanxang questions, then vitals with a week of history (devices
  online, internet, services by day, storage, security, power) above the existing cards. The Ad blocking and Smart
  home number tiles are gone; their cards stay.
- Coverage answers "can I trust the device list?": a headline ("33 of 42 devices are seen by two or more sources",
  or "All 12 devices come from one source (LAN scan)"), a card per source with friendly names, its devices, when it
  last ran and a 7-day strip in your time zone (the pill says "ok", "2 bad days", or "failing" with the error), and
  **Ways to see more**: devices that rely on one source, adding a switch (SNMP) or devices with an unknown
  connection, wired or unknown devices (not Proxmox guests) missing from the latest cabling scan (when it is set up), and done rows for "Every known device has been
  seen" and "No device has gone quiet" (gone quiet links to Triage). `/api/coverage` adds `runs`, `counted`,
  `multi`, `total`, `single_source`, `unknown_connection` and `off_map`. Only a source with an ok run this
  week counts, and a source whose latest run failed keeps the headline from reading as all-clear.
- Security trends: the charts have gridlines and x/y values (sizes or counts up the side, times or weekdays along
  the bottom), in your own clock and time zone instead of UTC.
- Overview: each host and Proxmox node meter (CPU, RAM, disk) has the last 24 hours as a small line beside it (and the
  page loads faster: it no longer computes Home's briefing), a short list of counts (containers, Proxmox guests, LAN hosts) links to where each is listed, and the inventory
  dump folds under "Raw snapshot".
- Uptime: a headline over the checks ("All 3 checks up", "1 check down"), counting the built-in Internet check when
  it is on ("Internet down", "Internet and all 3 checks up"). A check with no recent result reads as unknown, never
  as up. The explanation folds under "How checks work".

## 1.4.2 - 2026-11-19

### Changed
- Security page, What the internet sees: also lists the software Shodan detected on your IP (for example
  "nginx 1.18.0").
- Internet view: a failed Shodan lookup is tried again an hour later instead of the next day.
- The chat column beside the page narrows on smaller windows (down to 280 px) so the page keeps room.

### Fixed
- Chat tools: a limit the model sends as text ("lots") falls back to the default instead of failing the tool, and
  alert details are cut to 300 characters so a long one can't crowd out the answer.
- Daily summary: after it was off for more than two days, the next one no longer lists every device that went
  quiet in the meantime as "gone quiet" yesterday; a day with nothing to send no longer records a send time.

## 1.4.1 - 2026-11-19

### Fixed
- Home, Security posture card: with the internet view on, the Internet line now also shows a clean result
  ("No open ports seen") and an IP Shodan has no data for ("Shodan has no data for this IP"), instead of
  leaving the line out, so you can tell a check ran.

## 1.4.0 - 2026-11-19

See what the internet sees on your home IP, ask the local chat about posture, devices, alerts, disks and uptime, and get an optional daily summary of what changed.

### Added
- Optional daily summary: set `notify.daily_summary` to a time like `08:00` (in the alert time zone,
  `notify.timezone`) or use the Setup page's Daily summary card, and once a day Lanxang sends what changed in the
  last 24 hours: new devices, alerts opened or cleared, public routes added or removed, devices gone quiet. Nothing
  is sent on a day without changes.
- Chat can now look things up in the posture data: new tools `get_posture`, `get_devices`, `get_alerts`, `get_disks`,
  `get_uptime` and (with the Internet view on) `get_internet_view`, all read-only and capped to short lists so small
  local models cope. The Security page gains the chip "What can the internet see on my network?".
- Internet view (opt-in): once a day `lanxang internet check` asks Shodan's InternetDB what it sees on your home's
  public IP. An open port you don't expect (`posture.expected_ports`, 80 and 443 by default) or a reported CVE
  alerts; the Security page shows **What the internet sees** and the Home Security posture card a one-line summary.
  Turn it on with `posture.internet_view` or the Setup page's Internet view card — it sends your home IP to Shodan.
  A port's alert clears when Shodan no longer sees it or when you add it to the expected ports (Save on the card
  rechecks at once). A failed lookup, or an empty answer after Shodan had data, keeps the last answer and its
  alerts; a new public IP starts from nothing.

### Fixed
- Activity, with the time zone set to "this browser": days and "×N today" counts now follow the viewer's own day
  (the browser tells Lanxang its zone), so repeats near midnight are no longer counted into the wrong day.
- `tools/screenshots.sh` picks free ports instead of fixed ones, so it runs beside another copy or service.

## 1.3.0 - 2026-11-19

The old Atlas names are gone; re-running the installer moves an older install over.

### Removed
- The old Atlas names, as announced: the `atlas` command, reading `atlas.yaml`, the `ATLAS_*` setting names and
  the `ghcr.io/cyb3rron1n/atlas` image. Fleet checks run `lanxang doctor` on the other nodes.
- The compose file always mounts `lanxang.yaml`; `LANXANG_CONFIG` is no longer used.

### Upgrading
- Re-run the installer: it renames `atlas.yaml` to `lanxang.yaml`, `${ATLAS_…}` references in it and the `ATLAS_*` entries in `.env` to
  `LANXANG_*` (the old file is kept as `.env.before-1.3`). By hand, see Upgrading from atlas in Getting started.
- Until then Lanxang logs a warning that names what it no longer reads. Secrets saved on the Setup page under
  old names still work and are saved under the new ones next time. Data, sign-in and history are unchanged.

## 1.2.0 - 2026-11-19

Preferences: a gear in the top-right header for theme, motion, contrast, time and date, text size, density, start page and a collapsible sidebar, plus an accessibility pass and keyboard shortcuts.

### Added
- A header bar at the top right of every page: a theme button that cycles Light, Dark and System (follows the device), and a gear that opens Preferences. On phones both sit in the top bar.
- Preferences, a side panel that applies each change at once and remembers it in this browser: theme, reduced motion (System / On / Off), high contrast, text size (S / M / L), density (Comfortable / Compact), start page (Home, Devices, Alerts, Network map, Servers or Security) and a collapsed, icons-only sidebar.
- The sidebar has a collapse button and line icons for each section; it stays in view while the page scrolls.
- Preferences > Time & date, saved on the server for everyone: a 24-hour or 12-hour clock, the time zone (this browser, UTC or any IANA zone such as America/New_York) and the date format (2026-11-19, 19/11/2026 or 11/19/2026). It applies at once to every page and to alert messages, the test alert and the weekly summary; with "this browser", messages use UTC and say so. Also `display:` in the config file.
- The weekly summary says which week it covers and when it was sent; the test alert says when it was sent.
- Keyboard shortcuts: `g` then `h` Home, `g d` Devices, `g a` Alerts, `g s` Setup; `/` jumps to the page's search or filter box; `?` shows the list (Escape closes it). They do nothing while you type in a field or hold Ctrl, Alt or Cmd, and Preferences > Navigation mentions them.
- A "Skip to content" link, shown when you press Tab on any page.

### Changed
- Status is never shown by colour alone: status dots carry a mark (✓ ok, ! warning, × down, – unknown), alert rows say Problem, Watching or Resolved with an icon, and Exposure's status tiles and problem boxes carry a mark or word too.
- Gold text on light backgrounds is darker, for at least 4.5:1 contrast; high contrast also darkens gold and the warning and problem tints.
- The header bar comes first when you Tab through a page, then the sidebar, then the page.
- Alerts and Services no longer show headings for empty sections: the empty ones share one short line, and Alerts with nothing at all says "All clear".
- Alerts and Uptime use the same friendly times as the rest of the UI ("2 h ago", "yesterday 14:32").
- Activity groups by day in your time zone (or the one chosen in Preferences), not by UTC day.
- A device's "Where Lanxang saw it" table drops the ID column when the ID is just the MAC again.
- The sidebar's "Dark mode" button moved to the header bar; Sign out stays in the sidebar. A saved light or dark choice keeps working.
- Page text sizes are now relative to the browser's text size, so text size and browser zoom scale every page evenly.
- Times older than a week show the date ("2026-10-28") instead of "28 Oct", and Activity's day headings read "Wed 2026-10-28"; device "last seen" times in alerts now name their zone. Uptime's outage list and Visitors' times use the same friendly times as the rest of the UI.

## 1.1.0 - 2026-11-19

A polish release: light mode by default, a consistent look across every page, and friendlier empty pages.
### Changed
- The web UI now opens in light mode whatever the system theme; dark is still one click away in the sidebar and is remembered.
- Every time on Triage, Devices, Coverage, Home and Activity is written the same way and in the viewer's own time zone: "5 min ago", "today 14:32", "yesterday 14:32", "12 Nov". Activity no longer says "Times are UTC".
- The light theme's greys (table headers, tiles, borders, the cabling canvas, the Services lanes) are now jade-tinted instead of blue-grey; dark mode's muted text and sidebar text too.
- Activity's *What changed* list uses the app's line icons instead of emoji, and a run of new devices is one row that opens to list them ("37 new devices").
- Sign-in and first-run setup show the Lanxang logo and name.
- Setup's hints suggest the account name `lanxang` (SNMPv3 user, Proxmox user and token, NAS user); a new switch saved with a blank SNMPv3 user gets `lanxang`. Saved switches and settings keep their names.
- The device page's *Important* box no longer names Signal: alerts go to whichever channels are set up.
- Copy: spaced hyphens in sentences are now em dashes; counts say "1 service", "1 unnamed device", "1 low battery".
- One control system in the web UI: buttons, inputs and selects share one height (36 px), border, radius and a jade focus ring, with primary, secondary and danger (destructive: Turn off, Remove, Merge) buttons, a compact size for table and alert rows, and a clear disabled state. Uptime's, Cabling's and the sign-in page's own button and input styles are gone.
- Every time window and view switch is the same segmented control with the same labels: Activity, Trends and Visitors ("24 hours / 7 days / 30 days"), Exposure ("This hour / 1 hour / 24 hours"), Activity's filters and Cabling's Front panels / Map. URLs and query parameters are unchanged.
- Setup cards line their buttons up along the bottom, in the order Turn off (left), Test, Save. Alerts' Investigate is a button; Cabling's CSV link is "Export CSV".
- Pages with nothing to show yet say why and what fills them, in one shared style (icon, title, one sentence, next step): Home's *Security trends* before any traffic is counted (no empty chart; a zero *New destinations* chart becomes one line), Trends until there are enough samples to draw a line (pointing to a longer window when that one already has history), Visitors while tracking is off, Coverage before the first scan, and Chat while no AI is set up (it links to Setup's AI card). The sidebar's Chat link is hidden while no AI is set up.
- The device page starts with a status line (Online / Gone quiet chip, kind, IP and MAC, last seen, *View on front panel*), lays its fields out in two columns (one on a phone), and shows proper-case choices ("Network gear", "Known", "Wired"); the stored values are unchanged. Merge moved to a *Danger zone* card: no device is picked until you choose one, and Merge asks for a confirmation on the page before it runs (Cancel has focus; Escape closes it).

### Fixed
- Activity rendered an empty page when a saved change event held plain text instead of the usual fields; a row that can't be read is now shown as-is or left out. The demo data writes the real format.
- No more empty gap under the page title on Devices, Triage, Coverage and Cabling (the message line takes no space until it has something to say).
- Devices, the device page, Triage, Coverage, Uptime and Cabling no longer scroll sideways on a phone: inputs fit the screen and wide tables scroll inside their card.
- Uptime's *Add heartbeat* form: the controls are spaced and the name placeholder is no longer cut off.
- Services no longer says "Snapshot . Click…" when the snapshot has no time.

## 1.0.1 - 2026-11-18

### Fixed
- First start on a fresh data volume no longer fails when the web and scan containers create the database tables at the same moment (`table events already exists`); the loser now retries.
- The setup log from `lanxang init` is written to `logs/lanxang-init-<timestamp>.log` (older `atlas-init-*` logs are left alone).
- Setup page text uses em dashes instead of spaced hyphens.

## 1.0.0 - 2026-11-18

### Changed
- **Atlas is now Lanxang** (ລ້ານຊ້າງ, the old Lao kingdom, "land of a million elephants"): a new name, logo,
  colours and typeface (Lexend, shipped with the app - nothing is loaded from an outside font host), and the Lao
  name under the logo. The repo is now github.com/Cyb3rRon1n/lanxang, the docs are at
  cyb3rron1n.github.io/lanxang/ and the image is `ghcr.io/cyb3rron1n/lanxang`. Old repo and docs links redirect.
- **Polish**: Home hides the AI check-up card and the Chat link while no AI is set up; the *Host health* wording;
  card dots and borders now agree on colour; cleaner punctuation; messages name the config file actually in use;
  new light and dark screenshots.

### Upgrading
**Nothing is required** - an existing install keeps working and keeps its data and history. Until 1.2:
- the `atlas` command still works (and prints a one-line notice);
- `atlas.yaml` is still read when there is no `lanxang.yaml`;
- `ATLAS_*` settings still work next to `LANXANG_*` (the new name wins);
- the image is also still published as `ghcr.io/cyb3rron1n/atlas`;
- the compose services keep their names, `atlas` and `atlas-scan`.

To move to the new names when you like: rename `atlas.yaml` to `lanxang.yaml` and set
`LANXANG_CONFIG=lanxang.yaml` in `.env`; rename your `ATLAS_*` variables to `LANXANG_*`; and point the image at
`ghcr.io/cyb3rron1n/lanxang`.

Three things can affect you:
- Alert email subjects now start with "Lanxang:" - update any mail filters.
- A scan interval set only in your host shell (not in `.env` or an override file) no longer reaches the
  container. Put it in `.env`.
- A clone with a hand-pinned pre-1.0 `ATLAS_TAG=0.x` should switch to a 1.0 tag; the new image name has no 0.x
  tags.

### Removed in 1.2 (announcement)
The `atlas` command, the `atlas.yaml` fallback, the `ATLAS_*` setting names and the `ghcr.io/cyb3rron1n/atlas`
image name.

## 0.12.1 - 2026-11-18

### Fixed
- **One problem, one line on Home**: a degraded pool or failing disk was listed twice under *Needs attention*
  (the Storage line and its own alert), so Home said "2 things need a look" for one. Its *Details* now opens the
  alert, which says what to do, instead of Overview.

## 0.12.0 - 2026-11-18

### Added
- **Router DHCP names** (Setup → *OpenWrt router*): every scan reads the names your OpenWrt router's DHCP
  server gave each device, and who is on which Wi-Fi, and links them to devices by MAC - so Devices can tell you
  what an unknown address is. Read-only, through the router's web interface (the one LuCI uses); a router that
  doesn't answer never fails the scan.
- **Home Assistant** (Setup → *Home Assistant*): a *Smart home* tile and card on Home with the devices that
  dropped out (all their sensors, switches, locks... unavailable for hours - TVs and players that are just off
  don't count), low batteries and updates waiting. Alerts when Home Assistant stops answering, a device drops out
  or a battery runs low, and when each is fine again. Also in the weekly summary and `/metrics`. Read-only, with a
  long-lived access token.

## 0.11.2 - 2026-11-18

### Changed
- **No chat panel or "ask" chips while AI is off** (`intelligence.provider: none`, the default): they only led to
  "No AI assistant set up". They come back as soon as an AI is set up in Setup or atlas.yaml.

### Fixed
- **Smaller database**: routine discovery and plugin events (a copy of the system snapshot every scan, read by
  nothing after the latest) are kept 7 days instead of 90 - on a live install they were over half the database.
- **Ready for newer Python**: `datetime.utcnow()` (deprecated, to be removed) replaced everywhere by one helper
  that returns the same naive-UTC time; the test run went from ~600 warnings to none.
- **Browser tab icon**: pages now carry atlas's globe as their icon (inline), so tabs and bookmarks show it and
  browsers stop asking for a missing `/favicon.ico`.

## 0.11.1 - 2026-11-17

### Added
- **What changed** at the top of Alerts → Activity: the last 24 hours or 7 days in plain words - problems that
  started or cleared, one-off findings, new devices, Proxmox guests added or removed, container limits crossed.

### Fixed
- **Proxmox "changes detected" on every scan**: each scan reported the whole cluster (node and every guest) as
  newly added, because it compared against a saved state other atlas-scan commands overwrite. It now compares
  against the previous Proxmox scan, so Activity shows real changes only.
- **Servers → Overview and the AI check-up often saw an empty picture**: each atlas-scan command saves only its
  own part (the map, the Proxmox scan...), and the newest save was read alone. The newest state now fills each
  missing part from the most recent save that has it (container change detection gets the same fix).
- **Devices: Keep / Ignore no longer reload the page**, so the expanded "Show more" list stays open; the row turns
  into a short note. Buttons that still reload keep open lists and the scroll position.

## 0.11.0 - 2026-11-17

### Added
- **TrueNAS and Synology** (Setup → *TrueNAS or Synology*, or *What's on your network?* → NAS): Home's Storage &
  RAID card shows each pool or volume and every disk's health and temperature. Alerts when a pool isn't healthy,
  and the same disk alerts as Proxmox (failing, hot, worn out). TrueNAS 24.10+ over its websocket API with an API
  key; Synology DSM 7 with an admin account. Read-only. Built from the vendors' API docs and not yet checked
  against real hardware.
- **UniFi names and Wi-Fi details on Devices**: every client UniFi knows is linked to its device by MAC. A name
  you gave it in UniFi becomes atlas's suggested name, and the clue line shows the Wi-Fi network, access point,
  band and signal (and a guest network). Uses the existing UniFi connection.
- **Heartbeats** (Servers → Uptime): a backup or cron job pings its own secret address when it finishes
  (`/fail` when it failed). One alert when it doesn't check in on time or reports a failure, one when it's fine
  again.
- **Quiet hours** (Alerts page, or `notify.quiet_hours`): weekly windows, in your time zone, when no messages go
  out - problems still show on the Alerts page, like a scheduled Pause.
- **DNS check** in internet health: a name is looked up each minute (this machine's resolver, or each of
  `internet.dns_servers` - your router, Pi-hole) and shown under Internet on Servers → Uptime; one alert when
  lookups fail while the internet answers, one when they work again.
- **Prometheus `/metrics`**: uptime, internet, DNS, devices, alerts, disks, UPS, heartbeats and Pi-hole numbers
  for Grafana; read with the existing read-only API token.
- **Weekly summary**: Sunday evening, one message on how the week went (internet, services, new devices, alerts,
  heartbeats, disks, UPS) - which also shows atlas is alive. `notify.weekly_summary: false` turns it off.

## 0.10.0 - 2026-11-17

### Added
- **Internet health** on Servers → Uptime and a Home tile: once a minute atlas times a connection to public DNS
  servers (Cloudflare, Google, Quad9; `internet.targets`) and to your router. One alert when the internet drops
  and one when it's back with how long it lasted; the outage list says whether your router answered (so it was
  the provider) or not. Same graphs, uptime % and 30-day history as the uptime checks; no ping, no extra
  privileges. Turn off with `internet.enabled: false`.
- **Pi-hole and AdGuard Home** (Setup → *Pi-hole or AdGuard Home*, or *What's on your network?*): Home shows
  whether ad blocking is on, how many DNS questions were asked and blocked, and the devices that ask the most,
  named from your device list. One alert when blocking stays off (two checks in a row) and one when it's back.
  Pi-hole 6 (password or app password; atlas signs out after every read) and AdGuard Home (username +
  password). Read-only. Checked against real Pi-hole 6 and AdGuard Home v0.107.
- **Disk health from Proxmox**: every Proxmox scan reads each disk's SMART result, life left, temperature and
  bad-sector count. Home's Storage & RAID card sums them per host and lists any disk with a problem. Alerts when
  a disk fails SMART, runs hot (two scans in a row), is nearly worn out, or gains bad sectors; limits under
  `health.disk_*`. Works with the existing PVEAuditor token.

## 0.9.1 - 2026-11-17

### Fixed
- Atlas's own downloads (the IP-owner table, the IP-location file and the MAC maker list) no longer show up on
  the Security page as a new place this host talks to: after a download, its server is marked known.
- The event log and environment snapshots no longer grow forever: snapshots are kept 7 days and events 90 days
  (the newest of each kind is always kept). The tables get indexes, so Home and Overview stay fast.
- *Sign out* now ends every session, so a copied cookie stops working too.
- Two devices with the same name no longer confuse outage grouping or the device clues' *behind ...* place.
- The tests no longer touch the network (mDNS, UPnP, downloads) and run about 15 seconds faster.

## 0.9.0 - 2026-11-16

A new look (side menu, light and dark, Home and Cabling redesigned), clues that say what each new device is,
uptime checks, UPS power alerts, per-port traffic, one alert per outage, and a Setup tab that asks what you own.

### Added
- **Clues for new devices** on Devices and Triage, so you can tell what an IP address is: the maker from its
  MAC address (the IEEE's public list, downloaded monthly into `inventory/oui.csv`; without internet it is
  just left out), a private (randomised) Wi-Fi address, the name it gives itself, where the cabling map saw
  it (switch port, or behind which access point), what it announces about itself over mDNS/Bonjour and
  UPnP ("Living Room TV - Chromecast", "HP LaserJet M404", AirPlay, printing, HomeKit; `scan.discover`, on by
  default), its open ports and when it first appeared. Atlas fills
  in a suggested name and kind - *Espressif smart device*, *Nintendo game console*, *Phone, tablet or
  laptop* - and Keep saves both; change either before keeping.
- **Alerts page**: every problem atlas's checks find, in one place - *Needs action* (problems, which also send
  alerts), *Watching* (page only, e.g. a switch atlas can't read or devices waiting for a name) and *Resolved in
  the last 7 days*, each with a link to investigate. Covers the LAN watch, host health, certificates, cabling
  (cable health, loops, unreadable switches), open ports, important devices offline and the torrent VPN check.
  Problems resolve by themselves when the check stops seeing them; one-off findings (a new open port) after 7
  days. Home's *Needs attention* includes them.
- **Acknowledge, mute and pause** on the Alerts page. *Acknowledge* marks a problem as seen (it sinks down the
  list and leaves Home; a one-off finding is cleared). *Mute* stops messages about one alert, or about its whole
  device, for a day, a week or always - it stays listed. *Pause alerts* (1 hour to a day) holds every message
  during maintenance and shows a banner; *Resume now* ends it. Muted items are listed with *Unmute*. Every check
  asks before sending; if the alert list can't be read, alerts are sent as before.
- **UPS watch** (Setup → UPS): reads a NUT server - nut-server, or a Synology/QNAP/Unraid/TrueNAS network UPS
  server - once a minute. One alert on a power cut (charge and time left), one when the battery runs low, one when
  power is back (with how long it lasted). Status shows on Servers → Uptime.
- **Setup asks what's on your network.** Tick what you have (managed switch, SNMP router/firewall, NAS, UniFi,
  Proxmox, or just an ISP router) and Setup shows only the matching cards; gear atlas already found is ticked for
  you. Nothing is required - atlas works on any network from its own scan.
- **SNMPv2c** for switches, routers and NAS boxes that don't offer v3: a read-only community, kept with the other
  secrets. The card is now *Switches and routers (SNMP)*.
- **Supported hardware** page in the docs: what works today with which gear, and what's coming next.
- **Uptime checks** (Servers → Uptime). Add a web address or `host:port`; atlas tries it every minute. After two
  failures in a row it alerts once ("Media server is down") and again when it's back, with how long it was down.
  The page shows response time over 24 hours and uptime over 24 hours, 7 days and 30 days, and offers your public
  hostnames as one-click checks. `atlas uptime check` runs one pass; the compose file runs it every minute.
- **Fewer, clearer tabs.** Ten top tabs are now six - *Home, Alerts, Network, Servers, Security, Setup* - each
  with its pages as sub-tabs: Alerts · Activity (was History); Devices · Triage · Coverage · Cabling; Overview ·
  Trends (was Hosts); Exposure (was Posture) · Services (was Network) · Visitors (was Access). Every old address
  still works.
- **Traffic per port.** The cabling scan now reads each port's byte counters and works out its average traffic
  since the last scan. Busy cables show on the map (thick orange over half full, red over 80%, with the rate on the
  label), and the Port map gains a 24-hour graph per port. Kept a week; no extra polling.
- **One alert per outage.** When a switch or AP on the cabling map goes offline, the offline devices behind it fold
  under it - one alert and one message ("core-switch is offline - 12 devices behind it unreachable") instead of one
  per device.
- **Atlas finds switches it could read.** Each port check sends devices the standard SNMPv3 discovery message
  (no user, no password) and reads the LLDP capability flags the mapped switches already collect. Devices that
  look like managed switches or routers are suggested on the Cabling page, on their device page and under
  *Found on your network* on the Setup tab's Switches card (**Use** fills in the form, **Don't ask** hides it).
  `security.snmp_discovery` turns the probe off; `wiring.not_managed` lists dismissed addresses.

### Changed
- The chat panel starts closed on every page (open it from *Chat* in the side menu; atlas remembers).
  Devices, Triage and Coverage show times as *5 min ago*, with the exact time on hover. Makers known by
  another name show that name (Shenzhen Intellirocks shows as Govee).
- Line icons instead of emoji on Devices, Activity, Services, Visitors and Cabling, drawn in the theme's colours.
- **Cabling** opens on the switches' front panels (all expanded), with a *Front panels / Map* switch at the top
  and a one-line summary (switches, cables, what to check). Clicking a port shows a panel beside it: what's
  plugged in, speed, traffic now, PoE, VLANs, bundle or standby, and any cable problem in words. Clicking a
  box on the map jumps to its front panel.
- **Home** opens with one plain sentence (*Everything is healthy*, or how many things need a look), a row of
  numbers - devices online, servers healthy, uptime over 7 days, public routes, power or storage - each
  linking to its page, and a *Needs attention* table with how serious each item is and where to fix it.
- **New look**: a side menu with each section's pages listed under it (no second row of tabs), and a light
  theme by default that follows your system's dark mode. A sun / moon button in the side menu switches it and
  remembers your choice. Every page draws its colours from one set of theme tokens; the exported cabling SVG
  keeps the colours you see.
- Clearer errors from the Setup tab's tests and the cabling scan: a switch that doesn't answer, an unknown
  SNMPv3 user, a wrong passphrase or privacy type, and a Proxmox host that's down or refuses the token are each
  explained in plain words instead of net-snmp's or the HTTP library's raw message.

## 0.8.0 - 2026-11-16

### Added
- **Setup tab** on the web page: connect alerts (ntfy, Discord/Slack/webhooks, email), an AI model, managed
  switches (SNMPv3), a UniFi console and Proxmox without editing files. Every card has a Test button (alerts send
  one test message; the AI check only lists models; switches get one SNMP request; UniFi and Proxmox are signed
  in to and read) and Save / Turn off. Saving a switch, UniFi or Proxmox turns that feature on. Values set in
  `atlas.yaml` or `.env` win and show read-only; passwords and keys are stored privately in the data volume and
  never shown again. No restart needed.
- **Getting started checklist** on the Home page: name your devices, turn on alerts, then (optional) map your
  cabling and connect Proxmox. Each step links to where it's done and ticks off by itself; the list disappears
  once the required steps are done.

### Changed
- No AI model is assumed by default (`intelligence.provider` defaults to `none`, as the installer always
  wrote); `atlas doctor` reports it as off instead of an unknown provider. The installer no longer writes the AI
  section unless you choose one, so it can be set on the Setup tab.
- New description everywhere: atlas is a self-hosted watchdog for your home network (devices, cabling, security,
  alerts), not an "AI operations platform". New banner, docs home page and package description to match.

### Fixed
- The one-line installer (`curl ... | bash`) stopped silently after starting the containers, without printing
  the address and setup code: `docker compose` read the rest of the piped script as its input. Atlas itself was
  running fine. The installer now reads the whole script before running anything.

## 0.7.0 - 2026-11-15

### Added
- **PoE at a glance**: each device's front-panel header on the Cabling page lists the ports that can supply PoE
  and how many are powering something, e.g. `PoE: Port 4 (1 powering, 9.6 W of 30 W)`.
- **Device pages link to the wired map**: a switch, gateway or access point shows its model and a link that opens
  its front panel on the Cabling page; other wired devices link to where they plug in.
- **Spanning tree, link bundles and VLANs** on the cabling map: a spare cable that spanning tree blocks shows as
  standby (a note, not a warning); cables that all carry traffic are flagged as a loop risk and alerted once; LACP
  bundles draw as one labelled bundle; port tooltips show VLANs, with a VLAN picker when there's more than one. The
  switch model shows next to its name. Standard MIBs, plus UniFi's own port data.
- **Certificate watch** (`atlas certs check`, run daily by atlas-scan): alerts 14 and 3 days before a public
  hostname's TLS certificate expires, when a browser would refuse it, and when it's renewed. Days left show next
  to each route on the Posture page's Public exposure tab. Hostnames come from the Traefik routes plus
  `security.cert_hosts`.
- **Cable health** on the cabling map: CRC/alignment errors growing between scans, duplex mismatches, ports
  linking slower than before and flapping links, from SNMP and UniFi port counters. Problems turn the port red
  and send an alert (plus one when it clears).
- **LAN watch** (`atlas lan check`, run by atlas-scan): alerts on a DHCP server other than your router or
  `security.dhcp_servers`, on DHCP going silent, and on the gateway's IP answering from a new MAC (ARP spoofing).
  Shown as the LAN tile on the Posture page. The Docker image adds `atlas-dhcp-python`, an interpreter copy
  with only the permission to listen on UDP port 68.
- **Open-port watch** (`atlas ports check`, run by atlas-scan): alerts once when a LAN device, this host or the
  router opens a new port - common service ports by TCP connect, listening sockets, UniFi port forwards / UPnP
  switch, and UPnP IGD mappings on other routers. The first run only learns. Device pages list open ports; the
  Posture page shows the router's exposure.
- **PoE on the cabling map:** ⚡ on ports powering a device, capable ports outlined, per-device use and budget,
  PoE faults alert, a nearly used budget is shown, and ports starting/stopping PoE appear as changes. Read from
  SNMP (POWER-ETHERNET-MIB) and the UniFi console.
- **Host health alerts** (`atlas sample`): a sensor near its own temperature limit, memory or disks above 90%,
  crashed or restart-looping containers, and status feeds (e.g. a RAID watchdog) reporting a problem - one alert
  when it starts, one when it clears. Limits under `health:`.

### Changed
- **Asleep containers:** a container that stopped cleanly (exit code 0, e.g. a game room put to sleep by an idle
  timer) or has the label `atlas.on-demand=true` is listed as *Asleep* on the home page, not as a problem;
  `/api/summary` adds `containers_asleep`.
- Posture forgets a container's destinations and "expected" marks after `posture.retention_days` without traffic.
- The README shows the cabling map and switch front panels; the long design history moved from the contributor notes
  to [Design notes](docs/development/design-notes.md).

## 0.6.0 - 2026-11-15

### Added
- Alerts beyond Signal: `notify.ntfy`, `notify.webhooks` (Discord, Slack or plain JSON), `notify.email`
  (SMTP) and `notify.apprise` (100+ services; the Docker image includes Apprise). Every set channel gets
  each alert; one failing never blocks the others. `ATLAS_NTFY_TOKEN` / `ATLAS_SMTP_PASSWORD` can stay in `.env`.
- `atlas notify test` sends a test alert and shows which channels got it.
- New README: install, first steps, privacy (no telemetry), FAQ and troubleshooting on one short page.

## 0.5.1 - 2026-11-14

### Fixed
- Docker page and scans failed with "403 Forbidden" behind the socket proxy: the container list
  reads each container's image tags, so the proxy now also allows read-only image lookups
  (`IMAGES: 1`). Upgrade by running the installer again.

## 0.5.0 - 2026-11-14

### Upgrading from 0.4.x - read first
- **atlas now asks for its own admin password** (`web.auth: builtin`, the default). After the
  upgrade the web page shows a setup screen; the one-time code is in `docker compose logs atlas`.
  Already behind Authelia, Authentik or another auth proxy? Add `web: {auth: proxy}` to
  `atlas.yaml` before upgrading and nothing changes.
- **`docker.sock` is no longer mounted into atlas.** The new compose file adds a read-only Docker
  socket proxy. Copy the new `docker-compose.yml` (or re-run the installer). The chat's
  stop/restart/resize actions need `ATLAS_DOCKER_WRITE=1` in `.env`.
- Homepage widgets on `/api/summary` need the API token header (`atlas auth token`) unless you use
  `web.auth: proxy`.

### Added
- **One-line installer** (`install.sh`): checks Docker, asks four questions, writes `~/atlas`,
  starts atlas and sets the admin password. Re-run to upgrade; `--uninstall` to remove.
- **Built-in sign-in**: scrypt-hashed admin password, signed session cookie, per-client rate limit,
  first-run setup code, read-only API token for dashboards, `atlas auth` commands, `/healthz`.
- **Cabling map** (`/cabling`): port-level wired topology from your switches over SNMPv3 (read-only)
  and, optionally, a UniFi console - front-panel port layouts, patch-panel labels, change history,
  CSV/SVG export, Refresh button.
- **Access page**: a world map of who reaches your public services, sign-ins from Authelia,
  Jellyfin, Audiobookshelf and Kavita, learned normal places and new-place review.
- **Network page**: internet / home-only / background lanes plus the device tree.
- **Trends** as charts from atlas's own host history.
- **Torrent VPN watch**: alerts when a qBittorrent behind gluetun is unreachable, disconnected or
  firewalled.
- Home page redesign: what needs attention, storage, security trends, a daily AI check-up, and a
  docked chat panel.

### Changed
- Docker access goes through a read-only socket proxy by default.
- `ATLAS_BIND` in `.env` opens the web page to the LAN (sign-in makes that safe).
- Example configs, tests and docs use neutral example names and addresses.

### Security
- The web page no longer relies on a proxy for authentication by default; JSON writes need a
  signed-in session, not just a same-origin request.
