"""vector data utilities."""


def normalize_cosine_score(raw_score: float) -> float:
	"""normalize cosine similarity score from -1..1 to 0..1 range."""
	return (raw_score + 1) / 2
