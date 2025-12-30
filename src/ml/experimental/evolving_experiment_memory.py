#!/usr/bin/env python3
"""
Evolving Experiment Memory (A-Mem Inspired)

Transform experiment log from static append-only to evolving network:

1. Note Construction: Each experiment gets keywords, tags, context
2. Link Generation: Auto-link related experiments
3. Memory Evolution: New experiments update old ones
4. Network Retrieval: Query by concept, not just chronological

This makes experiments truly learn from each other over time.
"""

import builtins
import contextlib
import json
from collections import defaultdict
from pathlib import Path


class EvolvingExperimentMemory:
    """A-Mem inspired experiment memory"""

    def __init__(self, log_file="../../experiments/EXPERIMENT_LOG.jsonl"):
        self.log_file = Path(log_file)
        self.experiments = {}  # Dict for easy updates
        self.links = defaultdict(set)  # Experiment connections
        self.load_and_enrich()

    def load_and_enrich(self):
        """Load experiments and add A-Mem structure"""

        raw_experiments = []
        with open(self.log_file) as f:
            for line in f:
                if line.strip():
                    with contextlib.suppress(builtins.BaseException):
                        raw_experiments.append(json.loads(line))

        print(f"Loaded {len(raw_experiments)} experiments")

        # Enrich each with A-Mem structure
        for exp in raw_experiments:
            exp_id = exp.get("experiment_id")
            if not exp_id:
                continue

            # Add A-Mem attributes if missing
            if "keywords" not in exp:
                exp["keywords"] = self._extract_keywords(exp)

            if "tags" not in exp:
                exp["tags"] = self._extract_tags(exp)

            if "context" not in exp:
                exp["context"] = self._generate_context(exp)

            if "links" not in exp:
                exp["links"] = []

            self.experiments[exp_id] = exp

        # Generate links
        self._generate_all_links()

        print("Enriched with keywords, tags, context")
        print(f"Generated {sum(len(links) for links in self.links.values())} links")

    def _extract_keywords(self, exp):
        """Extract keywords from experiment (simple version)"""
        keywords = []

        method = exp.get("method", "").lower()

        # Extract key terms
        if "jaccard" in method:
            keywords.append("jaccard")
        if "node2vec" in method:
            keywords.append("node2vec")
        if "land" in method or "filter" in method:
            keywords.append("land_filtering")
        if "cluster" in method:
            keywords.append("clustering")
        if "archetype" in method:
            keywords.append("archetype")
        if "meta" in method or "stat" in method:
            keywords.append("meta_statistics")

        # Add phase as keyword
        if exp.get("phase"):
            keywords.append(exp["phase"])

        return keywords[:5]  # Top 5

    def _extract_tags(self, exp):
        """Extract categorical tags"""
        tags = []

        # Performance tags
        p10 = exp.get("results", {}).get("p10", 0)
        if p10 > 0.15:
            tags.append("high_performance")
        elif p10 > 0.10:
            tags.append("moderate_performance")
        elif p10 > 0:
            tags.append("low_performance")
        else:
            tags.append("failed")

        # Method tags
        method = exp.get("method", "").lower()
        if "jaccard" in method:
            tags.append("similarity_method")
        if "node2vec" in method or "embedding" in method:
            tags.append("embedding_method")
        if "ensemble" in method:
            tags.append("ensemble_method")

        # Insight tags
        if exp.get("learnings"):
            tags.append("has_learnings")

        return tags

    def _generate_context(self, exp):
        """Generate rich context description"""

        method = exp.get("method", "Unknown")
        hypothesis = exp.get("hypothesis", "")
        result = exp.get("results", {}).get("p10", 0)

        context = f"{method}"

        if hypothesis:
            context += f" testing if {hypothesis[:50]}"

        if result > 0:
            context += f" achieved P@10={result:.3f}"
        else:
            context += " failed to produce results"

        # Add key insight if available
        learnings = exp.get("learnings", [])
        if learnings and isinstance(learnings, list) and learnings:
            context += f". Key insight: {learnings[0][:50]}"

        return context

    def _generate_all_links(self):
        """Generate links between related experiments (A-Mem style)"""

        list(self.experiments.values())

        # For each experiment, find related ones
        for exp_id, exp in self.experiments.items():
            exp_keywords = set(exp.get("keywords", []))
            exp_phase = exp.get("phase", "")

            # Find experiments with overlapping keywords or same phase
            for other_id, other_exp in self.experiments.items():
                if other_id == exp_id:
                    continue

                other_keywords = set(other_exp.get("keywords", []))
                other_phase = other_exp.get("phase", "")

                # Link if:
                # - Share 2+ keywords
                # - Same phase
                # - One builds on other (explicit)

                keyword_overlap = len(exp_keywords & other_keywords)

                if keyword_overlap >= 2 or exp_phase == other_phase:
                    self.links[exp_id].add(other_id)
                    exp["links"].append(other_id)

    def evolve_related_memories(self, new_exp_id):
        """
        A-Mem principle: New experiment updates related old experiments.

        When exp_037 finds "clustering works", update exp_021's context.
        """

        new_exp = self.experiments.get(new_exp_id)
        if not new_exp:
            return

        new_learnings = new_exp.get("learnings", [])
        if not new_learnings:
            return

        # Find linked experiments
        related_ids = self.links.get(new_exp_id, set())

        for related_id in related_ids:
            related_exp = self.experiments.get(related_id)
            if not related_exp:
                continue

            # Evolve: Add cross-reference to learnings
            if "evolved_by" not in related_exp:
                related_exp["evolved_by"] = []

            related_exp["evolved_by"].append(
                {
                    "from_experiment": new_exp_id,
                    "new_insight": new_learnings[0] if new_learnings else "",
                }
            )

    def query_by_concept(self, concept):
        """Retrieve experiments by concept (not chronological)"""

        matches = []

        for exp in self.experiments.values():
            keywords = exp.get("keywords", [])
            tags = exp.get("tags", [])
            context = exp.get("context", "")

            if concept in keywords or concept in tags or concept.lower() in context.lower():
                matches.append(exp)

        return matches

    def save_evolved_log(self, output_file="../../experiments/EXPERIMENT_LOG_EVOLVED.jsonl"):
        """Save evolved experiment log"""

        with open(output_file, "w") as f:
            for exp in self.experiments.values():
                f.write(json.dumps(exp) + "\n")

        print(f"✓ Saved evolved log: {output_file}")


def main():
    print("=" * 60)
    print("Evolving Experiment Memory (A-Mem Inspired)")
    print("=" * 60)

    memory = EvolvingExperimentMemory()

    # Show enrichment
    sample_exp = next(iter(memory.experiments.values()))
    print("\nSample experiment after enrichment:")
    print(f"  ID: {sample_exp.get('experiment_id')}")
    print(f"  Keywords: {sample_exp.get('keywords', [])}")
    print(f"  Tags: {sample_exp.get('tags', [])}")
    print(f"  Context: {sample_exp.get('context', '')[:100]}...")
    print(f"  Links: {len(sample_exp.get('links', []))}")

    # Show network
    print("\nExperiment network:")
    for exp_id, links in list(memory.links.items())[:5]:
        print(f"  {exp_id} → {len(links)} related experiments")

    # Query by concept
    print("\nConcept-based retrieval:")
    jaccard_exps = memory.query_by_concept("jaccard")
    print(f"  'jaccard' concept: {len(jaccard_exps)} experiments")

    clustering_exps = memory.query_by_concept("clustering")
    print(f"  'clustering' concept: {len(clustering_exps)} experiments")

    failed_exps = [e for e in memory.experiments.values() if "failed" in e.get("tags", [])]
    print(f"  Failed experiments: {len(failed_exps)}")

    # Save
    memory.save_evolved_log()

    print(f"\n{'=' * 60}")
    print("A-Mem Principles Applied")
    print("=" * 60)
    print("Experiments now:")
    print("  ✓ Have structured attributes (keywords, tags, context)")
    print("  ✓ Are linked in a network")
    print("  ✓ Can be queried by concept")
    print("  ✓ Ready for evolution")


if __name__ == "__main__":
    main()
