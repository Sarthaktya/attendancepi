import cv2
import time

import config
from detection.face_detector import FaceDetector


def main():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    # Discard the first few frames — some cameras return black on startup
    for _ in range(5):
        cap.read()

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera opened at {actual_w}x{actual_h}")

    # Update detector input size to match what the camera actually gives us
    detector = FaceDetector(
        config.DETECTOR_MODEL,
        actual_w,
        actual_h,
        config.DETECTION_CONFIDENCE
    )

    print("Face detection test running. Press 'q' to quit.")

    prev_time = time.time()

    while True:
        ret, frame = cap.read()

        if not ret:
            print("Error: could not read frame.")
            break

        faces = detector.detect(frame)

        for (x1, y1, x2, y2) in faces:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # FPS counter
        now       = time.time()
        fps       = 1.0 / (now - prev_time)
        prev_time = now

        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"Faces: {len(faces)}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.imshow("Detection Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
