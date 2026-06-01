import cv2
import sys
import signal
import numpy as np

import config
from detection.face_detector    import FaceDetector
from recognition.embedder       import FaceEmbedder
from recognition.matcher        import IdentityMatcher
from tracking.temporal_tracker  import TemporalTracker
from attendance_engine          import AttendanceEngine


WINDOW_TITLE = "Attendance System"


def get_camera():
    from camera.threaded import ThreadedCamera

    if config.CAMERA_SOURCE == "webcam":
        from camera.webcam import WebcamStream
        return ThreadedCamera(WebcamStream(size=(config.FRAME_WIDTH, config.FRAME_HEIGHT)))
    else:
        from camera.picamera_stream import PiCameraStream
        return ThreadedCamera(PiCameraStream(size=(config.FRAME_WIDTH, config.FRAME_HEIGHT)))


def load_embeddings():
    import os
    if not os.path.exists(config.EMBEDDINGS_PATH):
        print("No enrolled faces found. Run enroll_faces.py first.")
        sys.exit(1)

    database = np.load(config.EMBEDDINGS_PATH, allow_pickle=True).item()
    print(f"Loaded {len(database)} enrolled people: {list(database.keys())}")
    return database


def draw_face_box(frame, x1, y1, x2, y2, label):
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(
        frame, label, (x1, y1 - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2
    )


def draw_status(frame, present_count, message=""):
    cv2.putText(
        frame, f"Present: {present_count}", (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
    )
    if message:
        cv2.putText(
            frame, message, (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2
        )


def main():
    print("Starting Attendance System...")

    known_embeddings = load_embeddings()

    detector   = FaceDetector(config.DETECTOR_MODEL, config.FRAME_WIDTH, config.FRAME_HEIGHT, config.DETECTION_CONFIDENCE)
    embedder   = FaceEmbedder(config.EMBEDDER_MODEL)
    matcher    = IdentityMatcher(known_embeddings, threshold=config.RECOGNITION_THRESHOLD)
    tracker    = TemporalTracker(min_duration=config.TEMPORAL_MIN_DURATION)
    attendance = AttendanceEngine(save_dir=config.ATTENDANCE_LOG_DIR)
    cap        = get_camera()

    def shutdown(sig, frame_arg):
        print("\nShutting down...")
        cap.release()
        cv2.destroyAllWindows()
        path = attendance.save_csv()
        print(f"Attendance saved to {path}")
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("System running. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()

        if not ret:
            print("Error: could not read frame.")
            break

        faces          = detector.detect(frame)
        status_message = ""

        if len(faces) == 0:
            status_message = "No face detected"

        elif len(faces) > 1:
            status_message = "Multiple faces - please enter one at a time"

        else:
            x1, y1, x2, y2 = faces[0]
            face_crop = frame[y1:y2, x1:x2]

            if face_crop.size > 0:
                embedding    = embedder.embed(face_crop)
                name, score  = matcher.match(embedding)

                if name is None:
                    name = "Unknown"

                if name == "Unknown":
                    label = "Unknown"
                else:
                    label = f"{name} ({score:.2f})"

                if tracker.update(name):
                    was_new = attendance.mark_present(name)
                    if was_new:
                        print(f"{name} marked present")

                draw_face_box(frame, x1, y1, x2, y2, label)

        draw_status(frame, len(attendance.records), status_message)

        cv2.imshow(WINDOW_TITLE, frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    path = attendance.save_csv()
    print(f"Attendance saved to {path}")


if __name__ == "__main__":
    main()
