//! Evaluation framework integration using anno
//!
//! Provides statistical rigor, confidence intervals, and significance testing
//! for card similarity evaluation.

use serde::{Deserialize, Serialize};

use crate::test_set::TestSet;

/// Evaluation metrics with confidence intervals
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvaluationMetrics {
    /// Precision@K with confidence interval
    pub precision_at_k: MetricWithCI,
    /// Recall@K with confidence interval
    pub recall_at_k: MetricWithCI,
    /// nDCG@K with confidence interval
    pub ndcg_at_k: MetricWithCI,
    /// Mean Reciprocal Rank with confidence interval
    pub mrr: MetricWithCI,
    /// Number of queries evaluated
    pub n_queries: usize,
}

/// Metric with confidence interval (inspired by anno's MetricWithCI)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MetricWithCI {
    /// Mean value
    pub mean: f64,
    /// Standard deviation
    pub std_dev: f64,
    /// 95% confidence interval (lower, upper)
    pub ci_95: (f64, f64),
    /// Sample size
    pub n: usize,
}

impl MetricWithCI {
    /// Create from a vector of scores with bootstrap confidence interval
    pub fn from_scores(scores: &[f64], n_bootstrap: usize) -> Self {
        if scores.is_empty() {
            return Self {
                mean: 0.0,
                std_dev: 0.0,
                ci_95: (0.0, 0.0),
                n: 0,
            };
        }

        let mean = scores.iter().sum::<f64>() / scores.len() as f64;
        let variance = scores
            .iter()
            .map(|&x| (x - mean).powi(2))
            .sum::<f64>()
            / scores.len() as f64;
        let std_dev = variance.sqrt();

        // Bootstrap confidence interval
        let mut bootstrap_means = Vec::with_capacity(n_bootstrap);
        for _ in 0..n_bootstrap {
            let sample: Vec<f64> = (0..scores.len())
                .map(|_| {
                    let idx = fastrand::usize(..scores.len());
                    scores[idx]
                })
                .collect();
            let sample_mean = sample.iter().sum::<f64>() / sample.len() as f64;
            bootstrap_means.push(sample_mean);
        }

        bootstrap_means.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let ci_lower = bootstrap_means[(n_bootstrap as f64 * 0.025) as usize];
        let ci_upper = bootstrap_means[(n_bootstrap as f64 * 0.975) as usize];

        Self {
            mean,
            std_dev,
            ci_95: (ci_lower, ci_upper),
            n: scores.len(),
        }
    }

    /// Format for display
    pub fn format(&self, precision: usize) -> String {
        format!(
            "{:.prec$} (95% CI: {:.prec$}, {:.prec$}, n={})",
            self.mean,
            self.ci_95.0,
            self.ci_95.1,
            self.n,
            prec = precision
        )
    }
}

/// Evaluate a similarity function on a test set
pub fn evaluate_similarity(
    test_set: &TestSet,
    similarity_fn: impl Fn(&str, usize) -> Vec<(String, f64)>,
    top_k: usize,
    n_bootstrap: usize,
) -> EvaluationMetrics {
    let mut precision_scores = Vec::new();
    let mut recall_scores = Vec::new();
    let mut ndcg_scores = Vec::new();
    let mut mrr_scores = Vec::new();

    for (query, labels) in &test_set.queries {
        let predictions = similarity_fn(query, top_k * 2); // Get more for recall calculation
        let predictions: Vec<String> = predictions.iter().map(|(card, _)| card.clone()).collect();

        // Get all relevant labels (combining all relevance levels)
        let all_relevant: Vec<String> = labels
            .highly_relevant
            .iter()
            .chain(labels.relevant.iter())
            .chain(labels.somewhat_relevant.iter())
            .cloned()
            .collect();

        let relevant_set: std::collections::HashSet<String> =
            all_relevant.iter().cloned().collect();

        // Precision@K
        let top_k_preds = predictions.iter().take(top_k);
        let relevant_in_top_k = top_k_preds
            .clone()
            .filter(|pred| relevant_set.contains(*pred))
            .count();
        let precision = if top_k > 0 {
            relevant_in_top_k as f64 / top_k as f64
        } else {
            0.0
        };
        precision_scores.push(precision);

        // Recall@K
        let recall = if !all_relevant.is_empty() {
            relevant_in_top_k as f64 / all_relevant.len() as f64
        } else {
            0.0
        };
        recall_scores.push(recall);

        // nDCG@K (simplified - treating all relevant equally)
        let dcg: f64 = predictions
            .iter()
            .take(top_k)
            .enumerate()
            .map(|(rank, pred)| {
                if relevant_set.contains(pred) {
                    1.0 / (rank as f64 + 2.0).ln_1p() // log2(rank+2)
                } else {
                    0.0
                }
            })
            .sum();

        // Ideal DCG (all relevant in top K)
        let ideal_dcg: f64 = (0..all_relevant.len().min(top_k))
            .map(|rank| 1.0 / (rank as f64 + 2.0).ln_1p())
            .sum();

        let ndcg = if ideal_dcg > 0.0 { dcg / ideal_dcg } else { 0.0 };
        ndcg_scores.push(ndcg);

        // MRR (Mean Reciprocal Rank)
        let mrr = predictions
            .iter()
            .position(|pred| relevant_set.contains(pred))
            .map(|rank| 1.0 / (rank + 1) as f64)
            .unwrap_or(0.0);
        mrr_scores.push(mrr);
    }

    EvaluationMetrics {
        precision_at_k: MetricWithCI::from_scores(&precision_scores, n_bootstrap),
        recall_at_k: MetricWithCI::from_scores(&recall_scores, n_bootstrap),
        ndcg_at_k: MetricWithCI::from_scores(&ndcg_scores, n_bootstrap),
        mrr: MetricWithCI::from_scores(&mrr_scores, n_bootstrap),
        n_queries: test_set.queries.len(),
    }
}

/// Format evaluation report
pub fn format_evaluation_report(metrics: &EvaluationMetrics) -> String {
    format!(
        "Evaluation Results (n={} queries)\n\
        ============================================\n\
        Precision@{:2}: {}\n\
        Recall@{:2}:    {}\n\
        nDCG@{:2}:      {}\n\
        MRR:            {}\n",
        metrics.n_queries,
        10, // top_k - could be parameterized
        metrics.precision_at_k.format(4),
        10,
        metrics.recall_at_k.format(4),
        10,
        metrics.ndcg_at_k.format(4),
        metrics.mrr.format(4),
    )
}

