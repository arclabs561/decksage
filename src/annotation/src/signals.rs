//! Similarity signals: sideboard co-occurrence and temporal trends
//!
//! Extracts implicit signals from deck data:
//! - Sideboard patterns (cards that appear together in sideboards)
//! - Temporal trends (cards that rise/fall together over time)

use std::collections::{HashMap, HashSet};
use std::path::Path;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Compute sideboard signal from deck JSONL
pub fn compute_sideboard_signal(
    decks_jsonl: &Path,
    min_decks: usize,
) -> Result<SideboardSignal> {
    compute_sideboard_signal_impl(decks_jsonl, min_decks)
}

/// Sideboard co-occurrence signal
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SideboardSignal {
    /// Card -> co-occurring card -> frequency (0-1)
    pub cooccurrence: HashMap<String, HashMap<String, f32>>,
    /// Card -> flexibility score (appears in both MB and SB)
    pub flexibility: HashMap<String, f32>,
}

impl SideboardSignal {
    /// Compute sideboard similarity between two cards
    pub fn similarity(&self, query: &str, candidate: &str) -> f32 {
        self.cooccurrence
            .get(query)
            .and_then(|others| others.get(candidate))
            .copied()
            .unwrap_or(0.0)
    }

    /// Get flexibility score (higher = appears in both MB and SB more often)
    pub fn flexibility_score(&self, card: &str) -> f32 {
        self.flexibility.get(card).copied().unwrap_or(0.0)
    }
}

/// Compute sideboard co-occurrence from deck JSONL (internal implementation)
fn compute_sideboard_signal_impl(
    decks_jsonl: &Path,
    min_decks: usize,
) -> Result<SideboardSignal> {
    let content = std::fs::read_to_string(decks_jsonl)
        .with_context(|| format!("Failed to read decks: {}", decks_jsonl.display()))?;

    let mut sideboard_pairs: HashMap<String, HashMap<String, usize>> = HashMap::new();
    let mut card_sb_counts: HashMap<String, usize> = HashMap::new();
    let mut card_mb_counts: HashMap<String, usize> = HashMap::new();
    let mut card_both_counts: HashMap<String, usize> = HashMap::new();

    for line in content.lines() {
        if line.trim().is_empty() {
            continue;
        }

        let deck: DeckRecord = serde_json::from_str(line)
            .with_context(|| format!("Failed to parse deck JSON: {}", line))?;

        let mut sb_cards = HashSet::new();
        let mut mb_cards = HashSet::new();

        for card_entry in &deck.cards {
            let card = &card_entry.name;
            let partition = card_entry.partition.as_deref().unwrap_or("Main").to_lowercase();

            if partition == "sideboard" {
                sb_cards.insert(card.clone());
            } else {
                mb_cards.insert(card.clone());
            }
        }

        if sb_cards.len() < 2 {
            continue;
        }

        // Count sideboard co-occurrences
        for card in &sb_cards {
            *card_sb_counts.entry(card.clone()).or_insert(0) += 1;
            for other in &sb_cards {
                if card != other {
                    sideboard_pairs
                        .entry(card.clone())
                        .or_insert_with(HashMap::new)
                        .entry(other.clone())
                        .and_modify(|count| *count += 1)
                        .or_insert(1);
                }
            }
        }

        // Track MB/SB overlap
        for card in mb_cards.intersection(&sb_cards) {
            *card_both_counts.entry(card.clone()).or_insert(0) += 1;
        }
        for card in &mb_cards {
            *card_mb_counts.entry(card.clone()).or_insert(0) += 1;
        }
    }

    // Convert to frequencies
    let mut cooccurrence: HashMap<String, HashMap<String, f32>> = HashMap::new();
    for (card, others) in sideboard_pairs {
        let total = card_sb_counts.get(&card).copied().unwrap_or(0);
        if total < min_decks {
            continue;
        }

        let mut card_cooccur = HashMap::new();
        for (other, count) in others {
            if card_sb_counts.get(&other).copied().unwrap_or(0) >= min_decks {
                let freq = count as f32 / total as f32;
                card_cooccur.insert(other, freq);
            }
        }
        if !card_cooccur.is_empty() {
            cooccurrence.insert(card, card_cooccur);
        }
    }

    // Compute flexibility scores
    let mut flexibility: HashMap<String, f32> = HashMap::new();
    for (card, both_count) in card_both_counts {
        let mb_count = card_mb_counts.get(&card).copied().unwrap_or(0);
        let sb_count = card_sb_counts.get(&card).copied().unwrap_or(0);
        let total = mb_count + sb_count - both_count;
        if total > 0 {
            let flex = both_count as f32 / total as f32;
            flexibility.insert(card, flex);
        }
    }

    Ok(SideboardSignal {
        cooccurrence,
        flexibility,
    })
}

/// Temporal trend signal
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TemporalSignal {
    /// Month (YYYY-MM) -> card -> co-occurring card -> frequency
    pub monthly_cooccurrence: HashMap<String, HashMap<String, HashMap<String, f32>>>,
    /// Trending pairs: (card1, card2, trend_score)
    pub trending_pairs: Vec<(String, String, f32)>,
}

impl TemporalSignal {
    /// Compute temporal similarity (recent months weighted higher)
    pub fn similarity(&self, query: &str, candidate: &str) -> f32 {
        let months: Vec<&String> = self.monthly_cooccurrence.keys().collect();
        let mut sorted_months = months.clone();
        sorted_months.sort();

        // Get last 3 months
        let recent_months: Vec<&String> = sorted_months
            .iter()
            .rev()
            .take(3)
            .copied()
            .collect();

        if recent_months.is_empty() {
            return 0.0;
        }

        // Weighted average by recency
        let mut total_score = 0.0;
        let mut total_weight = 0.0;

        for (i, month) in recent_months.iter().enumerate() {
            let weight = (i + 1) as f32; // More recent = higher weight
            if let Some(month_data) = self.monthly_cooccurrence.get(*month) {
                if let Some(query_data) = month_data.get(query) {
                    if let Some(freq) = query_data.get(candidate) {
                        total_score += freq * weight;
                        total_weight += weight;
                    }
                }
            }
        }

        if total_weight > 0.0 {
            total_score / total_weight
        } else {
            0.0
        }
    }

    /// Get trending boost for a pair
    pub fn trending_boost(&self, card1: &str, card2: &str) -> f32 {
        let pair_key = if card1 < card2 {
            (card1, card2)
        } else {
            (card2, card1)
        };

        self.trending_pairs
            .iter()
            .find(|(c1, c2, _)| {
                (c1 == pair_key.0 && c2 == pair_key.1) || (c1 == pair_key.1 && c2 == pair_key.0)
            })
            .map(|(_, _, trend)| *trend * 0.2) // Scale trend
            .unwrap_or(0.0)
    }
}

/// Compute temporal signal from deck JSONL
pub fn compute_temporal_signal(
    decks_jsonl: &Path,
    min_decks_per_month: usize,
) -> Result<TemporalSignal> {
    compute_temporal_signal_impl(decks_jsonl, min_decks_per_month)
}

/// Compute temporal trends from deck JSONL (internal implementation)
fn compute_temporal_signal_impl(
    decks_jsonl: &Path,
    min_decks_per_month: usize,
) -> Result<TemporalSignal> {
    let content = std::fs::read_to_string(decks_jsonl)
        .with_context(|| format!("Failed to read decks: {}", decks_jsonl.display()))?;

    let mut monthly_decks: HashMap<String, Vec<DeckRecord>> = HashMap::new();

    // Group decks by month
    for line in content.lines() {
        if line.trim().is_empty() {
            continue;
        }

        let deck: DeckRecord = serde_json::from_str(line)
            .with_context(|| format!("Failed to parse deck JSON: {}", line))?;

        let date = parse_deck_date(&deck)?;
        let month_key = date.format("%Y-%m").to_string();
        monthly_decks.entry(month_key).or_insert_with(Vec::new).push(deck);
    }

    // Compute co-occurrence per month
    let mut monthly_cooccurrence: HashMap<String, HashMap<String, HashMap<String, f32>>> =
        HashMap::new();

    for (month, decks) in &monthly_decks {
        if decks.len() < min_decks_per_month {
            continue;
        }

        let mut card_pairs: HashMap<String, HashMap<String, usize>> = HashMap::new();
        let mut card_counts: HashMap<String, usize> = HashMap::new();

        for deck in decks {
            let cards: HashSet<String> = deck.cards.iter().map(|c| c.name.clone()).collect();

            for card in &cards {
                *card_counts.entry(card.clone()).or_insert(0) += 1;
                for other in &cards {
                    if card != other {
                        card_pairs
                            .entry(card.clone())
                            .or_insert_with(HashMap::new)
                            .entry(other.clone())
                            .and_modify(|count| *count += 1)
                            .or_insert(1);
                    }
                }
            }
        }

        // Convert to frequencies
        let mut month_cooccur: HashMap<String, HashMap<String, f32>> = HashMap::new();
        for (card, others) in card_pairs {
            let total = card_counts.get(&card).copied().unwrap_or(0);
            if total < 5 {
                continue;
            }

            let mut card_cooccur = HashMap::new();
            for (other, count) in others {
                if card_counts.get(&other).copied().unwrap_or(0) >= 5 {
                    let freq = count as f32 / total as f32;
                    card_cooccur.insert(other, freq);
                }
            }
            if !card_cooccur.is_empty() {
                month_cooccur.insert(card, card_cooccur);
            }
        }

        if !month_cooccur.is_empty() {
            monthly_cooccurrence.insert(month.clone(), month_cooccur);
        }
    }

    // Find trending pairs
    let trending_pairs = find_trending_pairs(&monthly_cooccurrence, 3)?;

    Ok(TemporalSignal {
        monthly_cooccurrence,
        trending_pairs,
    })
}

/// Find card pairs that are trending (rising co-occurrence)
fn find_trending_pairs(
    monthly_cooccurrence: &HashMap<String, HashMap<String, HashMap<String, f32>>>,
    min_months: usize,
) -> Result<Vec<(String, String, f32)>> {
    let mut months: Vec<&String> = monthly_cooccurrence.keys().collect();
    months.sort();

    if months.len() < min_months {
        return Ok(vec![]);
    }

    let mut pair_trends: HashMap<(String, String), Vec<f32>> = HashMap::new();

    // Track pairs across months
    for month in &months {
        if let Some(month_data) = monthly_cooccurrence.get(*month) {
            for (card1, others) in month_data {
                for (card2, freq) in others {
                    let pair_key = if card1 < card2 {
                        (card1.clone(), card2.clone())
                    } else {
                        (card2.clone(), card1.clone())
                    };
                    pair_trends
                        .entry(pair_key)
                        .or_insert_with(Vec::new)
                        .push(*freq);
                }
            }
        }
    }

    // Compute trends (simple: last - first / num_months)
    let mut trending: Vec<(String, String, f32)> = Vec::new();

    for ((card1, card2), frequencies) in pair_trends {
        if frequencies.len() < min_months {
            continue;
        }

        let trend = (frequencies[frequencies.len() - 1] - frequencies[0])
            / (frequencies.len() - 1) as f32;

        // Only include significant trends
        if trend.abs() > 0.01 {
            trending.push((card1, card2, trend));
        }
    }

    // Sort by trend (descending)
    trending.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal));

    Ok(trending)
}

/// Parse deck date from metadata
fn parse_deck_date(deck: &DeckRecord) -> Result<DateTime<Utc>> {
    // Try various date fields
    let date_str = deck
        .date
        .as_ref()
        .or(deck.scraped_at.as_ref())
        .or(deck.created_at.as_ref())
        .ok_or_else(|| anyhow::anyhow!("No date field found in deck"))?;

    // Try ISO 8601 formats
    let formats = [
        "%Y-%m-%dT%H:%M:%S%.fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ];

    for fmt in &formats {
        if let Ok(dt) = DateTime::parse_from_str(date_str, fmt) {
            return Ok(dt.with_timezone(&Utc));
        }
    }

    // Try chrono's flexible parser
    if let Ok(dt) = date_str.parse::<DateTime<Utc>>() {
        return Ok(dt);
    }

    anyhow::bail!("Failed to parse date: {}", date_str);
}

/// Deck record from JSONL
#[derive(Debug, Deserialize)]
struct DeckRecord {
    #[serde(default)]
    cards: Vec<CardEntry>,
    #[serde(default)]
    date: Option<String>,
    #[serde(default)]
    scraped_at: Option<String>,
    #[serde(default)]
    created_at: Option<String>,
}

#[derive(Debug, Deserialize)]
struct CardEntry {
    name: String,
    #[serde(default)]
    partition: Option<String>,
}

