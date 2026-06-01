import csv
import io
from datetime import date, datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from ..database import get_db, Student, AttendanceRecord, get_settings, save_setting
from ..relay    import relay

router = APIRouter()


@router.delete("/students/{student_id}")
def delete_student(student_id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        return JSONResponse({"error": "Not found"}, status_code=404)
    db.delete(student)
    db.commit()
    return JSONResponse({"ok": True})


@router.get("/attendance/today")
def today_attendance(db: Session = Depends(get_db)):
    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.date == date.today())
        .join(Student)
        .order_by(AttendanceRecord.time_marked)
        .all()
    )
    return [{"name": r.student.name, "time": r.time_marked} for r in records]


@router.get("/pi/status")
def pi_status():
    return {"connected": relay.pi_connected}


@router.get("/attendance/export")
def export_csv(selected_date: str = None, db: Session = Depends(get_db)):
    target_date = date.today()
    if selected_date:
        try:
            target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.date == target_date)
        .join(Student)
        .order_by(AttendanceRecord.time_marked)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Date", "Time"])
    for r in records:
        writer.writerow([r.student.name, str(r.date), r.time_marked])

    output.seek(0)
    filename = f"attendance_{target_date}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/settings")
async def update_settings(request: Request, db: Session = Depends(get_db)):
    data = await request.json()

    allowed = {"recognition_threshold", "detection_confidence",
               "temporal_min_duration", "num_enroll_samples"}

    for key, value in data.items():
        if key in allowed:
            save_setting(db, key, str(value))

    # Push updated settings to Pi immediately if connected
    settings = get_settings(db)
    await relay.send_to_pi({"type": "settings_update", "settings": settings})

    return JSONResponse({"ok": True, "settings": settings})
