//! DeckSage Annotation CLI
//!
//! Hand annotation tool for expanding test sets with proper statistical rigor.

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use decksage_annotation::{
    create_batch, evaluate_similarity, format_evaluation_report, load_test_set, merge_annotations,
    save_test_set, AnnotationBatch, Candidate, QueryGenerator, QueryStrategy,
};

#[derive(Parser)]
#[command(name = "decksage-annotate")]
#[command(about = "Hand annotation tool for test set expansion")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Generate annotation batch
    Generate {
        /// Game (magic, pokemon, yugioh)
        #[arg(long)]
        game: String,
        /// Target number of queries
        #[arg(long)]
        target: usize,
        /// Current number of queries
        #[arg(long)]
        current: usize,
        /// Pairs CSV file
        #[arg(long)]
        pairs: PathBuf,
        /// Existing test set to exclude queries from
        #[arg(long)]
        test_set: Option<PathBuf>,
        /// Output YAML file
        #[arg(long)]
        output: PathBuf,
        /// Random seed
        #[arg(long, default_value_t = 42)]
        seed: u64,
    },
    /// Evaluate similarity function on test set
    Eval {
        /// Test set JSON file
        #[arg(long)]
        test_set: PathBuf,
        /// Top K for evaluation
        #[arg(long, default_value_t = 10)]
        top_k: usize,
        /// Number of bootstrap samples for CI
        #[arg(long, default_value_t = 1000)]
        n_bootstrap: usize,
        /// Similarity function (placeholder - would need actual implementation)
        #[arg(long, default_value = "fusion")]
        method: String,
    },
    /// Grade and validate annotations
    Grade {
        /// Annotation YAML file
        #[arg(long)]
        input: PathBuf,
    },
    /// Merge annotations into test set
    Merge {
        /// Annotation YAML file
        #[arg(long)]
        input: PathBuf,
        /// Test set JSON file
        #[arg(long)]
        test_set: PathBuf,
        /// Output test set JSON (default: overwrite input)
        #[arg(long)]
        output: Option<PathBuf>,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Generate {
            game,
            target,
            current,
            pairs,
            test_set,
            output,
            seed,
        } => {
            let n_new = target.saturating_sub(current);
            if n_new == 0 {
                println!("✓ Already have {current} queries, no expansion needed");
                return Ok(());
            }

            println!("📋 Generating {n_new} new queries for {game}...");

            // Load existing queries to exclude
            let exclude: HashSet<String> = if let Some(ts_path) = &test_set {
                let ts = load_test_set(ts_path)?;
                ts.queries.keys().cloned().collect()
            } else {
                HashSet::new()
            };

            // Build degree map from pairs CSV
            let degree_map = build_degree_map(&pairs)?;
            let query_gen = QueryGenerator::new(degree_map);

            // Sample queries
            let queries = query_gen.sample(n_new, QueryStrategy::Stratified, &exclude, seed)?;

            // Generate candidates for each query
            println!("🔍 Generating candidates for {} queries...", queries.len());

            // Load signals
            let decks_path = pairs.parent()
                .and_then(|p| p.parent())
                .and_then(|p| p.join("data/processed/decks_with_metadata.jsonl").exists().then_some(p.join("data/processed/decks_with_metadata.jsonl")))
                .or_else(|| {
                    // Try relative path
                    Some(PathBuf::from("../../data/processed/decks_with_metadata.jsonl"))
                });

            let sideboard_signal = if let Some(ref dp) = decks_path {
                if dp.exists() {
                    Some(decksage_annotation::compute_sideboard_signal(dp, 5)?)
                } else {
                    None
                }
            } else {
                None
            };

            let temporal_signal = if let Some(ref dp) = decks_path {
                if dp.exists() {
                    Some(decksage_annotation::compute_temporal_signal(dp, 20)?)
                } else {
                    None
                }
            } else {
                None
            };

            let candidate_generator = move |query: &str| -> Result<Vec<Candidate>> {
                use decksage_annotation::SimilarityFunction;
                use rank_fusion::RrfConfig;

                // Build similarity function with available signals
                let sim_fn = SimilarityFunction {
                    embeddings: None, // TODO: Load embeddings
                    jaccard_adj: None, // TODO: Load from pairs CSV
                    sideboard: sideboard_signal.clone(),
                    temporal: temporal_signal.clone(),
                    gnn: None, // TODO: Load GNN embeddings from JSON
                    rrf_config: RrfConfig::default(),
                };

                sim_fn.similar(query, 20)
            };

            let metadata = create_batch(&game, queries, candidate_generator, &output)?;
            println!("✓ Created annotation batch: {}", output.display());
            println!("   Queries: {}", metadata.num_queries);
        }
        Commands::Eval {
            test_set,
            top_k,
            n_bootstrap,
            method: _method,
        } => {
            let ts = load_test_set(&test_set)?;
            println!("📊 Evaluating on {} queries...", ts.queries.len());

            // Placeholder similarity function - would need actual implementation
            // that calls Python API or loads embeddings
            let similarity_fn = |_query: &str, _k: usize| -> Vec<(String, f64)> {
                // TODO: Integrate with actual similarity API
                // For now, return empty results
                vec![]
            };

            let metrics = evaluate_similarity(&ts, similarity_fn, top_k, n_bootstrap);
            println!("\n{}", format_evaluation_report(&metrics));
        }
        Commands::Grade { input } => {
            let content = std::fs::read_to_string(&input)
                .with_context(|| format!("Failed to read: {}", input.display()))?;
            let batch: AnnotationBatch = serde_yaml::from_str(&content)
                .with_context(|| format!("Failed to parse YAML: {}", input.display()))?;

            let mut total_candidates = 0;
            let mut graded_candidates = 0;
            let mut relevance_dist: HashMap<u8, usize> = HashMap::new();
            let mut errors = Vec::new();

            for task in &batch.tasks {
                for candidate in &task.candidates {
                    total_candidates += 1;
                    if let Some(rel) = candidate.relevance {
                        graded_candidates += 1;
                        if rel <= 4 {
                            *relevance_dist.entry(rel).or_insert(0) += 1;
                        } else {
                            errors.push(format!(
                                "{}: Invalid relevance {} (must be 0-4)",
                                task.query, rel
                            ));
                        }
                    }
                }
            }

            println!("\n📊 Annotation Statistics:");
            println!("   Total queries: {}", batch.tasks.len());
            println!("   Total candidates: {}", total_candidates);
            println!("   Graded: {}", graded_candidates);
            println!("   Ungraded: {}", total_candidates - graded_candidates);
            println!(
                "   Completion rate: {:.1}%",
                100.0 * (graded_candidates as f32 / total_candidates as f32)
            );

            println!("\n📈 Relevance Distribution:");
            for rel in 0..=4 {
                let count = relevance_dist.get(&rel).copied().unwrap_or(0);
                println!("   {}: {} candidates", rel, count);
            }

            if !errors.is_empty() {
                println!("\n⚠️  Validation Errors ({}):", errors.len());
                for error in errors.iter().take(10) {
                    println!("   - {}", error);
                }
                if errors.len() > 10 {
                    println!("   ... and {} more", errors.len() - 10);
                }
            }

            if graded_candidates < total_candidates {
                println!(
                    "\n❌ Incomplete: {} candidates still need grading",
                    total_candidates - graded_candidates
                );
                std::process::exit(1);
            } else if !errors.is_empty() {
                println!("\n⚠️  Has validation errors, but all candidates graded");
                std::process::exit(1);
            } else {
                println!("\n✓ All annotations complete and valid!");
            }
        }
        Commands::Merge {
            input,
            test_set,
            output,
        } => {
            let content = std::fs::read_to_string(&input)
                .with_context(|| format!("Failed to read: {}", input.display()))?;
            let batch: AnnotationBatch = serde_yaml::from_str(&content)
                .with_context(|| format!("Failed to parse YAML: {}", input.display()))?;

            let mut ts = load_test_set(&test_set)?;
            ts = merge_annotations(&batch, ts)?;

            let output_path = output.unwrap_or(test_set);
            save_test_set(&mut ts, &output_path)?;

            println!("✓ Merged annotations into: {}", output_path.display());
            println!("   Total queries: {}", ts.queries.len());
        }
    }

    Ok(())
}

fn build_degree_map(pairs_csv: &PathBuf) -> Result<HashMap<String, usize>> {
    let mut reader = csv::Reader::from_path(pairs_csv)
        .with_context(|| format!("Failed to open pairs CSV: {}", pairs_csv.display()))?;

    let mut degree_map: HashMap<String, usize> = HashMap::new();

    for result in reader.records() {
        let record = result.context("Failed to read CSV record")?;
        if record.len() < 2 {
            continue;
        }

        let card1 = record.get(0).unwrap_or("").to_string();
        let card2 = record.get(1).unwrap_or("").to_string();

        *degree_map.entry(card1).or_insert(0) += 1;
        *degree_map.entry(card2).or_insert(0) += 1;
    }

    Ok(degree_map)
}
