import os

# All paths are relative to this file so the project works
# regardless of which directory you run scripts from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _path(*parts):
    return os.path.join(BASE_DIR, *parts)

# ---------------------------------------------------------
# Change CAMERA_SOURCE to switch between laptop and Pi.
#   "webcam"   -> uses your laptop camera (for testing)
#   "picamera" -> uses the Raspberry Pi camera module
# ---------------------------------------------------------
CAMERA_SOURCE = "webcam"

# Model paths
DETECTOR_MODEL = _path("models", "face_detection_yunet_2026may.onnx")
EMBEDDER_MODEL = _path("models", "recognition", "face_recognition_sface_2021dec.onnx")

# Camera resolution
FRAME_WIDTH  = 640
FRAME_HEIGHT = 480

# Detection — lower this if faces are being missed, raise it to reduce false positives
DETECTION_CONFIDENCE = 0.6

# Recognition — raise this to be stricter about who gets marked present
RECOGNITION_THRESHOLD = 0.75

# Enrollment
NUM_ENROLL_SAMPLES = 30
EMBEDDINGS_PATH    = _path("known_embeddings.npy")

# Attendance
ATTENDANCE_LOG_DIR    = _path("attendance_logs")
TEMPORAL_MIN_DURATION = 2.0   # seconds a face must be visible before being marked
