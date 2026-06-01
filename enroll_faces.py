import os
import argparse
import cv2
import numpy as np

import config
from detection.face_detector import FaceDetector
from recognition.embedder    import FaceEmbedder


WINDOW_TITLE = "Enrollment"


def get_camera():
    from camera.threaded import ThreadedCamera

    if config.CAMERA_SOURCE == "webcam":
        from camera.webcam import WebcamStream
        return ThreadedCamera(WebcamStream(size=(config.FRAME_WIDTH, config.FRAME_HEIGHT)))
    else:
        from camera.picamera_stream import PiCameraStream
        return ThreadedCamera(PiCameraStream(size=(config.FRAME_WIDTH, config.FRAME_HEIGHT)))


def main():
    parser = argparse.ArgumentParser(description="Enroll a face into the attendance system")
    parser.add_argument("--name",    required=True, help="Name of the person to enroll")
    parser.add_argument("--samples", type=int, default=config.NUM_ENROLL_SAMPLES, help="Number of samples to capture")
    args = parser.parse_args()

    name        = args.name
    num_samples = args.samples

    detector = FaceDetector(config.DETECTOR_MODEL, config.FRAME_WIDTH, config.FRAME_HEIGHT, config.DETECTION_CONFIDENCE)
    embedder = FaceEmbedder(config.EMBEDDER_MODEL)
    cap      = get_camera()

    captured = []

    print(f"Enrolling: {name}")
    print("Press 'c' to capture a sample, 'q' to quit early")

    while True:
        ret, frame = cap.read()

        if not ret:
            print("Error: could not read frame.")
            break

        faces = detector.detect(frame)

        for (x1, y1, x2, y2) in faces:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        cv2.putText(
            frame,
            f"Samples: {len(captured)}/{num_samples}",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        cv2.imshow(WINDOW_TITLE, frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("c") and len(faces) == 1:
            x1, y1, x2, y2 = faces[0]
            face_crop = frame[y1:y2, x1:x2]

            if face_crop.size > 0:
                embedding = embedder.embed(face_crop)
                captured.append(embedding)
                print(f"Captured {len(captured)}/{num_samples}")

        if key == ord("q") or len(captured) >= num_samples:
            break

    cap.release()
    cv2.destroyAllWindows()

    if len(captured) == 0:
        print("Enrollment failed: no samples captured.")
        return

    # Load existing database or start a fresh one
    if os.path.exists(config.EMBEDDINGS_PATH):
        database = np.load(config.EMBEDDINGS_PATH, allow_pickle=True).item()
    else:
        database = {}

    database[name] = captured
    np.save(config.EMBEDDINGS_PATH, database)

    print(f"Done. {len(captured)} samples saved for {name}.")


if __name__ == "__main__":
    main()
