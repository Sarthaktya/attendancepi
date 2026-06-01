import numpy as np


class IdentityMatcher:
    def __init__(self, known_embeddings, threshold=0.65):
        self.threshold = threshold

        # Normalise to list format regardless of how embeddings were saved.
        # Old enroll_faces.py saved a single averaged array; new one saves a list.
        self.known_embeddings = {}
        for name, emb in known_embeddings.items():
            if isinstance(emb, list):
                self.known_embeddings[name] = emb
            else:
                self.known_embeddings[name] = [emb]

    def match(self, query_embedding):
        best_name  = None
        best_score = -1.0

        for name, embeddings in self.known_embeddings.items():
            # Score against every stored sample and take the best one.
            # This is more robust than matching against a single average.
            for ref_embedding in embeddings:
                score = float(np.dot(query_embedding, ref_embedding))

                if score > best_score:
                    best_score = score
                    best_name  = name

        if best_score >= self.threshold:
            return best_name, best_score

        return None, best_score
