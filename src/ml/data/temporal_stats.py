#!/usr/bin/env python3
"""
Temporal Statistics Computation

Compute statistical summaries from temporal distributions (monthly_counts).
Based on tsfresh-style feature extraction for time series.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np


@dataclass
class TemporalStats:
    """Temporal distribution statistics."""
    first_seen: datetime
    last_seen: datetime
    total_occurrences: int
    
    # Distribution statistics
    mean_date: datetime | None = None  # Average occurrence time
    median_date: datetime | None = None  # Median occurrence time
    std_days: float | None = None  # Standard deviation in days
    skewness: float | None = None  # Distribution skew (positive = recent bias)
    kurtosis: float | None = None  # Distribution tail heaviness
    
    # Activity patterns
    peak_month: str | None = None  # Month with highest activity
    peak_count: int | None = None  # Count in peak month
    months_active: int = 0  # Number of distinct months
    activity_span_days: int = 0  # Days between first and last
    
    # Percentiles (for trend detection)
    p25_date: datetime | None = None  # 25th percentile
    p75_date: datetime | None = None  # 75th percentile
    
    # Consistency metrics
    consistency_score: float | None = None  # 0-1, higher = more consistent
    volatility: float | None = None  # Coefficient of variation (std/mean)
    recent_trend: float | None = None  # Slope of last 6 months (positive = increasing)


def compute_temporal_stats(
    monthly_counts: dict[str, int],
    first_seen: datetime,
    last_seen: datetime,
    total_occurrences: int,
) -> TemporalStats:
    """
    Compute temporal statistics from monthly_counts histogram.
    
    Args:
        monthly_counts: Dict mapping "YYYY-MM" -> count
        first_seen: First occurrence datetime
        last_seen: Last occurrence datetime
        total_occurrences: Total number of occurrences
    
    Returns:
        TemporalStats object with computed statistics
    """
    if not monthly_counts:
        # Fallback to first/last_seen only
        return TemporalStats(
            first_seen=first_seen,
            last_seen=last_seen,
            total_occurrences=total_occurrences,
            months_active=0,
            activity_span_days=(last_seen - first_seen).days,
        )
    
    # Convert monthly counts to datetime list (weighted by count)
    dates = []
    for month_key, count in monthly_counts.items():
        try:
            month_date = datetime.strptime(month_key, "%Y-%m")
            # Add date count times (weighted)
            dates.extend([month_date] * count)
        except ValueError:
            continue
    
    if not dates:
        return TemporalStats(
            first_seen=first_seen,
            last_seen=last_seen,
            total_occurrences=total_occurrences,
            months_active=len(monthly_counts),
            activity_span_days=(last_seen - first_seen).days,
        )
    
    dates_array = np.array([d.timestamp() for d in dates])
    
    # Basic statistics
    mean_timestamp = np.mean(dates_array)
    median_timestamp = np.median(dates_array)
    std_seconds = np.std(dates_array)
    std_days = std_seconds / 86400.0
    
    mean_date = datetime.fromtimestamp(mean_timestamp)
    median_date = datetime.fromtimestamp(median_timestamp)
    
    # Percentiles
    p25_timestamp = np.percentile(dates_array, 25)
    p75_timestamp = np.percentile(dates_array, 75)
    p25_date = datetime.fromtimestamp(p25_timestamp)
    p75_date = datetime.fromtimestamp(p75_timestamp)
    
    # Skewness and kurtosis
    if len(dates_array) > 1 and std_seconds > 0:
        # Normalized skewness
        skewness = float(np.mean(((dates_array - mean_timestamp) / std_seconds) ** 3))
        # Normalized kurtosis (excess kurtosis)
        kurtosis = float(np.mean(((dates_array - mean_timestamp) / std_seconds) ** 4) - 3.0)
    else:
        skewness = 0.0
        kurtosis = 0.0
    
    # Peak month
    peak_month = max(monthly_counts.items(), key=lambda x: x[1])[0]
    peak_count = monthly_counts[peak_month]
    
    # Consistency score (coefficient of variation)
    counts = list(monthly_counts.values())
    if len(counts) > 1:
        mean_count = np.mean(counts)
        std_count = np.std(counts)
        volatility = float(std_count / mean_count) if mean_count > 0 else 0.0
        # Consistency is inverse of volatility (normalized to 0-1)
        consistency_score = float(1.0 / (1.0 + volatility))
    else:
        volatility = 0.0
        consistency_score = 1.0
    
    # Recent trend (slope of last 6 months)
    sorted_months = sorted(monthly_counts.keys())
    recent_months = sorted_months[-6:] if len(sorted_months) >= 6 else sorted_months
    
    if len(recent_months) >= 2:
        # Linear regression on recent months
        x = np.arange(len(recent_months))
        y = np.array([monthly_counts[m] for m in recent_months])
        
        if len(x) > 1 and np.std(x) > 0:
            # Simple linear regression slope
            recent_trend = float(np.polyfit(x, y, 1)[0])
        else:
            recent_trend = 0.0
    else:
        recent_trend = 0.0
    
    return TemporalStats(
        first_seen=first_seen,
        last_seen=last_seen,
        total_occurrences=total_occurrences,
        mean_date=mean_date,
        median_date=median_date,
        std_days=std_days,
        skewness=skewness,
        kurtosis=kurtosis,
        peak_month=peak_month,
        peak_count=peak_count,
        months_active=len(monthly_counts),
        activity_span_days=(last_seen - first_seen).days,
        p25_date=p25_date,
        p75_date=p75_date,
        consistency_score=consistency_score,
        volatility=volatility,
        recent_trend=recent_trend,
    )


def compute_recency_score(
    monthly_counts: dict[str, int],
    current_date: datetime,
    decay_days: float = 365.0,
) -> float:
    """
    Compute recency-weighted score from monthly counts.
    
    More recent months get higher weight using exponential decay.
    Returns a normalized score (0-1) representing recency-weighted activity.
    
    Args:
        monthly_counts: Dict mapping "YYYY-MM" -> count
        current_date: Current date for recency calculation
        decay_days: Decay half-life in days (default: 365.0 for 1 year)
    
    Returns:
        Recency-weighted score (0-1), where 1.0 = all activity in most recent month
    
    Example:
        >>> counts = {"2024-01": 10, "2024-12": 20}
        >>> score = compute_recency_score(counts, datetime(2025, 1, 1))
        >>> 0.0 <= score <= 1.0
        True
    """
    if not monthly_counts:
        return 0.0
    
    if decay_days <= 0:
        decay_days = 365.0  # Default to 1 year
    
    total_score = 0.0
    total_weight = 0.0
    valid_months = 0
    
    for month_key, count in monthly_counts.items():
        if count <= 0:
            continue  # Skip zero/negative counts
        
        try:
            month_date = datetime.strptime(month_key, "%Y-%m")
            days_ago = (current_date - month_date).days
            
            if days_ago < 0:
                continue  # Skip future dates
            
            # Exponential decay weight (higher for more recent)
            weight = np.exp(-days_ago / decay_days)
            
            total_score += count * weight
            total_weight += weight
            valid_months += 1
        except (ValueError, TypeError):
            continue  # Skip invalid date formats
    
    if total_weight > 0 and valid_months > 0:
        # Compute average recency weight (weighted by count)
        # This represents how recent the activity is on average
        # For single month: returns that month's weight
        # For multiple months: returns count-weighted average of weights
        weighted_avg = total_score / total_weight
        
        # Normalize: compare to what it would be if all activity were in most recent month
        # If all counts were recent (weight=1.0), weighted_avg would equal total_count
        # So normalized = weighted_avg / total_count
        # But this gives us the count-weighted average weight, which is what we want
        total_count = sum(monthly_counts.values())
        if total_count > 0:
            # For single month: weighted_avg = count, so result = count / count = 1.0 (wrong!)
            # We need average weight, not weighted average of counts
            # Solution: compute average weight directly
            avg_weight = total_weight / valid_months  # Simple average of weights
            # But we want count-weighted average, so:
            # avg_weight = sum(count_i * weight_i) / sum(count_i) = total_score / total_count
            count_weighted_avg = total_score / total_count if total_count > 0 else 0.0
            return float(count_weighted_avg)
    
    return 0.0


def compute_consistency(
    monthly_counts: dict[str, int],
) -> float:
    """
    Compute consistency score (0-1, higher = more consistent).
    
    Based on coefficient of variation - lower variation = higher consistency.
    
    Args:
        monthly_counts: Dict mapping "YYYY-MM" -> count
    
    Returns:
        Consistency score (0-1)
    """
    if not monthly_counts:
        return 0.0
    
    counts = list(monthly_counts.values())
    if len(counts) <= 1:
        return 1.0
    
    mean_count = np.mean(counts)
    std_count = np.std(counts)
    
    if mean_count == 0:
        return 0.0
    
    # Coefficient of variation
    cv = std_count / mean_count
    
    # Convert to 0-1 scale (lower CV = higher consistency)
    consistency = 1.0 / (1.0 + cv)
    
    return float(consistency)


def compute_trend(
    monthly_counts: dict[str, int],
    lookback_months: int = 6,
) -> float:
    """
    Compute trend (slope) of recent months.
    
    Positive = increasing, negative = decreasing.
    
    Args:
        monthly_counts: Dict mapping "YYYY-MM" -> count
        lookback_months: Number of recent months to analyze
    
    Returns:
        Trend slope (positive = increasing)
    """
    if not monthly_counts:
        return 0.0
    
    sorted_months = sorted(monthly_counts.keys())
    recent_months = sorted_months[-lookback_months:] if len(sorted_months) >= lookback_months else sorted_months
    
    if len(recent_months) < 2:
        return 0.0
    
    # Linear regression on recent months
    x = np.arange(len(recent_months))
    y = np.array([monthly_counts[m] for m in recent_months])
    
    if len(x) > 1 and np.std(x) > 0:
        # Simple linear regression slope
        slope = np.polyfit(x, y, 1)[0]
        return float(slope)
    
    return 0.0

