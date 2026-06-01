import numpy as np


class FaceRecognizer:
    def __init__(self, db_path, threshold=0.6):
        self.threshold = threshold
        self.db = np.load(db_path, allow_pickle=True).item()

    def recognize(self, embedding):
        best_name = "Unknown"
        best_distance = float("inf")

        for name, known_emb in self.db.items():
            dist = np.linalg.norm(embedding - known_emb)
            if dist < best_distance:
                best_distance = dist
                best_name = name

        if best_distance < self.threshold:
            return best_name, best_distance
        
        return "Unknown", best_distance
