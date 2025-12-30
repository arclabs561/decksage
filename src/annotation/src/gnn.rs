//! Graph Neural Network embeddings for card similarity
//!
//! Provides Rust implementations of GNN models for learning card representations
//! from co-occurrence graphs. Can train from scratch or load pre-trained models.

use std::collections::HashMap;
use std::path::Path;

use anyhow::{Context, Result};
use rank_refine::simd::cosine as cosine_sim;
use serde::{Deserialize, Serialize};

/// GNN model types supported
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum GNNModelType {
    /// Graph Convolutional Network (baseline)
    GCN,
    /// Graph Attention Network (attention-based)
    GAT,
    /// GraphSAGE (inductive learning)
    GraphSAGE,
}

/// GNN embedding model configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GNNConfig {
    pub model_type: GNNModelType,
    pub hidden_dim: usize,
    pub num_layers: usize,
    pub learning_rate: f32,
    pub epochs: usize,
}

impl Default for GNNConfig {
    fn default() -> Self {
        Self {
            model_type: GNNModelType::GCN,
            hidden_dim: 128,
            num_layers: 2,
            learning_rate: 0.01,
            epochs: 100,
        }
    }
}

/// GNN embedder that can train and provide similarity
pub struct GNNEmbedder {
    config: GNNConfig,
    embeddings: HashMap<String, Vec<f32>>,
    node_to_idx: HashMap<String, usize>,
    idx_to_node: HashMap<usize, String>,
}

impl GNNEmbedder {
    /// Create a new GNN embedder with configuration
    pub fn new(config: GNNConfig) -> Self {
        Self {
            config,
            embeddings: HashMap::new(),
            node_to_idx: HashMap::new(),
            idx_to_node: HashMap::new(),
        }
    }

    /// Load pre-trained embeddings from JSON (e.g., from Python PyG training)
    pub fn load_from_json(path: &Path) -> Result<Self> {
        let content = std::fs::read_to_string(path)
            .with_context(|| format!("Failed to read GNN embeddings: {}", path.display()))?;

        #[derive(Deserialize)]
        struct GNNState {
            model_type: String,
            hidden_dim: usize,
            num_layers: usize,
            node_to_idx: HashMap<String, usize>,
            idx_to_node: HashMap<usize, String>,
            embeddings: HashMap<String, Vec<f32>>,
        }

        let state: GNNState = serde_json::from_str(&content)
            .context("Failed to parse GNN embeddings JSON")?;

        let model_type = match state.model_type.as_str() {
            "GCN" => GNNModelType::GCN,
            "GAT" => GNNModelType::GAT,
            "GraphSAGE" => GNNModelType::GraphSAGE,
            _ => GNNModelType::GCN,
        };

        Ok(Self {
            config: GNNConfig {
                model_type,
                hidden_dim: state.hidden_dim,
                num_layers: state.num_layers,
                learning_rate: 0.01,
                epochs: 0,
            },
            embeddings: state.embeddings,
            node_to_idx: state.node_to_idx,
            idx_to_node: state.idx_to_node,
        })
    }

    /// Train GNN on edgelist (future: implement with candle/burn)
    ///
    /// For now, this is a placeholder. Options:
    /// 1. Call out to Python PyG training script
    /// 2. Implement with candle (lightweight, ONNX-compatible)
    /// 3. Implement with burn (full-featured, PyTorch-like)
    pub fn train(&mut self, _edgelist_path: &Path) -> Result<()> {
        // TODO: Implement GNN training in Rust
        // Option 1: Use candle for lightweight training
        // Option 2: Use burn for full-featured training
        // Option 3: Call Python script and load results
        
        anyhow::bail!(
            "GNN training not yet implemented in Rust. \
            Train with Python PyG and load with load_from_json()"
        );
    }

    /// Compute cosine similarity between two card embeddings
    pub fn similarity(&self, card1: &str, card2: &str) -> f32 {
        let emb1 = match self.embeddings.get(card1) {
            Some(e) => e,
            None => return 0.0,
        };
        let emb2 = match self.embeddings.get(card2) {
            Some(e) => e,
            None => return 0.0,
        };

        cosine_sim(emb1, emb2)
    }

    /// Find most similar cards to a query
    pub fn most_similar(&self, query: &str, topn: usize) -> Vec<(String, f32)> {
        let query_emb = match self.embeddings.get(query) {
            Some(e) => e,
            None => return Vec::new(),
        };

        let mut similarities: Vec<(String, f32)> = self
            .embeddings
            .iter()
            .filter(|(card, _)| *card != query)
            .map(|(card, emb)| (card.clone(), cosine_sim(query_emb, emb)))
            .collect();

        similarities.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        similarities.truncate(topn);
        similarities
    }

    /// Get embedding for a card (returns None if not found)
    pub fn get_embedding(&self, card: &str) -> Option<&[f32]> {
        self.embeddings.get(card).map(|v| v.as_slice())
    }

    /// Save embeddings to JSON (for sharing with Python or caching)
    pub fn save_to_json(&self, path: &Path) -> Result<()> {
        #[derive(Serialize)]
        struct GNNState {
            model_type: String,
            hidden_dim: usize,
            num_layers: usize,
            node_to_idx: HashMap<String, usize>,
            idx_to_node: HashMap<usize, String>,
            embeddings: HashMap<String, Vec<f32>>,
        }

        let model_type_str = match self.config.model_type {
            GNNModelType::GCN => "GCN",
            GNNModelType::GAT => "GAT",
            GNNModelType::GraphSAGE => "GraphSAGE",
        };

        let state = GNNState {
            model_type: model_type_str.to_string(),
            hidden_dim: self.config.hidden_dim,
            num_layers: self.config.num_layers,
            node_to_idx: self.node_to_idx.clone(),
            idx_to_node: self.idx_to_node.clone(),
            embeddings: self.embeddings.clone(),
        };

        let json = serde_json::to_string_pretty(&state)
            .context("Failed to serialize GNN embeddings")?;

        std::fs::write(path, json)
            .with_context(|| format!("Failed to write GNN embeddings: {}", path.display()))?;

        Ok(())
    }
}

// Using rank_refine::simd::cosine for SIMD-accelerated similarity computation

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cosine_similarity() {
        use rank_refine::simd::cosine;
        let a = vec![1.0, 0.0, 0.0];
        let b = vec![1.0, 0.0, 0.0];
        assert!((cosine(&a, &b) - 1.0).abs() < 1e-6);

        let a = vec![1.0, 0.0, 0.0];
        let b = vec![0.0, 1.0, 0.0];
        assert!((cosine(&a, &b) - 0.0).abs() < 1e-6);
    }

    #[test]
    fn test_gnn_embedder_similarity() {
        let mut embeddings = HashMap::new();
        embeddings.insert("Lightning Bolt".to_string(), vec![1.0, 0.0, 0.0]);
        embeddings.insert("Chain Lightning".to_string(), vec![0.9, 0.1, 0.0]);
        embeddings.insert("Brainstorm".to_string(), vec![0.0, 0.0, 1.0]);

        let embedder = GNNEmbedder {
            config: GNNConfig::default(),
            embeddings,
            node_to_idx: HashMap::new(),
            idx_to_node: HashMap::new(),
        };

        let sim = embedder.similarity("Lightning Bolt", "Chain Lightning");
        assert!(sim > 0.8); // Should be high similarity

        let sim = embedder.similarity("Lightning Bolt", "Brainstorm");
        assert!(sim < 0.5); // Should be low similarity
    }
}

