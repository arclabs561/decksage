//! Test set management and merging

use std::collections::HashMap;
use std::path::Path;

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

/// Canonical test set format
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestSet {
    #[serde(default = "default_version")]
    pub version: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub game: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub num_queries: Option<usize>,
    pub queries: HashMap<String, RelevanceLabels>,
}

fn default_version() -> String {
    "1.0".to_string()
}

/// Relevance labels for a query
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RelevanceLabels {
    #[serde(default)]
    pub highly_relevant: Vec<String>,
    #[serde(default)]
    pub relevant: Vec<String>,
    #[serde(default)]
    pub somewhat_relevant: Vec<String>,
    #[serde(default)]
    pub marginally_relevant: Vec<String>,
    #[serde(default)]
    pub irrelevant: Vec<String>,
}

impl RelevanceLabels {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn add(&mut self, card: String, relevance: u8) {
        match relevance {
            4 => self.highly_relevant.push(card),
            3 => self.relevant.push(card),
            2 => self.somewhat_relevant.push(card),
            1 => self.marginally_relevant.push(card),
            0 => self.irrelevant.push(card),
            _ => {} // Invalid relevance, ignore
        }
    }
}

/// Load test set from JSON
pub fn load_test_set(path: &Path) -> Result<TestSet> {
    let content = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read test set: {}", path.display()))?;
    let test_set: TestSet = serde_json::from_str(&content)
        .with_context(|| format!("Failed to parse test set JSON: {}", path.display()))?;
    Ok(test_set)
}

/// Save test set to JSON
pub fn save_test_set(test_set: &mut TestSet, path: &Path) -> Result<()> {
    test_set.num_queries = Some(test_set.queries.len());
    let content =
        serde_json::to_string_pretty(test_set).context("Failed to serialize test set to JSON")?;
    std::fs::write(path, content)
        .with_context(|| format!("Failed to write test set: {}", path.display()))?;
    Ok(())
}

/// Merge annotations into test set
pub fn merge_annotations(batch: &crate::AnnotationBatch, mut test_set: TestSet) -> Result<TestSet> {
    for task in &batch.tasks {
        if test_set.queries.contains_key(&task.query) {
            eprintln!("Warning: Query '{}' already exists, skipping", task.query);
            continue;
        }

        let mut labels = RelevanceLabels::new();
        for candidate in &task.candidates {
            if let Some(relevance) = candidate.relevance {
                labels.add(candidate.card.clone(), relevance);
            }
        }

        test_set.queries.insert(task.query.clone(), labels);
    }

    test_set.num_queries = Some(test_set.queries.len());
    Ok(test_set)
}
