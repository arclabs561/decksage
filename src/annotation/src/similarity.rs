//! Similarity computation with sideboard and temporal signals
//!
//! Integrates multiple similarity signals using rank-fusion:
//! - Embedding similarity
//! - Jaccard co-occurrence
//! - Sideboard co-occurrence
//! - Temporal trends
//! - Functional tags (if available)

use std::collections::{HashMap, HashSet};

use anyhow::Result;
use rank_fusion::RrfConfig;
use rank_refine::simd::cosine as cosine_sim;

use crate::candidate::Candidate;
use crate::gnn::GNNEmbedder;
use crate::signals::{SideboardSignal, TemporalSignal};

/// Similarity function that combines multiple signals
pub struct SimilarityFunction {
    /// Embedding similarity (card -> embedding vector)
    pub embeddings: Option<HashMap<String, Vec<f32>>>,
    /// Jaccard co-occurrence (card -> set of neighbors)
    pub jaccard_adj: Option<HashMap<String, std::collections::HashSet<String>>>,
    /// Sideboard signal
    pub sideboard: Option<SideboardSignal>,
    /// Temporal signal
    pub temporal: Option<TemporalSignal>,
    /// GNN embeddings (learned graph representations)
    pub gnn: Option<GNNEmbedder>,
    /// RRF configuration
    pub rrf_config: RrfConfig,
}

impl SimilarityFunction {
    /// Find similar cards to query
    pub fn similar(&self, query: &str, k: usize) -> Result<Vec<Candidate>> {
        let mut sources: Vec<(&str, Vec<(String, f32)>)> = Vec::new();

        // Embedding similarity
        if let Some(embeddings) = &self.embeddings {
            if let Some(query_emb) = embeddings.get(query) {
                let mut scored: Vec<(String, f32)> = embeddings
                    .iter()
                    .filter(|(card, _)| *card != query)
                    .map(|(card, emb)| {
                        let score = cosine_sim(query_emb, emb);
                        (card.clone(), score)
                    })
                    .collect();
                scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
                scored.truncate(k * 2); // Get more for fusion
                sources.push(("embedding", scored));
            }
        }

        // Jaccard co-occurrence
        if let Some(adj) = &self.jaccard_adj {
            if let Some(neighbors) = adj.get(query) {
                let mut scored: Vec<(String, f32)> = neighbors
                    .iter()
                    .map(|card| {
                        // Simple: 1.0 if co-occurs, could compute actual Jaccard
                        (card.clone(), 1.0)
                    })
                    .collect();
                scored.truncate(k * 2);
                sources.push(("jaccard", scored));
            }
        }

        // Sideboard signal
        if let Some(sb) = &self.sideboard {
            let mut scored: Vec<(String, f32)> = sb
                .cooccurrence
                .get(query)
                .map(|others| {
                    others
                        .iter()
                        .map(|(card, freq)| (card.clone(), *freq))
                        .collect()
                })
                .unwrap_or_default();
            scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
            scored.truncate(k);
            if !scored.is_empty() {
                sources.push(("sideboard", scored));
            }
        }

        // Temporal signal
        if let Some(temp) = &self.temporal {
            // Get candidates from recent months
            let mut scored: Vec<(String, f32)> = Vec::new();
            
            // Get all unique cards from monthly co-occurrence
            let mut all_cards = HashSet::new();
            for month_data in temp.monthly_cooccurrence.values() {
                if let Some(query_data) = month_data.get(query) {
                    for card in query_data.keys() {
                        all_cards.insert(card.clone());
                    }
                }
            }
            
            // Score each candidate
            for card in all_cards {
                let score = temp.similarity(query, &card);
                if score > 0.0 {
                    scored.push((card, score));
                }
            }
            
            scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
            scored.truncate(k);
            if !scored.is_empty() {
                sources.push(("temporal", scored));
            }
        }

        // GNN signal (learned graph embeddings)
        if let Some(gnn) = &self.gnn {
            let similar = gnn.most_similar(query, k * 2);
            if !similar.is_empty() {
                sources.push(("gnn", similar));
            }
        }

        // Fuse using rank-fusion
        if sources.is_empty() {
            return Ok(vec![]);
        }

        crate::generate_candidates_fused(query, &sources, self.rrf_config)
    }
}

// Using rank_refine::simd::cosine for SIMD-accelerated similarity computation

