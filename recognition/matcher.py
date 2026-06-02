import numpy as np


class IdentityMatcher:
    def __init__(self, known_embeddings, threshold=0.65):
        self.threshold = threshold

        # Normalise to list format
        self.known_embeddings = {}
        for name, emb in known_embeddings.items():
            if isinstance(emb, list):
                self.known_embeddings[name] = emb
            else:
                self.known_embeddings[name] = [emb]

    def match(self, query_embedding):
        """
        Score each person by the mean of their TOP 3 most-similar samples.
        This is more robust than a single max — a single fluke sample
        from a new enrolment can't dominate the result.

        Also requires a MARGIN between best and runner-up:
        the winner must beat second place by at least 0.05.
        Otherwise the match is too ambiguous to trust.
        """
        per_person_scores = {}

        for name, embeddings in self.known_embeddings.items():
            sims = [float(np.dot(query_embedding, ref)) for ref in embeddings]
            sims.sort(reverse=True)
            # Mean of top 3 (or fewer if person has <3 samples)
            top_k = sims[:3]
            per_person_scores[name] = sum(top_k) / len(top_k)

        if not per_person_scores:
            return None, -1.0

        # Sort by score, descending
        ranked = sorted(per_person_scores.items(), key=lambda x: x[1], reverse=True)
        best_name, best_score = ranked[0]

        # Margin check — winner must beat second place by a small amount.
        # Only enforced when there are 3+ enrolled people; with just 2,
        # similar-looking pairs would always fail this check.
        if len(ranked) >= 3:
            second_score = ranked[1][1]
            if best_score - second_score < 0.02:
                return None, best_score   # too ambiguous

        if best_score >= self.threshold:
            return best_name, best_score

        return None, best_score
