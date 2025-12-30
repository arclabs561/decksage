//! Candidate generation and management

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

/// Candidate card for annotation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Candidate {
    pub card: String,
    pub sources: Vec<String>,
    pub scores: HashMap<String, f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub relevance: Option<u8>,
    #[serde(default)]
    pub notes: String,
}

impl Candidate {
    pub fn new(card: String, sources: Vec<String>, scores: HashMap<String, f32>) -> Self {
        Self {
            card,
            sources,
            scores,
            relevance: None,
            notes: String::new(),
        }
    }

    /// Check if candidate is fully annotated
    pub fn is_annotated(&self) -> bool {
        self.relevance.is_some()
    }

    /// Get max score across all sources
    pub fn max_score(&self) -> f32 {
        self.scores.values().fold(0.0f32, |acc, &v| acc.max(v))
    }

    /// Get number of sources that predicted this candidate
    pub fn source_count(&self) -> usize {
        self.sources.len()
    }
}
