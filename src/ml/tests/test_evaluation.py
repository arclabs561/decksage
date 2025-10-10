"""Test evaluation utilities."""

from ..utils.evaluation import (
    compute_precision_at_k,
    evaluate_similarity,
    jaccard_similarity,
)


def test_compute_precision_at_k_perfect():
    """Perfect predictions score 1.0."""
    predictions = ["card1", "card2", "card3"]
    labels = {"highly_relevant": ["card1", "card2", "card3"], "relevant": [], "irrelevant": []}

    score = compute_precision_at_k(predictions, labels, k=3)
    assert score == 1.0


def test_compute_precision_at_k_none():
    """No relevant predictions score 0.0."""
    predictions = ["card1", "card2", "card3"]
    labels = {
        "highly_relevant": ["other1"],
        "relevant": ["other2"],
        "irrelevant": ["card1", "card2", "card3"],
    }

    score = compute_precision_at_k(predictions, labels, k=3)
    assert score == 0.0


def test_compute_precision_at_k_weighted():
    """Mixed relevance is weighted correctly."""
    predictions = ["card1", "card2", "card3"]
    labels = {
        "highly_relevant": ["card1"],  # 1.0
        "relevant": ["card2"],  # 0.75
        "somewhat_relevant": ["card3"],  # 0.5
        "irrelevant": [],
    }

    # (1.0 + 0.75 + 0.5) / 3 = 0.75
    score = compute_precision_at_k(predictions, labels, k=3)
    assert abs(score - 0.75) < 0.001


def test_jaccard_similarity_identical():
    """Identical sets have Jaccard = 1.0."""
    set1 = {"a", "b", "c"}
    set2 = {"a", "b", "c"}
    assert jaccard_similarity(set1, set2) == 1.0


def test_jaccard_similarity_disjoint():
    """Disjoint sets have Jaccard = 0.0."""
    set1 = {"a", "b", "c"}
    set2 = {"d", "e", "f"}
    assert jaccard_similarity(set1, set2) == 0.0


def test_jaccard_similarity_partial():
    """Partial overlap calculates correctly."""
    set1 = {"a", "b", "c"}
    set2 = {"b", "c", "d"}
    # Intersection: {b, c} = 2
    # Union: {a, b, c, d} = 4
    # Jaccard = 2/4 = 0.5
    assert jaccard_similarity(set1, set2) == 0.5


def test_jaccard_similarity_empty():
    """Empty sets return 0.0."""
    assert jaccard_similarity(set(), set()) == 0.0
    assert jaccard_similarity({"a"}, set()) == 0.0
    assert jaccard_similarity(set(), {"a"}) == 0.0


def test_evaluate_similarity_basic():
    """Basic evaluation loop works."""
    test_set = {"query1": {"highly_relevant": ["result1", "result2"], "relevant": ["result3"]}}

    def dummy_similarity(query, k):
        return [("result1", 0.9), ("result2", 0.8), ("wrong", 0.7)]

    results = evaluate_similarity(test_set, dummy_similarity, top_k=3)

    assert "p@3" in results
    assert "ndcg@3" in results
    assert "mrr@3" in results
    assert results["num_queries"] == 1
    assert results["num_evaluated"] == 1
    assert results["num_skipped"] == 0
    assert 0.0 <= results["p@3"] <= 1.0


def test_evaluate_similarity_skip_missing():
    """Skips queries that error."""
    test_set = {"query1": {"highly_relevant": ["a"]}, "query2": {"highly_relevant": ["b"]}}

    def failing_similarity(query, k):
        if query == "query1":
            raise KeyError("Missing")
        return [("b", 0.9)]

    results = evaluate_similarity(test_set, failing_similarity, top_k=1)

    assert results["num_queries"] == 2
    assert results["num_evaluated"] == 1
    assert results["num_skipped"] == 1
