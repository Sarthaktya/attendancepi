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
        """
        Returns a list of detection arrays (raw YuNet output rows).
        Each row contains: [x, y, w, h, lm_x1, lm_y1, ..., score]
        The full row is needed by SFace's alignCrop() for proper alignment.
        """
        _, detections = self.detector.detect(frame)
        if detections is None:
            return []
        return list(detections)

    @staticmethod
    def detection_to_box(detection, frame_width, frame_height):
        """Convert raw detection to a clamped bounding box for display."""
        x = int(detection[0])
        y = int(detection[1])
        w = int(detection[2])
        h = int(detection[3])

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(frame_width,  x + w)
        y2 = min(frame_height, y + h)

        return (x1, y1, x2, y2)
