"""vector data utilities."""


def normalize_cosine_score(raw_score: float) -> float:
	"""normalize cosine similarity score from -1..1 to 0..1 range."""
	return (raw_score + 1) / 2


def normalize_scores(scores: list[float]) -> list[float]:
	"""normalize a list of scores to 0-1 where 1 is most relevant.

	divides all scores by the max score in the batch.
	"""
	if not scores:
		return scores
	max_score = max(scores)
	if max_score <= 0:
		return [0.0] * len(scores)
	return [s / max_score for s in scores]
