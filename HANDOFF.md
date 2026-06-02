# AttendancePi — Handoff Document

A face-recognition attendance system that runs on a Raspberry Pi 5, streams its camera feed to a FastAPI web app (hosted on Render.com or self-hosted on the Pi itself), and lets an admin enrol students, monitor live attendance, and export records from any browser.

---

## 1. Project Goals & Current Status

### Original goal
Replace manual classroom attendance with an automated camera-based system. A camera at the doorway recognises students walking in, marks them present, logs the time, and exposes everything through a clean web admin panel.

### Current status — working end-to-end
- Pi captures video, detects faces, recognises enrolled students locally
- Pi streams compressed JPEG frames + events to the web server via WebSocket
- Web server (FastAPI) relays frames to browser clients in real time
- Admin can enrol students through the browser (no SSH/CLI needed)
- Monitor page shows full student roster as Present/Absent in real time
- Attendance is saved to PostgreSQL (Render) or SQLite (local Pi)
- CSV export by date works
- Live settings tuning (recognition threshold, sample count, etc.) without restart
- Reset All Data + per-student delete propagate to the Pi
- Deployed to Render at `https://attendancepi-7wgk.onrender.com`
- Also runs fully Pi-local at `http://raspberrypi.local:8000` (no internet needed)
- `systemd` services auto-start both the Pi client and (when self-hosted) the web server on boot
- **Physical hardware feedback** — blue LED + beep on successful mark, red LED + double beep on unknown face

### Known limitations
- Render free tier spins down after 15 min idle (use UptimeRobot to keep warm)
- Render free tier WebSockets struggle under live-enrolment CPU spikes — for active enrolment, Pi-local mode is smoother
- Recognition accuracy depends heavily on enrolment variety — capture samples from different angles/lighting
- No liveness detection — a printed photo could still spoof the system (planned, not built)
- Local SQLite on Pi and Render PostgreSQL are separate databases unless `DATABASE_URL` env var on Pi points to Render's PG

---

## 2. Key Architectural Decisions

### Pi connects outward to the server, not the other way around
The Pi is behind a home/school router with no public IP. Instead of port-forwarding, the Pi opens a WebSocket *out* to the server. The server then relays frames and commands. This is the standard IoT pattern and means zero firewall configuration on the Pi side.

### Two-tier deployment: Pi-local OR Render
The same `pi_client.py` works against either:
- `ws://localhost:8000` — Pi runs the webapp itself, accessible on LAN. Smooth, no internet needed.
- `wss://attendancepi-XXXX.onrender.com` — accessible from anywhere, but free tier has bandwidth/CPU limits.

Switching modes is one line in the systemd service file. We chose this split because Render is great for remote access but bad for real-time live video; the Pi handles real-time better but isn't reachable from outside the network.

### Single-worker FastAPI with in-memory relay state
`relay.py` keeps the active Pi WebSocket + set of browser sockets in memory. This requires `--workers 1` (multiple workers wouldn't share the connection state). We accepted this constraint because:
- Only one Pi connects per server
- A handful of browser clients max
- Single worker is plenty for this load

### Recognition runs on the Pi, not the server
The Pi has plenty of CPU for SFace inference. Doing it locally:
- Avoids streaming full-resolution video to the server
- Works even when the server is unreachable
- Keeps biometric face embeddings on-device (privacy)

The server only sees: detected name + confidence + timestamp.

### Face embeddings stay on Pi, attendance records go to DB
`known_embeddings.npy` is biometric data — never leaves the Pi. The database only stores student names + attendance timestamps. This separation means a server breach doesn't expose face data.

### YuNet for detection + SFace with `alignCrop()` for recognition
Initially used Caffe SSD ResNet-10 (2017) and SFace with manually-cropped tight boxes. Switched to:
- **YuNet** (2026 May version) — newer, faster, returns 5 facial landmarks
- **SFace via `FaceRecognizerSF`** — uses YuNet's landmarks for proper alignment

This was a huge accuracy win — cross-person similarity dropped from ~0.95 (broken) to a clean range, because SFace was *designed* for aligned faces and was getting unaligned crops before.

### Top-3 mean + margin check matcher
A naive "best of all stored samples" matcher had a critical bug: each new enrolment (30 samples) increases the chance of one fluke high-scoring sample, so the *latest* enrolled person became the default match for everyone. We fixed this by:
- Score each person by mean of their top-3 most-similar samples
- Require the winner to beat the runner-up by ≥0.02 (only when 3+ people enrolled)

### Vote buffer for stability
On top of the matcher, we keep a deque of the last 10 frame results. Only accept a name if it appears in ≥7 of them. A single bad frame can no longer flip the recognition.

### Continuous-time temporal tracker
A face must be *continuously* visible as the same person for N seconds before being marked. Switching identity mid-window resets the timer. Prevents false marking from fragmented detections.

### Threaded camera capture
`ThreadedCamera` runs camera I/O in a background daemon thread. `read()` always returns the latest frame instantly — main thread never blocks on the camera even while inference runs. Especially important on Pi where `picamera2.capture_array()` has measurable latency.

### Live settings updates over the same WebSocket
When you save settings in the UI, the server pushes the new values to the Pi over the existing WebSocket. The Pi updates the matcher threshold, tracker duration, etc. live — no restart, no reconnect.

### Hardware feedback module is optional and isolated
`hardware/feedback.py` wraps GPIO control behind a small class. If `gpiozero` isn't available (laptop testing) or `HARDWARE_ENABLED = False`, every method becomes a no-op. Each LED/buzzer action spawns a short-lived daemon thread so the CV loop is never blocked by `time.sleep()` calls during a beep or flash sequence.

### Same router file structure for pages + API + WebSockets
`webapp/routers/pages.py` for HTML pages, `api.py` for JSON endpoints, `ws.py` for WebSockets. Clean separation, easy to find things.

---

## 3. Tech Stack

### Pi-side (`pi_client.py` + modules)
| Component | Choice | Why |
|---|---|---|
| OS | Raspberry Pi OS (64-bit) | Default for Pi 5 |
| Python | 3.13 | Comes with Pi OS |
| Camera | `picamera2` (BGR888) | Native Pi 5 camera API; outputs BGR directly |
| Detection | OpenCV `FaceDetectorYN` (YuNet 2026May) | Modern, lightweight, returns landmarks |
| Recognition | OpenCV `FaceRecognizerSF` (SFace) | Optimised for edge, official OpenCV API |
| Async WebSocket | `websockets` library | Standard for Python asyncio WS clients |
| Process supervision | `systemd` services | Auto-start on boot, restart on crash |
| GPIO control | `gpiozero` (pre-installed on Pi OS) | Cleanest Pi GPIO API |

### Server-side (`webapp/`)
| Component | Choice | Why |
|---|---|---|
| Web framework | FastAPI | Async + WebSocket support out of the box |
| ASGI server | Uvicorn (single worker) | Required for in-memory relay state |
| ORM | SQLAlchemy 2.x | Familiar, plays well with Postgres and SQLite |
| Database | PostgreSQL (Render) or SQLite (local) | Render's free PG for cloud, SQLite for Pi-local |
| Templating | Jinja2 | Standard for FastAPI |
| Auth | Cookie-based session (custom, in-memory) | Single admin user, no need for OAuth/JWT overhead |

### Frontend (`webapp/templates/`)
| Choice | Why |
|---|---|
| Plain HTML + Jinja2 templates | No build step, easy to edit |
| Tailwind CSS (CDN) | Quick utility-first styling |
| Vanilla JavaScript | No framework needed for the small amount of interactivity |
| WebSockets for live updates | Same channel for camera feed + events |

### Deployment
| Choice | Why |
|---|---|
| Render.com web service + free PostgreSQL | Free tier, auto-deploy from GitHub |
| `render.yaml` blueprint | Reproducible setup |
| GitHub for source control | Standard; Render auto-redeploys on push |

---

## 4. Custom Rules & Styling Preferences

### Code style
- **Vertical alignment of assignments** for related variables (e.g. multiple `self.x = ...` lines aligned on `=`)
- **No emojis** in code or generated files unless explicitly asked
- **Comments explain "why" not "what"** — code shows the what
- **Section dividers** in larger files: `# ── Section Name ──...` (em-dash style)
- **Imports grouped**: stdlib, then third-party, then local — separated by blank lines
- **`if __name__ == "__main__"`** at the bottom of every entry-point script
- **Snake_case for Python, kebab/camelCase for HTML/JS as conventional**

### Color/UI choices in templates
- Dark theme everywhere (`bg-gray-950`, `bg-gray-900` panels)
- Green accents for positive actions (`bg-green-700`, `text-green-400`) — present, save, enroll
- Red accents for danger/disconnect (`bg-red-800`, `text-red-400`) — remove, reset, errors
- Yellow/amber for warnings or "in progress" (`text-yellow-400`)
- Rounded corners (`rounded-xl` for panels, `rounded-lg` for buttons)
- Subtle borders (`border border-gray-800`) instead of heavy shadows

### Configuration patterns
- **Single `config.py`** at the project root holds *all* tunable constants
- **Paths in config are absolute**, resolved from `config.py`'s own location with `BASE_DIR = os.path.dirname(os.path.abspath(__file__))`. Lets scripts run from any working directory.
- **Settings the user might change live** are in the database via the `Setting` model, not in `config.py`. `config.py` provides defaults; DB overrides them; UI changes update DB and push to Pi.

### Error handling preferences
- **Fail loudly with `print()`** for Pi-side errors when running under systemd — needed for `journalctl -u attendancepi -f` debugging
- **`try/except` around external calls** (alignCrop, network) but always log the exception text — never silently swallow
- **Graceful shutdown** via `signal.signal(SIGINT/SIGTERM, ...)` — guarantees CSV save and clean WebSocket close

### WebSocket conventions
- All messages are JSON with a `type` field: `frame`, `attendance_marked`, `pi_status`, `unknown_face`, `start_enrollment`, `stop_enrollment`, `settings_update`, `enrollment_complete`, `sample_captured`, `reset_embeddings`, `remove_student`
- Server → Pi events are commands; Pi → server events are data
- Server → browser events include both relayed Pi data and server-generated status

### Database conventions
- **Convert ORM objects to plain dicts** before passing to templates — prevents `DetachedInstanceError` after the session closes
- **Always wrap session in `try/finally`** via the `get_db()` dependency

### Things explicitly avoided
- No threading inside FastAPI handlers (asyncio only)
- No file-based state for things that need to be shared between Pi and server (use DB or WebSocket events)
- No biometric data in the database or git (only `known_embeddings.npy` on the Pi, gitignored)
- No `git add .` from outside the project root — easy way to commit junk
- No skipping git hooks (`--no-verify`) without reason
- No emojis in code unless the user asked

---

## Hardware Wiring

```
Pi 5V (pin 2)   ──────────────── Buzzer (+)
Buzzer (−)      ──────────────── BC547 Collector
BC547 Emitter   ──────────────── GND rail
GPIO 22         ── 270Ω ──────── BC547 Base

GPIO 5          ── 220Ω ──────── Blue LED anode  → cathode → GND rail
GPIO 27         ── 220Ω ──────── Red LED anode   → cathode → GND rail
```

- **GPIO 17 cannot be used** — it's reserved by the 5-inch touchscreen (`pendown`)
- **Buzzer needs the BC547 transistor** because GPIO can't source enough current. The 5V rail powers the buzzer; GPIO 22 just switches the transistor on/off.
- All cathodes and the transistor emitter share the same breadboard GND rail wired back to a Pi GND pin.

## File Map

```
attendancepi_v2/
├── camera/
│   ├── picamera_stream.py   — Raspberry Pi camera (BGR888)
│   ├── webcam.py            — Laptop webcam (cv2.VideoCapture + CAP_DSHOW)
│   └── threaded.py          — Background-thread wrapper for either source
├── detection/
│   └── face_detector.py     — YuNet wrapper, returns raw detections with landmarks
├── recognition/
│   ├── embedder.py          — SFace via FaceRecognizerSF (uses alignCrop)
│   └── matcher.py           — Top-3 mean + margin check
├── tracking/
│   └── temporal_tracker.py  — "N seconds continuous" gating
├── hardware/
│   └── feedback.py          — LEDs + buzzer via gpiozero (no-op on laptop)
├── webapp/
│   ├── main.py              — FastAPI app entry
│   ├── database.py          — SQLAlchemy models + settings helpers
│   ├── auth.py              — Cookie session auth
│   ├── relay.py             — Pi/browser WebSocket connection registry
│   ├── routers/
│   │   ├── pages.py         — HTML page routes
│   │   ├── api.py           — REST endpoints (delete, export, settings, reset)
│   │   └── ws.py            — /ws/pi and /ws/browser handlers
│   └── templates/
│       ├── base.html        — Layout + navbar
│       ├── login.html
│       ├── dashboard.html   — Live feed + stats + recent arrivals
│       ├── monitor.html     — Roster with Present/Absent + "Face Not Matched" banner
│       ├── enroll.html      — Browser-driven enrolment
│       ├── students.html    — List + remove
│       ├── attendance.html  — Date-filtered records + CSV export
│       └── settings.html    — Live-tuning sliders + reset button
├── models/
│   ├── face_detection_yunet_2026may.onnx
│   └── recognition/face_recognition_sface_2021dec.onnx
├── attendance_logs/         — Local CSV output (gitignored)
├── config.py                — All defaults + path resolution
├── pi_client.py             — Pi-side entry point
├── attendance_engine.py     — CSV writer
├── requirements_pi.txt
├── requirements_webapp.txt
├── render.yaml              — Render blueprint
├── Procfile                 — Render startup command
├── .gitignore
└── README.md
```

---

## How to Run

### Pi-local (recommended for active use)
```bash
# On Pi
sudo systemctl start attendancepi-web
sudo systemctl start attendancepi
# Browser
http://raspberrypi.local:8000
```

### Render (recommended for remote access)
```bash
# Pi /etc/systemd/system/attendancepi.service:
# Environment=SERVER_URL=wss://attendancepi-XXXX.onrender.com
sudo systemctl restart attendancepi
# Browser
https://attendancepi-XXXX.onrender.com
```

Login password is set via the `ADMIN_PASSWORD` env var (Render dashboard or systemd Environment line).

---

## Future Improvements (Discussed, Not Built)
- Liveness detection (blink via YuNet landmarks, or MiniFASNet anti-spoofing model)
- Manual override button per student row on the monitor page
- Email/SMS alerts when specific students arrive
- Multi-camera support (multiple Pis connecting to one server)
- Attendance trends/charts
- Bulk enrol from a folder of photos
