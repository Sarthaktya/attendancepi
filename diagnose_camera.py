import cv2
import numpy as np

backends = [
    ("DSHOW",  cv2.CAP_DSHOW),
    ("MSMF",   cv2.CAP_MSMF),
    ("ANY",    cv2.CAP_ANY),
]

print("Scanning cameras...\n")

for index in range(4):
    for backend_name, backend in backends:
        cap = cv2.VideoCapture(index, backend)

        if not cap.isOpened():
            continue

        # Discard warmup frames
        for _ in range(3):
            cap.read()

        ret, frame = cap.read()

        if not ret or frame is None:
            cap.release()
            continue

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Check if frame is actually black or a placeholder
        mean_brightness = np.mean(frame)
        looks_real      = mean_brightness > 5.0

        print(f"  Index {index} | {backend_name:5s} | {w}x{h} | brightness={mean_brightness:.1f} | {'REAL FEED' if looks_real else 'BLACK / PLACEHOLDER'}")
        cap.release()

print("\nDone. Use the index + backend marked as REAL FEED.")
