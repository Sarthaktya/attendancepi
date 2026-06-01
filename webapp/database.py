import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./attendance.db")

# Render.com gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine       = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()


class Student(Base):
    __tablename__ = "students"

    id         = Column(Integer, primary_key=True)
    name       = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship("AttendanceRecord", back_populates="student", cascade="all, delete")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id          = Column(Integer, primary_key=True)
    student_id  = Column(Integer, ForeignKey("students.id"), nullable=False)
    date        = Column(Date,    nullable=False)
    time_marked = Column(String,  nullable=False)

    student = relationship("Student", back_populates="records")


class Setting(Base):
    __tablename__ = "settings"

    key   = Column(String, primary_key=True)
    value = Column(String, nullable=False)


# Default values — used if no row exists in DB yet
DEFAULT_SETTINGS = {
    "recognition_threshold":  "0.75",
    "detection_confidence":   "0.6",
    "temporal_min_duration":  "2.0",
    "num_enroll_samples":     "30",
}


def get_settings(db) -> dict:
    rows = db.query(Setting).all()
    result = dict(DEFAULT_SETTINGS)
    for row in rows:
        result[row.key] = row.value
    return result


def save_setting(db, key: str, value: str):
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(engine)
