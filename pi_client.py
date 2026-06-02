"""
Pi Client — runs on the Raspberry Pi.

Connects to the Render.com server via WebSocket, streams the camera feed,
runs the full attendance pipeline locally, and handles enrollment commands
sent from the admin webapp.

Usage:
    SERVER_URL=wss://your-app.onrender.com PI_SECRET=yourSecret python pi_client.py
"""

import os
import cv2
import json
import time
import base64
import asyncio
import threading
import queue
from collections import deque, Counter
import numpy as np
import websockets

import config
from detection.face_detector   import FaceDetector
from recognition.embedder      import FaceEmbedder
from recognition.matcher       import IdentityMatcher
from tracking.temporal_tracker import TemporalTracker
from attendance_engine         import AttendanceEngine

SERVER_URL = os.getenv("SERVER_URL", "wss://your-app.onrender.com")
PI_SECRET  = os.getenv("PI_SECRET",  "pisecret123")


# ── Camera setup ───────────────────────────────────────────────────────────────

def build_camera():
    from camera.threaded import ThreadedCamera

    if config.CAMERA_SOURCE == "webcam":
        from camera.webcam import WebcamStream
        return ThreadedCamera(WebcamStream(size=(config.FRAME_WIDTH, config.FRAME_HEIGHT)))
    else:
        from camera.picamera_stream import PiCameraStream
        return ThreadedCamera(PiCameraStream(size=(config.FRAME_WIDTH, config.FRAME_HEIGHT)))


# ── State shared between OpenCV thread and asyncio ────────────────────────────

class State:
    def __init__(self):
        self.mode              = "normal"    # "normal" | "enrolling"
        self.enroll_name       = None
        self.enroll_samples    = []
        self.enroll_target     = config.NUM_ENROLL_SAMPLES
        self.last_capture_time = 0.0
        self.lock              = threading.Lock()

        # Thread-safe queue: CV thread writes, asyncio sender reads
        self.outbox: queue.SimpleQueue = queue.SimpleQueue()
        self.last_unknown_sent = 0.0

        # Smooths recognition — only accept a name if it appears in
        # the majority of the last VOTE_WINDOW frames
        self.vote_buffer = deque(maxlen=10)


# ── CV processing ──────────────────────────────────────────────────────────────

def process_frame(frame, state, detector, embedder, matcher, tracker, attendance):
    faces = detector.detect(frame)

    with state.lock:
        mode = state.mode

    if mode == "enrolling":
        _process_enrollment(frame, faces, state, embedder)
    else:
        _process_attendance(frame, faces, state, matcher, embedder, tracker, attendance)

    return frame


def _process_enrollment(frame, faces, state, embedder):
    with state.lock:
        name    = state.enroll_name
        count   = len(state.enroll_samples)
        target  = state.enroll_target
        last_t  = state.last_capture_time

    cv2.putText(frame, f"Enrolling: {name}  ({count}/{target})",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    if len(faces) == 1:
        x1, y1, x2, y2 = faces[0]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)

        now = time.time()
        if now - last_t >= 2.0:
            face_crop = frame[y1:y2, x1:x2]
            if face_crop.size > 0:
                emb = embedder.embed(face_crop)

                with state.lock:
                    state.enroll_samples.append(emb)
                    state.last_capture_time = now
                    new_count = len(state.enroll_samples)
                    done      = new_count >= state.enroll_target

                state.outbox.put_nowait({
                    "type":  "sample_captured",
                    "count": new_count,
                    "total": state.enroll_target,
                })

                if done:
                    _finish_enrollment(state)
    else:
        hint = "No face detected" if len(faces) == 0 else "One face at a time"
        cv2.putText(frame, hint, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)


def _finish_enrollment(state):
    with state.lock:
        name    = state.enroll_name
        samples = list(state.enroll_samples)

    # Save to local embeddings file
    if os.path.exists(config.EMBEDDINGS_PATH):
        db = np.load(config.EMBEDDINGS_PATH, allow_pickle=True).item()
    else:
        db = {}

    db[name] = samples
    np.save(config.EMBEDDINGS_PATH, db)

    state.outbox.put_nowait({"type": "enrollment_complete", "name": name})

    with state.lock:
        state.mode           = "normal"
        state.enroll_name    = None
        state.enroll_samples = []

    print(f"Enrollment complete: {name}")


def _process_attendance(frame, faces, state, matcher, embedder, tracker, attendance):
    if len(faces) == 0:
        cv2.putText(frame, "No face detected", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
        return

    if len(faces) > 1:
        cv2.putText(frame, "Multiple faces — one at a time", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
        return

    if matcher is None:
        cv2.putText(frame, "No students enrolled", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
        return

    x1, y1, x2, y2 = faces[0]
    face_crop = frame[y1:y2, x1:x2]
    if face_crop.size == 0:
        return

    emb         = embedder.embed(face_crop)
    raw_name, score = matcher.match(emb)

    if raw_name is None:
        raw_name = "Unknown"

    # Vote buffer: only accept a name if it appears in 7 of the last 10 frames.
    # This kills flickering — a single bad frame can't change the result.
    state.vote_buffer.append(raw_name)
    top_name, top_count = Counter(state.vote_buffer).most_common(1)[0]
    name = top_name if top_count >= 7 else "Unknown"

    if name == "Unknown":
        now = time.time()
        if now - state.last_unknown_sent >= 3.0:
            state.last_unknown_sent = now
            state.outbox.put_nowait({"type": "unknown_face"})

    if name != "Unknown" and tracker.update(name):
        marked = attendance.mark_present(name)
        if marked:
            time_str = attendance.records[name]
            state.outbox.put_nowait({
                "type": "attendance_marked",
                "name": name,
                "time": time_str,
            })
            print(f"Marked present: {name}")

    color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
    label = name if name == "Unknown" else f"{name}  {score:.2f}"
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(frame, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


# ── Frame compression ──────────────────────────────────────────────────────────

def frame_to_b64(frame) -> str:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return base64.b64encode(buf).decode()


# ── Main asyncio client ────────────────────────────────────────────────────────

async def run(state, cap, detector, embedder, matcher, tracker, attendance):
    url = f"{SERVER_URL}/ws/pi?secret={PI_SECRET}"

    while True:
        try:
            print(f"Connecting to {SERVER_URL}...")
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                print("Connected.")

                async def sender():
                    nonlocal matcher
                    frame_count = 0
                    loop = asyncio.get_running_loop()

                    while True:
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            await asyncio.sleep(0.03)
                            continue

                        frame_count += 1

                        # Skip frames we won't send — no point running CV on them
                        if frame_count % 3 != 0:
                            await asyncio.sleep(0.01)
                            continue

                        # Run CV only on the frame we are about to send
                        frame = await loop.run_in_executor(
                            None, process_frame,
                            frame, state, detector, embedder, matcher, tracker, attendance
                        )

                        # Flush outbox (attendance events, enrollment updates)
                        while not state.outbox.empty():
                            msg = state.outbox.get_nowait()
                            await ws.send(json.dumps(msg))

                            if msg["type"] == "enrollment_complete":
                                if os.path.exists(config.EMBEDDINGS_PATH):
                                    db      = np.load(config.EMBEDDINGS_PATH, allow_pickle=True).item()
                                    matcher = IdentityMatcher(db, threshold=config.RECOGNITION_THRESHOLD)

                        # Resize to half resolution + lower quality before sending
                        # cuts bandwidth ~75% with barely noticeable quality loss
                        small = cv2.resize(frame, (320, 240))
                        # Browser expects RGB in JPEG — convert from BGR before encoding
                        small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                        _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 40])
                        b64 = base64.b64encode(buf).decode()
                        await ws.send(json.dumps({"type": "frame", "data": b64}))

                async def receiver():
                    async for raw in ws:
                        msg = json.loads(raw)

                        if msg["type"] == "start_enrollment":
                            name   = msg.get("name", "Unknown")
                            target = msg.get("samples", config.NUM_ENROLL_SAMPLES)
                            with state.lock:
                                state.mode              = "enrolling"
                                state.enroll_name       = name
                                state.enroll_samples    = []
                                state.enroll_target     = target
                                state.last_capture_time = 0.0
                            print(f"Enrollment started: {name}")

                        elif msg["type"] == "stop_enrollment":
                            with state.lock:
                                state.mode           = "normal"
                                state.enroll_name    = None
                                state.enroll_samples = []
                            print("Enrollment cancelled.")

                        elif msg["type"] == "settings_update":
                            s = msg.get("settings", {})
                            with state.lock:
                                if "recognition_threshold" in s:
                                    state.recognition_threshold = float(s["recognition_threshold"])
                                if "temporal_min_duration" in s:
                                    state.temporal_min_duration = float(s["temporal_min_duration"])
                                if "num_enroll_samples" in s:
                                    state.enroll_target = int(s["num_enroll_samples"])
                            # Update live objects
                            if "recognition_threshold" in s:
                                matcher.threshold = float(s["recognition_threshold"])
                            if "temporal_min_duration" in s:
                                tracker.min_duration = float(s["temporal_min_duration"])
                            print(f"Settings updated: {s}")

                        elif msg["type"] == "reset_embeddings":
                            if os.path.exists(config.EMBEDDINGS_PATH):
                                os.remove(config.EMBEDDINGS_PATH)
                            matcher = None
                            tracker.first_seen.clear()
                            tracker.marked.clear()
                            state.vote_buffer.clear()
                            print("Embeddings reset.")

                await asyncio.gather(sender(), receiver())

        except Exception as e:
            print(f"Disconnected: {e}. Retrying in 5s...")
            await asyncio.sleep(5)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    print("Starting Pi Client...")

    cap = build_camera()

    detector   = FaceDetector(config.DETECTOR_MODEL, config.FRAME_WIDTH,
                               config.FRAME_HEIGHT, config.DETECTION_CONFIDENCE)
    embedder   = FaceEmbedder(config.EMBEDDER_MODEL)
    tracker    = TemporalTracker(min_duration=config.TEMPORAL_MIN_DURATION)
    attendance = AttendanceEngine(save_dir=config.ATTENDANCE_LOG_DIR)

    matcher = None
    if os.path.exists(config.EMBEDDINGS_PATH):
        db      = np.load(config.EMBEDDINGS_PATH, allow_pickle=True).item()
        matcher = IdentityMatcher(db, threshold=config.RECOGNITION_THRESHOLD)
        print(f"Loaded {len(db)} enrolled students.")
    else:
        print("No embeddings found — run enrollment first.")

    state = State()

    asyncio.run(run(state, cap, detector, embedder, matcher, tracker, attendance))


if __name__ == "__main__":
    main()
