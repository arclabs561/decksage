#!/usr/bin/env python3
"""
Inter-Annotator Agreement (IAA) Metrics

Implements modern best practices for annotation quality assessment:
- Cohen's Kappa (two annotators)
- Krippendorff's Alpha (multiple annotators, handles missing data)
- Fleiss' Kappa (multiple annotators, categorical)
- Intra-class Correlation (continuous/ordinal)
- Intra-annotator agreement (stability over time)

Based on 2024-2025 best practices:
- Multi-layered evaluation (reliability, difficulty, ambiguity)
- Annotator confidence tracking
- Continuous monitoring

Research References:
- Inter-annotator agreement: https://www.innovatiana.com/en/post/inter-annotator-agreement
- Krippendorff's Alpha: https://labelstud.io/blog/how-to-use-krippendorff-s-alpha-to-measure-annotation-agreement
- Building trustworthy datasets: https://keymakr.com/blog/measuring-inter-annotator-agreement-building-trustworthy-datasets/
- Data annotation metrics: https://www.telusdigital.com/insights/data-and-ai/article/data-annotation-metrics
- Multi-annotator validation: https://mindkosh.com/blog/multi-annotator-validation-enhancing-label-accuracy-through-consensus
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np


try:
    from scipy.stats import chi2_contingency

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    chi2_contingency = None


class InterAnnotatorAgreement:
    """
    Compute inter-annotator agreement metrics for annotation quality assessment.

    Best practices (2024-2025):
    - Assess annotator reliability, sample difficulty, label ambiguity simultaneously
    - Complement IAA with intra-annotator agreement (stability)
    - Incorporate annotator confidence ratings
    - Continuous monitoring of IAA trends
    """

    def __init__(self):
        pass

    def cohens_kappa(
        self, annotator1: list[int], annotator2: list[int], min_rating: int = 0, max_rating: int = 4
    ) -> dict[str, float]:
        """
        Compute Cohen's Kappa for two annotators.

        κ = (P_o - P_e) / (1 - P_e)
        where:
        - P_o = observed agreement
        - P_e = expected agreement by chance

        Interpretation:
        - κ < 0: No agreement
        - 0 ≤ κ ≤ 0.20: Slight agreement
        - 0.21 ≤ κ ≤ 0.40: Fair agreement
        - 0.41 ≤ κ ≤ 0.60: Moderate agreement
        - 0.61 ≤ κ ≤ 0.80: Substantial agreement
        - 0.81 ≤ κ ≤ 1.00: Almost perfect agreement

        Args:
            annotator1: Ratings from first annotator (list of ints, 0-4)
            annotator2: Ratings from second annotator (list of ints, 0-4)
            min_rating: Minimum rating value (default: 0)
            max_rating: Maximum rating value (default: 4)

        Returns:
            Dict with kappa, observed_agreement, expected_agreement, interpretation
        """
        if len(annotator1) != len(annotator2):
            raise ValueError("Annotators must rate same number of items")

        n = len(annotator1)
        if n == 0:
            return {
                "kappa": 0.0,
                "observed_agreement": 0.0,
                "expected_agreement": 0.0,
                "interpretation": "no_data",
                "n_items": 0,
            }

        # Observed agreement
        agreements = sum(1 for a1, a2 in zip(annotator1, annotator2) if a1 == a2)
        p_o = agreements / n

        # Expected agreement by chance
        # P_e = sum over categories: (freq_a1(cat) / n) * (freq_a2(cat) / n)
        counter1 = Counter(annotator1)
        counter2 = Counter(annotator2)

        p_e = 0.0
        for rating in range(min_rating, max_rating + 1):
            freq1 = counter1.get(rating, 0) / n
            freq2 = counter2.get(rating, 0) / n
            p_e += freq1 * freq2

        # Cohen's Kappa
        if p_e >= 1.0:
            kappa = 0.0
        else:
            kappa = (p_o - p_e) / (1.0 - p_e)

        # Interpretation
        if kappa < 0:
            interpretation = "no_agreement"
        elif kappa <= 0.20:
            interpretation = "slight"
        elif kappa <= 0.40:
            interpretation = "fair"
        elif kappa <= 0.60:
            interpretation = "moderate"
        elif kappa <= 0.80:
            interpretation = "substantial"
        else:
            interpretation = "almost_perfect"

        return {
            "kappa": float(kappa),
            "observed_agreement": float(p_o),
            "expected_agreement": float(p_e),
            "interpretation": interpretation,
            "n_items": n,
            "n_agreements": agreements,
        }

    def krippendorffs_alpha(
        self, annotations: dict[str, list[int | None]], metric: str = "ordinal"
    ) -> dict[str, float]:
        """
        Compute Krippendorff's Alpha for multiple annotators.

        Handles missing data and different metric types (nominal, ordinal, interval, ratio).

        α = 1 - (D_o / D_e)
        where:
        - D_o = observed disagreement
        - D_e = expected disagreement by chance

        Interpretation:
        - α < 0: No agreement
        - 0 ≤ α ≤ 0.67: Unreliable
        - 0.67 < α ≤ 0.80: Tentative conclusions
        - α > 0.80: Reliable

        Args:
            annotations: Dict mapping annotator_id -> list of ratings (can include None for missing)
            metric: Type of metric - "nominal"|"ordinal"|"interval"|"ratio" (default: "ordinal")

        Returns:
            Dict with alpha, observed_disagreement, expected_disagreement, interpretation
        """
        # Collect all items (by index)
        annotator_ids = list(annotations.keys())
        if not annotator_ids:
            return {
                "alpha": 0.0,
                "observed_disagreement": 0.0,
                "expected_disagreement": 0.0,
                "interpretation": "no_data",
                "n_items": 0,
                "n_annotators": 0,
            }

        # Find max length (number of items)
        max_len = max(len(ratings) for ratings in annotations.values())
        if max_len == 0:
            return {
                "alpha": 0.0,
                "observed_disagreement": 0.0,
                "expected_disagreement": 0.0,
                "interpretation": "no_data",
                "n_items": 0,
                "n_annotators": len(annotator_ids),
            }

        # Build item-by-item ratings matrix
        items: list[list[int | None]] = []
        for i in range(max_len):
            item_ratings = []
            for ann_id in annotator_ids:
                if i < len(annotations[ann_id]):
                    item_ratings.append(annotations[ann_id][i])
                else:
                    item_ratings.append(None)
            items.append(item_ratings)

        # Compute disagreement based on metric type
        if metric == "nominal":
            disagreement_func = self._nominal_disagreement
        elif metric == "ordinal":
            disagreement_func = self._ordinal_disagreement
        elif metric == "interval":
            disagreement_func = self._interval_disagreement
        elif metric == "ratio":
            disagreement_func = self._ratio_disagreement
        else:
            raise ValueError(f"Unknown metric: {metric}")

        # Observed disagreement
        d_o = 0.0
        n_pairs = 0

        for item_ratings in items:
            # Filter out None (missing)
            valid_ratings = [r for r in item_ratings if r is not None]
            if len(valid_ratings) < 2:
                continue

            # Sum pairwise disagreements
            for i, r1 in enumerate(valid_ratings):
                for r2 in valid_ratings[i + 1 :]:
                    d_o += disagreement_func(r1, r2)
                    n_pairs += 1

        if n_pairs > 0:
            d_o = d_o / n_pairs

        # Expected disagreement (from marginal distribution)
        all_ratings = [r for ratings in annotations.values() for r in ratings if r is not None]
        if not all_ratings:
            d_e = 1.0
        else:
            rating_counts = Counter(all_ratings)
            total = len(all_ratings)

            d_e = 0.0
            for r1, count1 in rating_counts.items():
                for r2, count2 in rating_counts.items():
                    prob1 = count1 / total
                    prob2 = count2 / total
                    d_e += prob1 * prob2 * disagreement_func(r1, r2)

        # Krippendorff's Alpha
        if d_e == 0:
            alpha = 1.0 if d_o == 0 else 0.0
        else:
            alpha = 1.0 - (d_o / d_e)

        # Interpretation
        if alpha < 0:
            interpretation = "no_agreement"
        elif alpha <= 0.67:
            interpretation = "unreliable"
        elif alpha <= 0.80:
            interpretation = "tentative"
        else:
            interpretation = "reliable"

        return {
            "alpha": float(alpha),
            "observed_disagreement": float(d_o),
            "expected_disagreement": float(d_e),
            "interpretation": interpretation,
            "n_items": max_len,
            "n_annotators": len(annotator_ids),
            "n_pairs": n_pairs,
            "metric": metric,
        }

    def _nominal_disagreement(self, r1: int, r2: int) -> float:
        """Nominal: 0 if same, 1 if different."""
        return 0.0 if r1 == r2 else 1.0

    def _ordinal_disagreement(self, r1: int, r2: int) -> float:
        """Ordinal: squared difference."""
        return float((r1 - r2) ** 2)

    def _interval_disagreement(self, r1: int, r2: int) -> float:
        """Interval: squared difference (same as ordinal for integers)."""
        return float((r1 - r2) ** 2)

    def _ratio_disagreement(self, r1: int, r2: int) -> float:
        """Ratio: squared relative difference."""
        if r1 == 0 and r2 == 0:
            return 0.0
        if r1 == 0 or r2 == 0:
            return 1.0
        ratio = (r1 - r2) / ((r1 + r2) / 2)
        return float(ratio**2)

    def fleiss_kappa(
        self, annotations: dict[str, list[int]], min_rating: int = 0, max_rating: int = 4
    ) -> dict[str, float]:
        """
        Compute Fleiss' Kappa for multiple annotators (categorical).

        Similar to Cohen's Kappa but for multiple annotators.

        Args:
            annotations: Dict mapping annotator_id -> list of ratings
            min_rating: Minimum rating value
            max_rating: Maximum rating value

        Returns:
            Dict with kappa, interpretation, n_items, n_annotators
        """
        annotator_ids = list(annotations.keys())
        if not annotator_ids:
            return {"kappa": 0.0, "interpretation": "no_data", "n_items": 0, "n_annotators": 0}

        max_len = max(len(ratings) for ratings in annotations.values())
        if max_len == 0:
            return {
                "kappa": 0.0,
                "interpretation": "no_data",
                "n_items": 0,
                "n_annotators": len(annotator_ids),
            }

        # Build item-by-rating matrix
        n_items = max_len
        n_annotators = len(annotator_ids)
        n_categories = max_rating - min_rating + 1

        # Count ratings per item per category
        item_category_counts: list[dict[int, int]] = []
        for i in range(n_items):
            category_counts: dict[int, int] = defaultdict(int)
            for ann_id in annotator_ids:
                if i < len(annotations[ann_id]):
                    rating = annotations[ann_id][i]
                    if min_rating <= rating <= max_rating:
                        category_counts[rating] += 1
            item_category_counts.append(category_counts)

        # Compute P_j (proportion of assignments to category j)
        total_assignments = n_items * n_annotators
        p_j = defaultdict(float)
        for item_counts in item_category_counts:
            for category, count in item_counts.items():
                p_j[category] += count
        for category in p_j:
            p_j[category] /= total_assignments

        # Compute P_i (proportion of agreement for item i)
        p_i_list = []
        for item_counts in item_category_counts:
            total_for_item = sum(item_counts.values())
            if total_for_item == 0:
                p_i_list.append(0.0)
                continue

            # Agreement = sum of n_ij * (n_ij - 1) / (n * (n - 1))
            agreement = 0.0
            for count in item_counts.values():
                if total_for_item > 1:
                    agreement += count * (count - 1) / (total_for_item * (total_for_item - 1))
            p_i_list.append(agreement)

        p_bar = sum(p_i_list) / n_items if p_i_list else 0.0

        # Expected agreement
        p_e = sum(p_j[c] ** 2 for c in p_j)

        # Fleiss' Kappa
        if p_e >= 1.0:
            kappa = 0.0
        else:
            kappa = (p_bar - p_e) / (1.0 - p_e)

        # Interpretation (same as Cohen's)
        if kappa < 0:
            interpretation = "no_agreement"
        elif kappa <= 0.20:
            interpretation = "slight"
        elif kappa <= 0.40:
            interpretation = "fair"
        elif kappa <= 0.60:
            interpretation = "moderate"
        elif kappa <= 0.80:
            interpretation = "substantial"
        else:
            interpretation = "almost_perfect"

        return {
            "kappa": float(kappa),
            "p_bar": float(p_bar),
            "p_e": float(p_e),
            "interpretation": interpretation,
            "n_items": n_items,
            "n_annotators": n_annotators,
            "n_categories": n_categories,
        }

    def intra_annotator_agreement(
        self,
        annotator_id: str,
        annotations1: list[int],
        annotations2: list[int],
        time_interval_days: float | None = None,
    ) -> dict[str, Any]:
        """
        Compute intra-annotator agreement (stability over time).

        Measures how consistent an annotator is with themselves when rating
        the same items at different times.

        Args:
            annotator_id: Identifier for annotator
            annotations1: First set of ratings
            annotations2: Second set of ratings (same items, different time)
            time_interval_days: Time between annotations (optional)

        Returns:
            Dict with agreement metrics and interpretation
        """
        if len(annotations1) != len(annotations2):
            raise ValueError("Both annotation sets must have same length")

        # Use Cohen's Kappa for two sets from same annotator
        kappa_result = self.cohens_kappa(annotations1, annotations2)

        # Additional stability metrics
        exact_agreement = sum(1 for a1, a2 in zip(annotations1, annotations2) if a1 == a2)
        within_one = sum(1 for a1, a2 in zip(annotations1, annotations2) if abs(a1 - a2) <= 1)

        result = {
            "annotator_id": annotator_id,
            "kappa": kappa_result["kappa"],
            "interpretation": kappa_result["interpretation"],
            "exact_agreement": exact_agreement,
            "exact_agreement_rate": exact_agreement / len(annotations1) if annotations1 else 0.0,
            "within_one_agreement": within_one,
            "within_one_rate": within_one / len(annotations1) if annotations1 else 0.0,
            "n_items": len(annotations1),
            "time_interval_days": time_interval_days,
        }

        # Stability interpretation
        if kappa_result["kappa"] >= 0.80:
            result["stability"] = "high"
        elif kappa_result["kappa"] >= 0.60:
            result["stability"] = "moderate"
        else:
            result["stability"] = "low"

        return result

    def annotator_confidence_analysis(
        self,
        annotations: list[dict[str, Any]],  # [{rating, confidence, ...}, ...]
    ) -> dict[str, Any]:
        """
        Analyze relationship between annotator confidence and agreement.

        Best practice: High confidence should correlate with high agreement.

        Args:
            annotations: List of annotation dicts with 'rating' and 'confidence' fields

        Returns:
            Dict with confidence-agreement correlation analysis
        """
        if not annotations:
            return {"n_annotations": 0, "mean_confidence": 0.0, "correlation": 0.0}

        confidences = [ann.get("confidence", 0.5) for ann in annotations]
        ratings = [ann.get("rating", 0) for ann in annotations]

        mean_confidence = np.mean(confidences) if confidences else 0.0

        # Correlation between confidence and rating variance (lower variance = higher agreement)
        # For now, simple analysis
        result = {
            "n_annotations": len(annotations),
            "mean_confidence": float(mean_confidence),
            "confidence_std": float(np.std(confidences)) if confidences else 0.0,
            "rating_mean": float(np.mean(ratings)) if ratings else 0.0,
            "rating_std": float(np.std(ratings)) if ratings else 0.0,
        }

        # TODO: Add correlation computation when we have multi-annotator data
        result["correlation"] = 0.0  # Placeholder

        return result


__all__ = ["InterAnnotatorAgreement"]
