import cv2
import numpy as np


class FaceEmbedder:
    def __init__(self, model_path):
        self.net = cv2.dnn.readNet(model_path)

    def embed(self, face):
        face_resized = cv2.resize(face, (112, 112))

        # Input is BGR. swapRB=True converts it to RGB before the model sees it.
        blob = cv2.dnn.blobFromImage(
            face_resized,
            scalefactor=1.0 / 255,
            size=(112, 112),
            mean=(0, 0, 0),
            swapRB=True,
            crop=False
        )

        self.net.setInput(blob)
        embedding = self.net.forward()
        embedding = embedding.flatten()

        # Normalize so cosine similarity equals dot product
        norm = np.linalg.norm(embedding)
        embedding = embedding / norm

        return embedding
