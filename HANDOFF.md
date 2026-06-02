# AttendancePi — Comprehensive Project Handoff & Documentation

> A face-recognition attendance system built on a Raspberry Pi 5 with a real-time web admin panel, physical LED + buzzer feedback, and cloud-hosted backend for remote access.

---

## Table of Contents

1. [Abstract](#1-abstract)
2. [Problem Statement & Motivation](#2-problem-statement--motivation)
3. [Goals & Scope](#3-goals--scope)
4. [Current Status](#4-current-status)
5. [System Architecture](#5-system-architecture)
6. [Hardware Setup](#6-hardware-setup)
7. [Software Architecture](#7-software-architecture)
8. [Face Recognition Pipeline — Deep Dive](#8-face-recognition-pipeline--deep-dive)
9. [Key Architectural Decisions](#9-key-architectural-decisions)
10. [Tech Stack & Frameworks](#10-tech-stack--frameworks)
11. [Database Schema](#11-database-schema)
12. [WebSocket Protocol Reference](#12-websocket-protocol-reference)
13. [Code Conventions & Style Guide](#13-code-conventions--style-guide)
14. [Bugs Encountered & How They Were Fixed](#14-bugs-encountered--how-they-were-fixed)
15. [Setup & Deployment](#15-setup--deployment)
16. [Known Limitations](#16-known-limitations)
17. [Future Work](#17-future-work)
18. [File Map](#18-file-map)

---

## 1. Abstract

**AttendancePi** is a face-recognition based attendance system designed to replace manual attendance-taking in classrooms or workspaces. A camera mounted at the entrance recognises enrolled members walking in, automatically marks them present, logs the timestamp, and provides instant physical feedback through a blue LED and audio buzzer. Unknown faces trigger a red LED with a warning beep.

The system is fully manageable through a browser-based admin panel hosted either on the Raspberry Pi itself (LAN-only, fully offline) or on Render.com (accessible from anywhere). The admin can enrol students live, monitor attendance in real time, view past records by date, export CSVs, and tune recognition parameters — all from the web interface, no SSH or command-line knowledge required.

The recognition stack uses **YuNet** (OpenCV 2026) for face detection and **SFace** for embedding, with proper landmark-based alignment, a robust top-3 mean matcher, a vote buffer for stability, and a continuous-time temporal tracker to prevent false positives.

---

## 2. Problem Statement & Motivation

### The problem
Manual attendance in classrooms suffers from several issues:
- **Time-consuming** — 5-10 minutes lost at the start of every session
- **Error-prone** — names misheard, proxy attendance ("here for John"), missed marks
- **No real-time visibility** — instructors don't know who's missing until they tally manually
- **Hard to export / aggregate** — paper records or scattered spreadsheets
- **Inflexible** — no way to view attendance trends, latecomers, etc.

### Why face recognition specifically
- **No physical token required** (unlike RFID badges that get forgotten/swapped)
- **Passive** — student just walks in, no action needed
- **Tamper-resistant** when combined with liveness detection (planned)
- **Familiar** — people already use face unlock on phones

### Why Raspberry Pi
- **Cheap** (~₹6000 for Pi 5 + camera + accessories)
- **Self-contained** — fits in a small enclosure at the doorway
- **No PC required** — once configured, it runs headless
- **Powerful enough** for real-time CV (Pi 5's Cortex-A76 cores easily handle YuNet + SFace at 20+ FPS)

---

## 3. Goals & Scope

### Functional requirements
- [x] Detect faces in real time from a Pi camera feed
- [x] Recognise faces against an enrolled database
- [x] Mark attendance with timestamps in a persistent database
- [x] Web-based admin panel for enrolment, monitoring, and review
- [x] Per-day attendance records with CSV export
- [x] Physical LED + buzzer feedback for both success and failure
- [x] Live-tunable recognition settings (no restart required)
- [x] Auto-start on boot via systemd
- [x] Deploy-ready to Render.com (cloud) and Pi-local (LAN) modes

### Non-functional requirements
- [x] **Real-time** — feed latency under 1 second
- [x] **Privacy-respecting** — face embeddings never leave the Pi
- [x] **Resilient** — auto-reconnect on network drop, graceful crash recovery
- [x] **Maintainable** — single config file, modular code structure
- [x] **Documented** — this file + inline comments

### Out of scope (for v1)
- Liveness detection (anti-spoofing with photos)
- Multi-camera support
- Push notifications / email alerts
- Attendance analytics / charts
- Mobile app (browser works fine on mobile)

---

## 4. Current Status

### What works today
| Feature | Status |
|---|---|
| Pi captures live video from Camera Module 3 | ✅ |
| YuNet face detection with landmarks | ✅ |
| SFace face recognition via `alignCrop` | ✅ |
| Pi → server WebSocket streaming (~10 FPS) | ✅ |
| Web dashboard with live feed | ✅ |
| Browser-driven enrolment with progress bar | ✅ |
| Monitor page (live Present/Absent roster) | ✅ |
| Attendance history viewer + CSV export | ✅ |
| Settings page (live tuning of thresholds) | ✅ |
| Reset all data + per-student delete | ✅ |
| Blue LED + beep on marked present | ✅ |
| Red LED + double beep on unknown face | ✅ |
| Buzzer with BC547 transistor driver | ✅ |
| systemd auto-start on Pi boot | ✅ |
| Deployed to Render with PostgreSQL | ✅ |
| Pi-local mode (no internet needed) | ✅ |

### Known issues
- Render free tier disconnects WebSockets under sustained load (~1 min during heavy enrolment) — Pi-local recommended for active enrolment
- No liveness check — a printed photo can spoof the system

---

## 5. System Architecture

### High-level topology

```
                   ┌──────────────────────────────┐
                   │   Render.com Web Service     │
                   │   (FastAPI + PostgreSQL)     │
                   │                              │
                   │   ┌──────────────────────┐   │
                   │   │   ConnectionRelay    │   │
                   │   │   (in-memory)        │   │
                   │   └──────────────────────┘   │
                   └───────▲────────────▲─────────┘
                           │            │
                  WebSocket│            │WebSocket
                  (Pi→Srv) │            │(Srv↔Browser)
                           │            │
   ┌───────────────────────┴─────┐   ┌──┴──────────────────┐
   │  Raspberry Pi 5             │   │  Admin Browser      │
   │  ───────────────            │   │  ─────────────      │
   │  • pi_client.py             │   │  • Dashboard        │
   │  • Camera Module 3          │   │  • Monitor          │
   │  • YuNet + SFace inference  │   │  • Enrol            │
   │  • Local face embeddings    │   │  • Attendance       │
   │  • LEDs + buzzer (GPIO)     │   │  • Settings         │
   └─────────────────────────────┘   └─────────────────────┘
```

### Why this topology?

**The Pi initiates the connection to the server (outbound), not vice versa.**
This is critical. Home/school routers do NAT — the Pi has no public IP, can't accept inbound connections, and configuring port forwarding is fragile. By having the Pi *call out* to the server, it works on any network with no router config.

**The server is a thin relay, not an inference engine.**
All CV (detection, embedding, matching) runs locally on the Pi. The server only stores attendance records and forwards frames + events. This means:
- Bandwidth is low (compressed JPEG frames, not raw video)
- Face embeddings (biometric data) never leave the device
- System keeps working even if the server is briefly unreachable

**Browsers connect to the server, not the Pi directly.**
This way the Pi is invisible to end-users — they only know the web URL. Also lets multiple admins view the dashboard simultaneously.

### Deployment modes

**Mode A — Render (cloud-hosted):**
```
Pi ── Internet ──▶ Render server ◀── Internet ── Admin browser
```
- Pros: Accessible from anywhere, professional `.onrender.com` URL, free tier
- Cons: Needs internet, free tier sleeps after 15 min idle, free tier struggles with sustained WebSocket traffic

**Mode B — Pi-local (LAN-hosted):**
```
                    ┌── Browser (laptop)
Pi (also runs FastAPI server) ──── WiFi ──┼── Browser (phone)
                    └── Browser (tablet)
```
- Pros: No internet needed, no bandwidth limits, smoother for live enrolment
- Cons: Only accessible from the same WiFi network

Switching modes = changing one line in the systemd service file.

---

## 6. Hardware Setup

### Bill of Materials (BOM)

| Component | Quantity | Purpose |
|---|---|---|
| Raspberry Pi 5 (2GB) | 1 | Main compute |
| Raspberry Pi Camera Module 3 (IMX708) | 1 | Video capture |
| 5-inch touchscreen display | 1 | Local visual feedback (optional) |
| Blue LED (5mm) | 1 | Indicates successful attendance mark |
| Red LED (5mm) | 1 | Indicates unrecognised face |
| 220Ω resistor (Red-Red-Brown-Gold) | 2 | Current limiting for LEDs |
| 270Ω resistor (Red-Violet-Brown-Gold) | 1 | Base current for transistor |
| BC547 NPN transistor | 1 | Buzzer current amplifier |
| Active buzzer (5V) | 1 | Audio feedback |
| Breadboard (half-size) | 1 | Wiring |
| Jumper wires (male-to-female) | ~8 | Pi GPIO ↔ breadboard |

### Wiring Diagram

```
Pi GPIO Header                        Breadboard
─────────────                         ──────────

Pin 2  (5V)    ──────────────────▶    Buzzer (+)
                                      Buzzer (−) ──▶ BC547 Collector
Pin 4  (5V)                           BC547 Emitter ──▶ GND rail
                                      BC547 Base   ◀── 270Ω ◀── GPIO 22

Pin 29 (GPIO 5)  ── 220Ω ──▶ Blue LED anode → cathode ──▶ GND rail
Pin 13 (GPIO 27) ── 220Ω ──▶ Red LED anode  → cathode ──▶ GND rail
Pin 15 (GPIO 22) ── 270Ω ──▶ BC547 Base (as above)
Pin 6  (GND)     ──────────────────▶ GND rail
```

### Important hardware notes

**Why GPIO 5 instead of GPIO 17 for the blue LED?**
The 5-inch touchscreen uses GPIO 17 as its `pendown` interrupt line. Attempting to claim GPIO 17 from Python fails with `lgpio.error: 'GPIO busy'`. GPIO 5 is free and equivalent.

**Why a transistor for the buzzer?**
Pi GPIO pins source at most ~16 mA at 3.3 V. Most active 5V buzzers need 30+ mA to be audibly loud. Driving them directly produces a weak click instead of a beep. The BC547 acts as a switch: GPIO controls the base (small current), and the buzzer pulls its current from the Pi's 5V rail through the transistor (large current).

**Why current-limiting resistors?**
A standard red LED has a forward voltage of ~2V. Connecting it directly to 3.3V GPIO creates a near-short — instant LED damage *and* potential permanent damage to the GPIO pin (max rating: 16mA). With 220Ω: I = (3.3 − 2.0) / 220 = ~6mA. Safe and bright enough.

**BC547 pinout (flat side facing you, leads down):**
```
   ┌─────────┐
   │  BC547  │
   │  (flat) │
   └─┬───┬─┬─┘
     │   │ │
     C   B E
```

### Feedback patterns

| Event | LED | Buzzer |
|---|---|---|
| Startup | All off | Silent |
| Student marked present | Blue ON for 3 sec | Single 150 ms beep |
| Unknown face detected | Red flash 3× | Double 80 ms beep |
| Pi disconnected from server | (no LED change) | (silent) |

Each action runs in a short-lived daemon thread so the CV loop never blocks on `time.sleep()` calls.

---

## 7. Software Architecture

### Module structure

```
Pi-side                              Server-side
───────                              ───────────
config.py                            webapp/
pi_client.py (entry)                 ├── main.py (FastAPI entry)
camera/                              ├── database.py (SQLAlchemy)
├── picamera_stream.py               ├── auth.py (cookie sessions)
├── webcam.py                        ├── relay.py (in-memory WS state)
└── threaded.py                      ├── routers/
detection/                           │   ├── pages.py (HTML routes)
└── face_detector.py (YuNet)         │   ├── api.py (REST)
recognition/                         │   └── ws.py (WebSockets)
├── embedder.py (SFace)              └── templates/
└── matcher.py (top-3 mean)              ├── base.html
tracking/                                ├── login.html
└── temporal_tracker.py                  ├── dashboard.html
hardware/                                ├── monitor.html
└── feedback.py (LEDs + buzzer)          ├── enroll.html
attendance_engine.py (CSV writer)        ├── students.html
                                         ├── attendance.html
                                         └── settings.html
```

### Pi client — internal flow

```
┌──────────────────┐
│ ThreadedCamera   │  (background thread)
│ continuously     │
│ reads frames     │
└────────┬─────────┘
         │
         ▼ latest frame
┌──────────────────┐
│ asyncio sender() │
│ ──────────────── │
│ • get frame      │
│ • run CV in      │
│   thread pool    │     ┌──────────────────┐
│ • send JPEG      │────▶│ WebSocket to     │
│ • flush outbox   │     │ server           │
└──────────────────┘     └──────────────────┘
         ▲
         │ commands
┌──────────────────┐
│ asyncio          │
│ receiver()       │     ┌──────────────────┐
│ ──────────────── │◀────│ start_enrollment │
│ • settings       │     │ stop_enrollment  │
│ • commands       │     │ settings_update  │
│ • mode switch    │     │ reset_embeddings │
└──────────────────┘     │ remove_student   │
                         └──────────────────┘
```

### Server — request flow

```
Browser request                         Pi → Server message
───────────────                         ───────────────────
   │                                            │
   ▼                                            ▼
[FastAPI middleware]                    [WebSocket /ws/pi]
   │                                            │
   ▼                                            ▼
[Cookie auth check]                     [Forward "frame" → all browsers]
   │                                    [Save "attendance_marked" → DB]
   ▼                                    [Forward "unknown_face" → browsers]
[Router: pages/api]                     [Save Student on "enrollment_complete"]
   │
   ▼
[SQLAlchemy ORM] ──▶ PostgreSQL (Render) / SQLite (Pi-local)
   │
   ▼
[Jinja2 template] or [JSONResponse]
```

### Why FastAPI?

- Async/await is native — important because the server juggles WebSockets, HTTP, and DB simultaneously
- Built-in WebSocket support with the same router system as HTTP routes
- Automatic request validation via type hints
- Excellent docs and adoption

### Why a single Uvicorn worker?

The `ConnectionRelay` holds the active Pi WebSocket and the set of connected browser sockets in plain Python objects. If we had multiple workers, each would have its own relay state — browsers connected to worker A would never receive frames from worker B's Pi. Single worker is plenty for the load (one Pi, handful of browsers).

---

## 8. Face Recognition Pipeline — Deep Dive

This is the core technical contribution. The pipeline has six stages:

### Stage 1: Capture
- `picamera2` outputs `BGR888` frames at 640×480 directly into a numpy array
- `ThreadedCamera` runs capture in a background thread so the main loop never blocks
- `read()` returns the latest frame instantly

### Stage 2: Detection (YuNet)
- `cv2.FaceDetectorYN` loaded from `face_detection_yunet_2026may.onnx`
- Returns rows of shape `(N, 15)` where each row contains:
  - `[0..3]`: bounding box (x, y, w, h)
  - `[4..13]`: 5 facial landmarks (right eye, left eye, nose tip, right mouth corner, left mouth corner) as (x, y) pairs
  - `[14]`: confidence score
- We return raw rows (not just boxes) so the embedder can use the landmarks

**Why YuNet over the original Caffe SSD ResNet-10?**
- Newer (2023, updated 2026) vs 2017 — better trained on modern face datasets
- ~10× faster on Pi (lightweight CNN architecture)
- Returns landmarks for free — essential for alignment
- Detects faces at angles where the old model would miss them
- Tiny model (~350 KB)

### Stage 3: Alignment + Embedding (SFace)
- `cv2.FaceRecognizerSF` loaded from `face_recognition_sface_2021dec.onnx`
- Two-step process inside `embedder.embed()`:
  1. `recognizer.alignCrop(frame, detection)` — uses YuNet's 5 landmarks to warp the face into a canonical orientation (eyes horizontal, fixed size)
  2. `recognizer.feature(aligned)` — runs SFace forward pass, returns 128-dim embedding
- Embedding is L2-normalised so cosine similarity = dot product

**Why alignment matters (and how we discovered we needed it):**
We initially passed raw bounding-box crops to SFace. Diagnostic showed:
- Cross-person similarity: **0.955** (should be ~0.4)
- Self-similarity: **0.99** (artificially inflated)

The embedder was producing nearly identical vectors for everyone. Switching to `alignCrop` immediately fixed this — SFace was *designed* for aligned faces and was completely confused by unaligned crops.

### Stage 4: Matching (top-3 mean with margin check)
For each enrolled person:
1. Compute cosine similarity between query embedding and ALL of that person's stored samples
2. Sort scores, take the top 3
3. Person's score = mean of those top 3

Then compare across people:
- **Winner** = person with highest mean score
- **Margin check** (when 3+ people enrolled): winner must beat runner-up by ≥ 0.02
- **Threshold check**: winner's score must be ≥ `RECOGNITION_THRESHOLD` (default 0.75)
- If either check fails → return "Unknown"

**Why not just `max()` across all samples?**
This was a real bug we hit. With 30 samples per person, the chance that ONE sample randomly scores high against any face is non-trivial. The result: every newly-enrolled person became the default match for everyone. Top-3 mean filters out fluke matches because three independent samples have to all score high.

**Why the margin check?**
Even with top-3 mean, if two people look similar the scores can be very close. Returning whichever happens to win by a hair would make the system flicker between them. Requiring a clear winner means the system says "Unknown" in ambiguous cases — much better than guessing wrong.

### Stage 5: Vote buffer (stability)
- Keep a `deque(maxlen=10)` of the last 10 frame results
- Only accept a name if it appears in ≥ 7 of the last 10 frames
- A single bad frame can no longer flip the recognition

### Stage 6: Temporal tracker
- A face must be **continuously** visible as the same person for `TEMPORAL_MIN_DURATION` seconds (default 2.0)
- If the recognised name changes mid-window, the timer resets
- After the window completes, the person is marked present (if not already)

**Why "continuous" and not "cumulative"?**
Originally we tracked cumulative time per name. This caused false marks when the system briefly flickered to the wrong person — over 30 seconds of looking around, fragments of "wrong person" time could add up to the threshold. Resetting on identity change forces a clean, sustained recognition.

### Stage 7: Event emission
On successful mark:
- Write to local CSV (`attendance_engine.mark_present()`)
- Push `{"type": "attendance_marked", "name": ..., "time": ...}` to outbox
- Trigger blue LED + buzzer beep (`feedback.marked_present()`)

On unknown face:
- Push `{"type": "unknown_face"}` to outbox (rate-limited to once per 3 seconds)
- Trigger red LED flash + double beep (`feedback.unknown_face()`)

---

## 9. Key Architectural Decisions

Each decision below follows: **Problem → Alternatives → Chosen approach → Trade-offs**.

### Decision 1: Pi connects outward to the server

- **Problem:** The Pi is behind a home/school NAT router with no public IP.
- **Alternatives:**
  - **Port forwarding** — requires router admin access, fragile, breaks when IP changes
  - **VPN tunnel** — extra service to maintain, adds latency
  - **MQTT broker** — overkill for one device
  - **Inverse-direction WebSocket** (chosen)
- **Chosen:** Pi opens a WebSocket *out* to the server, which holds it open and uses it bidirectionally.
- **Trade-offs:** Server must always be reachable for any communication, but this works on any network with zero router configuration.

### Decision 2: Two-tier deployment (Render vs Pi-local)

- **Problem:** Render is great for remote access but has bandwidth and CPU limits. The Pi works great on LAN but isn't reachable from outside.
- **Chosen:** Same codebase, switch via one env var (`SERVER_URL`). Render for cloud, `ws://localhost:8000` for Pi-local.
- **Trade-offs:** Two separate databases (PostgreSQL on Render, SQLite on Pi), but they can be unified by setting `DATABASE_URL` on the Pi to point at Render's PG.

### Decision 3: Recognition runs on the Pi, not the server

- **Problem:** Where should we run the CV pipeline?
- **Alternatives:**
  - **Server-side** — would need to stream raw video continuously (huge bandwidth)
  - **Pi-side** (chosen) — embeddings + small JSON events only
- **Chosen:** Pi handles all CV. Server just stores and relays.
- **Trade-offs:**
  - **Pros:** Low bandwidth, works offline, biometric data stays on device (privacy)
  - **Cons:** Pi needs the models locally (~37 MB)

### Decision 4: Single-worker FastAPI with in-memory relay

- **Problem:** Need to share WebSocket connections between routes.
- **Alternatives:**
  - **Redis pub/sub** — overkill for our load
  - **Single in-memory relay** (chosen)
- **Chosen:** `relay.py` holds the active Pi WS + browser set in a Python object.
- **Trade-offs:** Forces `--workers 1`, but that's plenty for one Pi + a handful of browsers.

### Decision 5: YuNet + SFace via OpenCV's official API

- **Problem:** Initial pipeline used Caffe SSD (2017) + manual SFace blobFromImage. Recognition was unreliable.
- **Chosen:** YuNet 2026 for detection (with landmarks), `FaceRecognizerSF` for embedding (with `alignCrop`).
- **Trade-offs:** Slightly more code, but accuracy went from "broken" to "actually working."

### Decision 6: Top-3 mean matcher + margin check

- **Problem:** Naive max-over-all-samples matcher made every new enrolment dominate.
- **Chosen:** Per-person score = mean of top-3 most-similar samples. Require winner to beat second place by ≥0.02 when there are 3+ people.
- **Trade-offs:** Slightly more conservative (occasional "Unknown" instead of wrong guess), which is the right trade-off for attendance.

### Decision 7: Vote buffer + continuous-time tracker

- **Problem:** Single-frame recognition flickered between people; cumulative-time tracker false-marked from brief glitches.
- **Chosen:** Vote buffer over last 10 frames (7/10 majority); tracker resets when identity changes.
- **Trade-offs:** ~2-second delay before marking, but vastly more reliable.

### Decision 8: Threaded camera capture

- **Problem:** `picamera2.capture_array()` has ~30-50ms latency. Combined with inference, the main loop stalled and dropped frames.
- **Chosen:** `ThreadedCamera` runs capture in a background daemon thread; `read()` returns the latest frame instantly.
- **Trade-offs:** None significant — the standard pattern for real-time CV.

### Decision 9: Live settings tuning via WebSocket

- **Problem:** Tuning the recognition threshold required editing `config.py` and restarting.
- **Chosen:** Settings page in UI → POST → server saves to DB → server pushes `settings_update` over Pi WebSocket → Pi updates live objects.
- **Trade-offs:** Settings live in two places (`config.py` defaults + DB overrides), but DB always wins.

### Decision 10: Hardware feedback as an isolated, optional module

- **Problem:** Code that uses `gpiozero` can't run on a laptop (no GPIO hardware).
- **Chosen:** `hardware/feedback.py` wraps GPIO behind a class with a `HARDWARE_ENABLED` flag. Gracefully no-ops if `gpiozero` is unavailable.
- **Trade-offs:** None — pure win.

### Decision 11: GPIO 5 instead of GPIO 17 for blue LED

- **Problem:** The 5-inch touchscreen claims GPIO 17 (`pendown`). Python crashes with `'GPIO busy'` when trying to use it.
- **Chosen:** Migrated blue LED to GPIO 5.
- **Trade-offs:** None — GPIO 5 is electrically identical.

### Decision 12: BC547 transistor for buzzer drive

- **Problem:** Direct GPIO can't source enough current to drive a 5V active buzzer audibly.
- **Chosen:** NPN transistor switches the 5V rail to the buzzer; GPIO controls the base.
- **Trade-offs:** Extra component (~₹5), but the buzzer is now properly loud.

---

## 10. Tech Stack & Frameworks

### Pi-side stack

| Layer | Technology | Version | Rationale |
|---|---|---|---|
| OS | Raspberry Pi OS (64-bit) | Bookworm | Official Pi OS, supports Pi 5 |
| Language | Python | 3.13 | Pre-installed on Pi OS |
| Camera | `picamera2` | 0.3+ | Native Pi 5 camera API; BGR888 format |
| CV framework | `opencv-contrib-python` | 4.13+ | Includes `FaceDetectorYN` and `FaceRecognizerSF` |
| Numerics | `numpy` | 2.x | Standard |
| Detection model | YuNet | 2026May | Latest from opencv_zoo |
| Recognition model | SFace | 2021Dec | Compact (~37 MB), optimised for edge |
| WebSocket | `websockets` | 16.x | Standard asyncio WS client |
| GPIO | `gpiozero` | (built-in) | Cleanest Pi GPIO API |
| Process supervision | systemd | (built-in) | Auto-start, auto-restart, log integration |

### Server-side stack

| Layer | Technology | Rationale |
|---|---|---|
| Web framework | FastAPI | Async + WebSocket native, type-safe |
| ASGI server | Uvicorn | FastAPI's standard runtime |
| ORM | SQLAlchemy 2.x | Mature, supports both Postgres and SQLite |
| Database (cloud) | PostgreSQL | Render's managed free tier |
| Database (local) | SQLite | Zero-config, file-based |
| Templating | Jinja2 | Built into FastAPI's response system |
| Auth | Custom cookie sessions | Single admin user — no need for OAuth/JWT |

### Frontend stack

| Layer | Technology | Rationale |
|---|---|---|
| Markup | Jinja2 templates | Server-rendered HTML |
| Styling | Tailwind CSS (CDN) | Fast utility-first styling, no build step |
| Interactivity | Vanilla JavaScript | No framework needed for our small JS surface area |
| Real-time | Native WebSocket API | Same channel for camera feed + events |

### Deployment

| Item | Tool |
|---|---|
| Source control | Git + GitHub |
| Cloud hosting | Render.com (web service + free PostgreSQL) |
| Reproducible setup | `render.yaml` blueprint, `Procfile` |
| Uptime monitoring | UptimeRobot (free) — pings every 5 min to prevent free-tier spin-down |

---

## 11. Database Schema

Two tables (plus settings KV store):

### `students`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-incrementing |
| `name` | STRING UNIQUE NOT NULL | Display name; matches embeddings dict key on Pi |
| `created_at` | DATETIME | Auto-set on insert |

### `attendance_records`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-incrementing |
| `student_id` | INTEGER FK → students.id | ON DELETE CASCADE |
| `date` | DATE NOT NULL | Indexed for fast "today" queries |
| `time_marked` | STRING NOT NULL | "HH:MM:SS" |

### `settings`

| Column | Type | Notes |
|---|---|---|
| `key` | STRING PK | e.g. `recognition_threshold` |
| `value` | STRING NOT NULL | Stored as string, parsed on read |

The `Setting` table is a simple key-value store. `database.py` provides `get_settings()` (with defaults from `config.py`) and `save_setting()` helpers. Settings changes are pushed to the Pi over WebSocket the moment they're saved.

**Important conventions:**
- Records are converted to plain dicts before being passed to templates — prevents SQLAlchemy `DetachedInstanceError` after `db.close()`
- Sessions are wrapped in try/finally via the `get_db()` dependency
- One attendance record per student per date (enforced by a check before insert)

---

## 12. WebSocket Protocol Reference

All messages are JSON with a `type` field.

### Pi → Server messages

| Type | Payload | Server action |
|---|---|---|
| `frame` | `{ data: <base64 JPEG> }` | Forward to all browsers |
| `attendance_marked` | `{ name, time }` | Save to DB, broadcast to browsers |
| `unknown_face` | `{}` | Broadcast to browsers |
| `sample_captured` | `{ count, total }` | Broadcast to browsers (for progress bar) |
| `enrollment_complete` | `{ name }` | Add Student to DB if new, broadcast |

### Server → Pi messages

| Type | Payload | Pi action |
|---|---|---|
| `start_enrollment` | `{ name, samples }` | Switch to enrollment mode |
| `stop_enrollment` | `{}` | Cancel enrolment, return to normal |
| `settings_update` | `{ settings: {...} }` | Update live matcher/tracker params |
| `reset_embeddings` | `{}` | Wipe `known_embeddings.npy`, clear matcher |
| `remove_student` | `{ name }` | Remove from embeddings dict |

### Server → Browser messages (broadcast)

| Type | Payload | Browser action |
|---|---|---|
| `frame` | `{ data: <base64 JPEG> }` | Render to canvas |
| `pi_status` | `{ connected: bool }` | Update connection indicator |
| `attendance_marked` | `{ name, time }` | Update roster, show banner |
| `unknown_face` | `{}` | Flash red "Face Not Matched" banner |
| `sample_captured` | `{ count, total }` | Update progress bar |
| `enrollment_complete` | `{ name }` | Show success message |

### Browser → Server messages

| Type | Payload | Server action |
|---|---|---|
| `start_enrollment` | `{ name, samples }` | Forward to Pi |
| `stop_enrollment` | `{}` | Forward to Pi |

---

## 13. Code Conventions & Style Guide

### Python conventions

- **PEP 8 with slight personal flair** — vertical alignment on related assignments (multiple `self.x = ...` lines aligned on `=`)
- **Section dividers** in larger files: `# ── Section Name ──...` (em-dash style)
- **Imports grouped** with blank lines: stdlib, third-party, local
- **No emojis** in code or generated files unless explicitly requested
- **Comments explain "why" not "what"** — code shows the what
- **`if __name__ == "__main__"`** at the bottom of every entry-point script
- **Fail loudly with `print()`** when running under systemd — needed for `journalctl` debugging
- **`try/except` around external calls** (alignCrop, network, GPIO) but always log the exception text

### File organisation conventions

- **One concern per module** — `camera/` only deals with cameras, `recognition/` only with face matching
- **Single `config.py` at project root** holds all tunable constants
- **Paths in `config.py` are absolute** — resolved from `config.py`'s own location via `BASE_DIR = os.path.dirname(os.path.abspath(__file__))`. Lets scripts run from any working directory.
- **Settings live in DB if user-tunable**; in `config.py` if developer-only

### UI conventions (Tailwind classes)

- **Dark theme**: `bg-gray-950` (page), `bg-gray-900` (panels)
- **Green accents** for positive actions: `bg-green-700`, `text-green-400`
- **Red accents** for danger/disconnect: `bg-red-800`, `text-red-400`
- **Yellow/amber** for warnings or "in progress": `text-yellow-400`
- **Rounded corners**: `rounded-xl` for panels, `rounded-lg` for buttons
- **Subtle borders** instead of heavy shadows: `border border-gray-800`
- **Compact spacing** in dense layouts (tables, monitor lists): `py-1.5`, `py-2`

### Git conventions

- **Commit messages**: imperative mood, present tense ("Fix X" not "Fixed X")
- **No `git add .` from outside the project root** — easy way to commit accidental junk
- **Never skip hooks** (`--no-verify`) without explicit reason
- **`.gitignore`** covers venv, pycache, attendance_logs/, attendance.db, known_embeddings.npy

### Things explicitly avoided

- No threading inside FastAPI handlers (asyncio only)
- No file-based shared state between Pi and server (use DB or WebSocket)
- No biometric data in DB or git (only `known_embeddings.npy` on the Pi, gitignored)
- No emojis in code unless asked
- No premature optimisation
- No frameworks for the frontend (vanilla JS is enough)

---

## 14. Bugs Encountered & How They Were Fixed

Documenting these because they're educational and likely to recur.

### Bug 1: Enrolment crops included the green detection rectangle
- **Symptom:** All embeddings nearly identical (cross-similarity ≈ 0.95). Every face matched everyone.
- **Cause:** `cv2.rectangle()` was called *before* `frame[y1:y2, x1:x2]` was taken. The crop included the green border pixels — the same green pixels in every capture acted as a constant feature.
- **Fix:** Crop *first* from the clean frame, then draw the rectangle for display.

### Bug 2: Matcher always returned the newest enrolled person
- **Symptom:** Whoever was enrolled most recently became the default match for everyone.
- **Cause:** `max()` over all stored samples. With 30 samples per person, there was always at least one fluke sample for the new person that scored high.
- **Fix:** Score each person by mean of top-3 most-similar samples; require a margin between best and second-best.

### Bug 3: SFace embeddings were nearly identical regardless of face
- **Symptom:** Self-sim 0.99, cross-sim 0.95 — should be 0.85+ and 0.4 respectively.
- **Cause:** Feeding tight bounding-box crops to SFace. SFace was trained on *aligned* faces using specific landmark positions.
- **Fix:** Use `cv2.FaceRecognizerSF.alignCrop(frame, detection)` which uses YuNet's landmarks to properly align the face before embedding.

### Bug 4: Pi appeared "disconnected" in UI even while sending frames
- **Symptom:** Dashboard shows red dot, but camera feed visible.
- **Cause:** Stale WebSocket reference. When Pi reconnected, server still held the dead old socket; old socket's disconnect handler ran later and reset `relay.pi = None`.
- **Fix:** Only clear `relay.pi` if it's the *same* socket as the one disconnecting (`if relay.pi is ws`).

### Bug 5: GPIO 17 (`pendown`) busy
- **Symptom:** `lgpio.error: 'GPIO busy'` on startup.
- **Cause:** 5-inch touchscreen reserves GPIO 17 for its pen-down interrupt.
- **Fix:** Moved blue LED to GPIO 5. Identified via `sudo cat /sys/kernel/debug/gpio | grep GPIO17`.

### Bug 6: Buzzer too quiet
- **Symptom:** Buzzer barely audible despite being wired correctly.
- **Cause:** Pi GPIO sources only ~16mA at 3.3V; active buzzers need 30+ mA at 5V.
- **Fix:** BC547 transistor as a switch. GPIO controls base; buzzer pulls current from 5V rail through transistor.

### Bug 7: Database lazy-load error after session closed
- **Symptom:** `DetachedInstanceError: Parent instance is not bound to a Session`.
- **Cause:** Passing SQLAlchemy ORM objects to Jinja2 templates; template accessed `record.student.name` after `db.close()`.
- **Fix:** Convert to plain dicts inside the route function, while session is still open.

### Bug 8: Tab/space mix in original `run_attendance.py`
- **Symptom:** `TabError` on import.
- **Cause:** Mixed indentation across lines in the same function.
- **Fix:** Normalised to spaces throughout the project.

### Bug 9: Webcam returned black frames despite light being on
- **Symptom:** Camera opens, lights up, but feed is the Windows "camera blocked" placeholder.
- **Cause:** Windows privacy setting at the OS level was blocking desktop apps from camera access.
- **Fix:** Settings → Privacy & Security → Camera → enabled both top-level and "desktop apps" toggles.

### Bug 10: Render WebSocket disconnects every ~60 seconds during enrolment
- **Symptom:** Pi reconnects in a loop on Render but not on Pi-local.
- **Cause:** Render free tier has CPU and bandwidth limits. Heavy JPEG streaming + enrolment inference made the Pi miss WebSocket pings, Render killed the connection.
- **Partial fix:** Skip more frames (every 6th instead of 3rd), lower JPEG quality (40 → 25), bump `ping_interval=60, ping_timeout=120`.
- **Real fix:** Use Pi-local mode for active enrolment.

### Bug 11: `nonlocal matcher` declared after first use
- **Symptom:** `SyntaxError: name 'matcher' is used prior to nonlocal declaration`.
- **Cause:** `nonlocal` must come at the top of the function, before any reference to the variable.
- **Fix:** Moved `nonlocal matcher` to top of `sender()` and `receiver()`.

### Bug 12: Camera "freeze" was just slow inference, not a real freeze
- **Symptom:** Browser feed stutters every few seconds.
- **Cause:** Inference was running synchronously in the asyncio loop.
- **Fix:** Used `loop.run_in_executor(None, process_frame, ...)` so heavy CV runs in a thread pool.

---

## 15. Setup & Deployment

### One-time Pi setup

1. **Install Raspberry Pi OS 64-bit Bookworm** via Pi Imager.
2. **Enable SSH and set username** in Pi Imager's advanced options.
3. **Plug in Camera Module 3** to the Pi's CSI port.
4. **Boot the Pi** and SSH in: `ssh sarthak@<pi-ip>`
5. **Update**: `sudo apt update && sudo apt upgrade -y`
6. **Clone the repo**: `git clone https://github.com/<you>/attendancepi.git ~/attendancepi_v2`
7. **Create venv with system packages**:
   ```bash
   cd ~/attendancepi_v2
   python3 -m venv venv --system-site-packages
   source venv/bin/activate
   pip install -r requirements_pi.txt
   ```
8. **Edit `config.py`** — set `CAMERA_SOURCE = "picamera"`
9. **Wire the breadboard** as in section 6.
10. **Create systemd services** (see below)
11. **Enable + start both services**:
    ```bash
    sudo systemctl enable attendancepi-web attendancepi
    sudo systemctl start attendancepi-web
    sleep 3
    sudo systemctl start attendancepi
    ```

### systemd service files

`/etc/systemd/system/attendancepi-web.service` (only for Pi-local mode):
```ini
[Unit]
Description=AttendancePi Web Server
After=network.target

[Service]
Type=simple
User=sarthak
WorkingDirectory=/home/sarthak/attendancepi_v2
ExecStart=/home/sarthak/attendancepi_v2/venv/bin/python -m uvicorn webapp.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/attendancepi.service`:
```ini
[Unit]
Description=AttendancePi Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sarthak
WorkingDirectory=/home/sarthak/attendancepi_v2
Environment=SERVER_URL=ws://localhost:8000      # or wss://yourapp.onrender.com
Environment=PI_SECRET=pisecret123
ExecStart=/home/sarthak/attendancepi_v2/venv/bin/python -u pi_client.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Render deployment

1. Push the repo to GitHub.
2. On Render: **New → Web Service**, connect the repo.
3. Build Command: `pip install -r requirements_webapp.txt`
4. Start Command: `uvicorn webapp.main:app --host 0.0.0.0 --port $PORT --workers 1`
5. Add environment variables: `ADMIN_PASSWORD`, `PI_SECRET`.
6. Create a **free PostgreSQL** instance, copy Internal Database URL, paste as `DATABASE_URL` env var.
7. Deploy.
8. Set up UptimeRobot to ping the URL every 5 min (keeps free tier warm).

### Running for the first time

1. Open `http://raspberrypi.local:8000` (Pi-local) or `https://yourapp.onrender.com` (Render).
2. Log in with `ADMIN_PASSWORD`.
3. Go to **Enrol** page, type student name, click Start Enrolment.
4. Stand in front of the camera. Move slightly between samples.
5. After all samples captured, view **Students** to confirm.
6. Walk in front of the camera — should be marked Present.
7. Listen/look for blue LED + beep.

### Daily operation

1. Power on Pi. systemd starts everything automatically.
2. Open the URL on phone/laptop.
3. Monitor page shows live attendance.
4. End of day: go to Attendance → Export CSV.

---

## 16. Known Limitations

| Limitation | Mitigation |
|---|---|
| No liveness detection — photo spoofable | Planned (blink via landmarks or MiniFASNet) |
| Render free tier sleeps after 15 min | UptimeRobot keeps it warm |
| Render free tier WebSocket disconnects under load | Use Pi-local for active enrolment |
| One person at a time in frame | By design — multi-face handling planned |
| Threshold tuning is manual | UI sliders make it easy |
| No mobile-optimised view | Templates are responsive (Tailwind), works fine on mobile browsers |
| Pi-local and Render databases are separate | Set `DATABASE_URL` on Pi to point to Render PG for unified DB |
| Recognition needs good lighting | Inherent to the model |

---

## 17. Future Work

### Short-term polish
- Liveness detection via blink (YuNet landmarks)
- Manual override per student (mark present without camera)
- "Recent arrivals" feed on the dashboard with photo thumbnails
- Bulk enrol from a folder of student photos
- Per-student dashboard (their attendance history)

### Medium-term features
- Email/SMS notifications when specific students arrive (parents/teachers)
- Class/section grouping (separate rosters per class)
- Attendance percentage charts per student
- Late detection ("on-time" vs "late" boundary)
- Multi-camera support (multiple Pis to one server)

### Advanced
- On-device anti-spoofing with MiniFASNet
- Recognition retraining UI ("this person was misidentified")
- Federated enrolment across multiple Pis sharing one server
- Local TLS for the Pi web server (currently HTTP)
- ARM-optimised inference with quantised models

---

## 18. File Map

```
attendancepi_v2/
│
├── camera/
│   ├── __init__.py
│   ├── picamera_stream.py   — Raspberry Pi camera (BGR888)
│   ├── webcam.py            — Laptop webcam (cv2.VideoCapture + CAP_DSHOW)
│   └── threaded.py          — Background-thread wrapper for either source
│
├── detection/
│   ├── __init__.py
│   └── face_detector.py     — YuNet wrapper, returns raw detections + landmarks
│
├── recognition/
│   ├── __init__.py
│   ├── embedder.py          — SFace via FaceRecognizerSF (uses alignCrop)
│   └── matcher.py           — Top-3 mean + margin check
│
├── tracking/
│   ├── __init__.py
│   └── temporal_tracker.py  — Continuous-time presence gating
│
├── hardware/
│   ├── __init__.py
│   └── feedback.py          — LEDs + buzzer via gpiozero (no-op on laptop)
│
├── webapp/
│   ├── __init__.py
│   ├── main.py              — FastAPI app entry
│   ├── database.py          — SQLAlchemy models + settings helpers
│   ├── auth.py              — Cookie session auth
│   ├── relay.py             — Pi/browser WebSocket connection registry
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── pages.py         — HTML page routes
│   │   ├── api.py           — REST endpoints (delete, export, settings, reset)
│   │   └── ws.py            — /ws/pi and /ws/browser handlers
│   │
│   └── templates/
│       ├── base.html        — Layout + navbar
│       ├── login.html       — Password form
│       ├── dashboard.html   — Live feed + stats + recent arrivals
│       ├── monitor.html     — Roster with Present/Absent + "Face Not Matched"
│       ├── enroll.html      — Browser-driven enrolment
│       ├── students.html    — List + delete
│       ├── attendance.html  — Date-filtered records + CSV export
│       └── settings.html    — Live-tuning sliders + reset button
│
├── models/
│   ├── face_detection_yunet_2026may.onnx
│   └── recognition/face_recognition_sface_2021dec.onnx
│
├── attendance_logs/         — Local CSV output (gitignored)
│
├── config.py                — All defaults + path resolution
├── pi_client.py             — Pi-side entry point
├── attendance_engine.py     — CSV writer
│
├── requirements_pi.txt      — Pi dependencies
├── requirements_webapp.txt  — Server dependencies
├── render.yaml              — Render blueprint
├── Procfile                 — Render startup command
├── .gitignore
│
├── README.md                — Quick overview
└── HANDOFF.md               — This document
```

---

## Acknowledgements & Credits

- **YuNet** face detector — Wei Wu et al., released via [opencv_zoo](https://github.com/opencv/opencv_zoo)
- **SFace** face recognition — Yaoyao Zhong et al.
- **OpenCV** computer vision library
- **FastAPI** web framework
- **Render** for free-tier hosting

---

*Document version: 1.0 · Last updated: June 2026*
