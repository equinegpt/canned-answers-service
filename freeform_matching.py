# freeform_matching.py
"""
Fuzzy matching utilities for freeform question caching.

Uses Jaccard similarity with stop word removal and optional subset boosting.
"""

import json
import re
from typing import List, Set, Tuple, Optional, Any

# Stop words to remove during tokenization
STOP_WORDS: Set[str] = {
    "the", "a", "an", "is", "are", "in", "this", "for",
    "of", "to", "and", "or"
}


def normalize_question(question: str) -> str:
    """
    Normalize question: lowercase, strip punctuation.
    Returns the normalized string.
    """
    # Lowercase
    text = question.lower()
    # Remove punctuation (keep alphanumeric and spaces)
    text = re.sub(r'[^\w\s]', '', text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text


def tokenize_question(normalized: str) -> List[str]:
    """
    Split normalized text into tokens and remove stop words.
    Returns list of tokens (for JSON storage).
    """
    tokens = normalized.split()
    filtered = [t for t in tokens if t not in STOP_WORDS]
    return filtered


def tokens_to_json(tokens: List[str]) -> str:
    """Serialize tokens to JSON string for database storage."""
    return json.dumps(tokens)


def json_to_tokens(json_str: str) -> List[str]:
    """Deserialize tokens from JSON string."""
    return json.loads(json_str)


def jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    """
    Calculate Jaccard similarity: |intersection| / |union|
    Returns 0.0 if both sets are empty.
    """
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def compute_similarity(query_tokens: List[str], stored_tokens: List[str]) -> float:
    """
    Compute similarity between query and stored tokens.
    Includes subset boost: if query is a complete subset of stored tokens,
    boost the score slightly to prefer more comprehensive stored answers.
    """
    query_set = set(query_tokens)
    stored_set = set(stored_tokens)

    base_similarity = jaccard_similarity(query_set, stored_set)

    # Subset boost: if query tokens are entirely contained in stored tokens,
    # this indicates the stored question covers the query topic
    # Boost by 10% of the remaining score (caps at 1.0)
    if query_set and query_set.issubset(stored_set):
        boost = (1.0 - base_similarity) * 0.10
        base_similarity = min(1.0, base_similarity + boost)

    return base_similarity


def find_best_match(
    query_tokens: List[str],
    candidates: List[Tuple[Any, List[str]]],
    threshold: float
) -> Optional[Tuple[Any, float]]:
    """
    Find the best matching candidate above threshold.

    Args:
        query_tokens: Tokenized query question
        candidates: List of (db_record, stored_tokens) tuples
        threshold: Minimum similarity to accept

    Returns:
        (best_record, confidence) if found, else None
    """
    best_match = None
    best_score = 0.0

    for record, stored_tokens in candidates:
        score = compute_similarity(query_tokens, stored_tokens)
        if score > best_score:
            best_score = score
            best_match = record

    if best_match is not None and best_score >= threshold:
        return (best_match, best_score)

    return None
