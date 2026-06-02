import json
from datetime import date
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..relay    import relay
from ..auth     import PI_SECRET
from ..database import SessionLocal, Student, AttendanceRecord, get_settings

router = APIRouter()


@router.websocket("/ws/pi")
async def pi_endpoint(ws: WebSocket, secret: str = ""):
    if secret != PI_SECRET:
        await ws.close(code=4001)
        return

    await relay.connect_pi(ws)

    # Send current settings to Pi immediately on connect
    db       = SessionLocal()
    settings = get_settings(db)
    db.close()
    await relay.send_to_pi({"type": "settings_update", "settings": settings})

    try:
        while True:
            msg = await ws.receive_json()

            # ── Forward raw frame to all browsers ──────────────────────────
            if msg["type"] == "frame":
                await relay.broadcast(msg)

            # ── Save attendance record and notify browsers ──────────────────
            elif msg["type"] == "attendance_marked":
                name     = msg.get("name")
                time_str = msg.get("time")

                db      = SessionLocal()
                student = db.query(Student).filter(Student.name == name).first()

                if not student:
                    student = Student(name=name)
                    db.add(student)
                    db.commit()
                    db.refresh(student)

                existing = (
                    db.query(AttendanceRecord)
                    .filter(AttendanceRecord.student_id == student.id,
                            AttendanceRecord.date == date.today())
                    .first()
                )

                if not existing:
                    db.add(AttendanceRecord(
                        student_id  = student.id,
                        date        = date.today(),
                        time_marked = time_str
                    ))
                    db.commit()

                db.close()
                await relay.broadcast(msg)

            # ── Unknown face detected ──────────────────────────────────────
            elif msg["type"] == "unknown_face":
                await relay.broadcast(msg)

            # ── Enrollment progress updates ─────────────────────────────────
            elif msg["type"] in ("sample_captured", "enrollment_complete"):
                if msg["type"] == "enrollment_complete":
                    name = msg.get("name")
                    db   = SessionLocal()
                    if not db.query(Student).filter(Student.name == name).first():
                        db.add(Student(name=name))
                        db.commit()
                    db.close()

                await relay.broadcast(msg)

    except WebSocketDisconnect:
        was_current = relay.pi is ws
        relay.disconnect_pi(ws)
        # Only mark disconnected if this WAS the current Pi connection
        if was_current:
            await relay.broadcast({"type": "pi_status", "connected": False})


@router.websocket("/ws/browser")
async def browser_endpoint(ws: WebSocket):
    await relay.connect_browser(ws)
    await ws.send_json({"type": "pi_status", "connected": relay.pi_connected})

    try:
        while True:
            msg = await ws.receive_json()
            # Browser sends enrollment commands → forward to Pi
            if msg.get("type") in ("start_enrollment", "stop_enrollment"):
                await relay.send_to_pi(msg)
    except WebSocketDisconnect:
        relay.disconnect_browser(ws)
