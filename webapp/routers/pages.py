from pathlib import Path
from datetime import date, datetime
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from ..auth     import is_authenticated, create_session, ADMIN_PASSWORD
from ..database import SessionLocal, Student, AttendanceRecord, get_settings

router    = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _auth(request: Request):
    """Return a redirect if not logged in, else None."""
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    return None


# ── Auth ───────────────────────────────────────────────────────────────────────

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login(request: Request):
    form     = await request.form()
    password = form.get("password", "")

    if password == ADMIN_PASSWORD:
        token    = create_session()
        response = RedirectResponse("/dashboard", status_code=303)
        response.set_cookie("session", token, httponly=True, samesite="lax")
        return response

    return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect password"})


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response


# ── Pages ──────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard(request: Request):
    if (r := _auth(request)):
        return r

    db             = SessionLocal()
    total_students = db.query(Student).count()
    today_count    = db.query(AttendanceRecord).filter(AttendanceRecord.date == date.today()).count()
    db.close()

    return templates.TemplateResponse("dashboard.html", {
        "request":        request,
        "total_students": total_students,
        "today_count":    today_count,
    })


@router.get("/enroll")
def enroll_page(request: Request):
    if (r := _auth(request)):
        return r
    return templates.TemplateResponse("enroll.html", {"request": request})


@router.get("/students")
def students_page(request: Request):
    if (r := _auth(request)):
        return r

    db       = SessionLocal()
    students = db.query(Student).order_by(Student.created_at.desc()).all()
    db.close()

    return templates.TemplateResponse("students.html", {
        "request":  request,
        "students": students,
    })


@router.get("/monitor")
def monitor_page(request: Request):
    if (r := _auth(request)):
        return r

    db       = SessionLocal()
    students = db.query(Student).order_by(Student.name).all()
    records  = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.date == date.today())
        .all()
    )
    db.close()

    present_map = {r.student_id: r.time_marked for r in records}

    student_data = [
        {
            "id":      s.id,
            "name":    s.name,
            "present": s.id in present_map,
            "time":    present_map.get(s.id),
        }
        for s in students
    ]

    # Sort: absent first so present students don't push absent ones off screen
    student_data.sort(key=lambda s: s["present"])

    return templates.TemplateResponse("monitor.html", {
        "request":       request,
        "students":      student_data,
        "present_count": len(present_map),
        "total_count":   len(students),
        "today":         date.today().strftime("%d %b %Y"),
    })


@router.get("/attendance")
def attendance_page(request: Request, selected_date: str = None):
    if (r := _auth(request)):
        return r

    target_date = date.today()
    if selected_date:
        try:
            target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    db = SessionLocal()
    raw = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.date == target_date)
        .join(Student)
        .order_by(AttendanceRecord.time_marked)
        .all()
    )
    # Convert to plain dicts while the session is still open —
    # avoids lazy-load errors after db.close()
    records = [{"name": r.student.name, "time": r.time_marked} for r in raw]
    db.close()

    return templates.TemplateResponse("attendance.html", {
        "request":       request,
        "records":       records,
        "selected_date": target_date.strftime("%Y-%m-%d"),
        "is_today":      target_date == date.today(),
    })


@router.get("/settings")
def settings_page(request: Request):
    if (r := _auth(request)):
        return r

    db       = SessionLocal()
    settings = get_settings(db)
    db.close()

    return templates.TemplateResponse("settings.html", {
        "request":  request,
        "settings": settings,
    })
