import cv2


class FaceDetector:
    def __init__(self, model_path, frame_width, frame_height, confidence_threshold=0.6):
        self.frame_width  = frame_width
        self.frame_height = frame_height

        self.detector = cv2.FaceDetectorYN.create(
            model_path,
            "",
            (frame_width, frame_height),
            score_threshold=confidence_threshold
        )

    def detect(self, frame):
        _, detections = self.detector.detect(frame)

        if detections is None:
            return []

        boxes = []
        for detection in detections:
            x = int(detection[0])
            y = int(detection[1])
            w = int(detection[2])
            h = int(detection[3])

            # Clamp to frame boundaries
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(self.frame_width,  x + w)
            y2 = min(self.frame_height, y + h)

            boxes.append((x1, y1, x2, y2))

        return boxes
