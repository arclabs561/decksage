//! Query generation and sampling strategies

use std::collections::{HashMap, HashSet};

use anyhow::Result;
use rand::seq::SliceRandom;
use rand::SeedableRng;

/// Query generation strategy
#[derive(Debug, Clone, Copy)]
pub enum QueryStrategy {
    /// Uniform random sampling
    Random,
    /// High degree nodes only (popular cards)
    Popular,
    /// Stratified: mix of high/medium/low degree
    Stratified,
}

/// Generate queries from graph data
pub struct QueryGenerator {
    degree_map: HashMap<String, usize>,
    cards: Vec<String>,
}

impl QueryGenerator {
    pub fn new(degree_map: HashMap<String, usize>) -> Self {
        let cards: Vec<String> = degree_map.keys().cloned().collect();
        Self { degree_map, cards }
    }

    pub fn sample(
        &self,
        n: usize,
        strategy: QueryStrategy,
        exclude: &HashSet<String>,
        seed: u64,
    ) -> Result<Vec<String>> {
        let mut rng = rand::rngs::StdRng::seed_from_u64(seed);
        let available: Vec<String> = self
            .cards
            .iter()
            .filter(|c| !exclude.contains(*c))
            .cloned()
            .collect();

        if available.is_empty() {
            return Ok(vec![]);
        }

        let n = n.min(available.len());

        match strategy {
            QueryStrategy::Random => {
                let mut selected = available;
                selected.shuffle(&mut rng);
                Ok(selected.into_iter().take(n).collect())
            }
            QueryStrategy::Popular => {
                let mut sorted: Vec<String> = available;
                sorted.sort_by_key(|c| {
                    // Sort descending by degree
                    std::cmp::Reverse(*self.degree_map.get(c).unwrap_or(&0))
                });
                Ok(sorted.into_iter().take(n).collect())
            }
            QueryStrategy::Stratified => {
                let mut sorted: Vec<String> = available;
                sorted.sort_by_key(|c| std::cmp::Reverse(*self.degree_map.get(c).unwrap_or(&0)));

                let n_third = (n / 3).max(1);
                let len = sorted.len();

                let high = sorted[..len / 3].choose_multiple(&mut rng, n_third.min(len / 3));
                let mid =
                    sorted[len / 3..2 * len / 3].choose_multiple(&mut rng, n_third.min(len / 3));
                let low = sorted[2 * len / 3..].choose_multiple(&mut rng, n - 2 * n_third);

                let mut result: Vec<String> = high.chain(mid).chain(low).cloned().collect();
                result.shuffle(&mut rng);
                Ok(result)
            }
        }
    }
}
