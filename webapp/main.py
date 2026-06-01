from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from .database import init_db
from .routers import pages, api, ws

app = FastAPI(title="AttendancePi")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return RedirectResponse("/dashboard")


app.include_router(pages.router)
app.include_router(api.router,  prefix="/api")
app.include_router(ws.router)
