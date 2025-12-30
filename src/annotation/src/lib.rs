//! DeckSage Annotation Tool
//!
//! Hand annotation system for expanding test sets with proper statistical rigor.
//! Integrates with rank-fusion and rank-refine for candidate generation and ranking.

use std::collections::HashMap;
use std::path::Path;

use anyhow::{Context, Result};
use rank_fusion::RrfConfig;
use serde::{Deserialize, Serialize};

pub mod candidate;
pub mod eval;
pub mod gnn;
pub mod query;
pub mod signals;
pub mod similarity;
pub mod test_set;

pub use candidate::*;
pub use eval::*;
pub use query::*;
pub use signals::*;
pub use similarity::*;
pub use test_set::*;

/// Annotation batch metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatchMetadata {
    pub game: String,
    pub batch_id: String,
    pub num_queries: usize,
    pub created: String,
    pub target_total: usize,
    pub current_total: usize,
}

/// Annotation task for a single query
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnnotationTask {
    pub query: String,
    pub game: String,
    pub candidates: Vec<Candidate>,
}

/// Generate candidates using rank-fusion to combine multiple sources
/// 
/// Sources can include:
/// - Embedding similarity
/// - Jaccard co-occurrence
/// - Sideboard co-occurrence
/// - Temporal trends
/// - Functional tag similarity
pub fn generate_candidates_fused(
    _query: &str,
    sources: &[(&str, Vec<(String, f32)>)],
    config: RrfConfig,
) -> Result<Vec<Candidate>> {
    if sources.is_empty() {
        return Ok(vec![]);
    }

    // Convert to format expected by rank-fusion
    let lists: Vec<&[(String, f32)]> = sources.iter().map(|(_, list)| list.as_slice()).collect();
    let weights: Vec<f32> = vec![1.0; sources.len()];

    // Fuse using RRF
    let fused = rank_fusion::rrf_weighted(&lists, &weights, config)
        .map_err(|e| anyhow::anyhow!("Failed to fuse candidate lists: {}", e))?;

    // Build candidates with source attribution
    let mut candidates: HashMap<String, Candidate> = HashMap::new();

    // Track which sources predicted each candidate
    for (source_name, source_list) in sources.iter() {
        for (card, score) in source_list.iter() {
            let candidate = candidates
                .entry(card.clone())
                .or_insert_with(|| Candidate::new(card.clone(), vec![], HashMap::new()));

            candidate.sources.push(source_name.to_string());
            candidate.scores.insert(source_name.to_string(), *score);
        }
    }

    // Sort by fused score
    let mut result: Vec<Candidate> = fused
        .into_iter()
        .filter_map(|(card, _)| candidates.remove(&card))
        .collect();

    // Sort by number of sources (more sources = higher confidence)
    result.sort_by(|a, b| {
        b.sources.len().cmp(&a.sources.len()).then_with(|| {
            let a_max = a.scores.values().fold(0.0f32, |acc, &v| acc.max(v));
            let b_max = b.scores.values().fold(0.0f32, |acc, &v| acc.max(v));
            b_max
                .partial_cmp(&a_max)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
    });

    Ok(result)
}

/// Refine candidates using rank-refine (reranking with embeddings)
pub fn refine_candidates(
    query_embedding: &[f32],
    candidates: &[(String, &[f32])],
    top_k: Option<usize>,
) -> Vec<(String, f32)> {
    use rank_refine::simd::cosine;

    if candidates.is_empty() {
        return vec![];
    }

    // Compute cosine similarities
    let mut scored: Vec<(String, f32)> = candidates
        .iter()
        .map(|(card, emb)| {
            let score = cosine(query_embedding, emb);
            (card.clone(), score)
        })
        .collect();

    // Sort by score descending
    scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    // Take top k
    if let Some(k) = top_k {
        scored.truncate(k);
    }

    scored
}

/// Create annotation batch
pub fn create_batch(
    game: &str,
    queries: Vec<String>,
    candidate_generator: impl Fn(&str) -> Result<Vec<Candidate>>,
    output_path: &Path,
) -> Result<BatchMetadata> {
    let mut tasks = Vec::new();

    for query in queries {
        let candidates = candidate_generator(&query)
            .with_context(|| format!("Failed to generate candidates for query: {}", query))?;

        tasks.push(AnnotationTask {
            query,
            game: game.to_string(),
            candidates,
        });
    }

    let batch_id = output_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();

    let metadata = BatchMetadata {
        game: game.to_string(),
        batch_id,
        num_queries: tasks.len(),
        created: chrono::Utc::now().to_rfc3339(),
        target_total: 0,  // Will be set by caller
        current_total: 0, // Will be set by caller
    };

    let batch = AnnotationBatch {
        metadata: metadata.clone(),
        instructions: default_instructions(),
        tasks,
    };

    // Write YAML
    let yaml = serde_yaml::to_string(&batch).context("Failed to serialize batch to YAML")?;
    std::fs::write(output_path, yaml)
        .with_context(|| format!("Failed to write batch to: {}", output_path.display()))?;

    Ok(metadata)
}

/// Default annotation instructions
fn default_instructions() -> Instructions {
    Instructions {
        relevance_scale: HashMap::from([
            (
                4,
                "Extremely similar (near substitutes, same function)".to_string(),
            ),
            (
                3,
                "Very similar (often seen together, similar role)".to_string(),
            ),
            (
                2,
                "Somewhat similar (related function or archetype)".to_string(),
            ),
            (1, "Marginally similar (loose connection)".to_string()),
            (
                0,
                "Irrelevant (different function, color, or archetype)".to_string(),
            ),
        ]),
        grading_guidelines: vec![
            "Focus on functional similarity (can they replace each other?)".to_string(),
            "Consider archetype context (do they appear in same decks?)".to_string(),
            "Consider mana cost and card type".to_string(),
            "Add notes for edge cases or interesting patterns".to_string(),
        ],
    }
}

/// Complete annotation batch
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnnotationBatch {
    pub metadata: BatchMetadata,
    pub instructions: Instructions,
    pub tasks: Vec<AnnotationTask>,
}

/// Annotation instructions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Instructions {
    #[serde(rename = "relevance_scale")]
    pub relevance_scale: HashMap<u8, String>,
    #[serde(rename = "grading_guidelines")]
    pub grading_guidelines: Vec<String>,
}
