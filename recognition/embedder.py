import cv2
import numpy as np


class FaceEmbedder:
    """
    Wraps OpenCV's FaceRecognizerSF (the official SFace API).
    It uses YuNet's landmarks to align the face before embedding —
    this is what SFace was designed for and dramatically improves accuracy.
    """

    def __init__(self, model_path):
        self.recognizer = cv2.FaceRecognizerSF.create(model_path, "")

    def embed(self, frame, detection):
        """
        frame:     full BGR camera frame
        detection: raw YuNet detection row (with landmarks)
        Returns:   L2-normalised 128-dim embedding
        """
        # alignCrop expects shape (1, 15) — reshape if it's a 1D array
        det = np.asarray(detection, dtype=np.float32)
        if det.ndim == 1:
            det = det.reshape(1, -1)

        aligned = self.recognizer.alignCrop(frame, det[0])
        feature = self.recognizer.feature(aligned)
        feature = feature.flatten()

        # L2-normalise so cosine similarity == dot product
        norm = np.linalg.norm(feature)
        if norm > 0:
            feature = feature / norm

        return feature
