#!/usr/bin/env python3
"""
Data Quality Validation

Validates:
1. Source tracking completeness
2. Deck structure validity
3. Card name consistency
4. Format/archetype coverage
5. Partition integrity
6. Duplicate detection
"""

import json
from collections import Counter, defaultdict
from pathlib import Path


def validate_deck_structure(deck: dict) -> list[str]:
    """Validate a single deck's structure."""
    issues = []

    # Required fields
    if not deck.get("deck_id"):
        issues.append("Missing deck_id")
    if not deck.get("format"):
        issues.append("Missing format")

    # Cards validation
    cards = deck.get("cards", [])
    if len(cards) == 0:
        issues.append("Empty deck (no cards)")

    # Check for valid card structure
    for i, card in enumerate(cards):
        if not card.get("name"):
            issues.append(f"Card {i} missing name")
        if card.get("count", 0) <= 0:
            issues.append(f"Card {i} has invalid count: {card.get('count')}")

    # Check for reasonable deck size
    total_cards = sum(c.get("count", 0) for c in cards)
    if total_cards < 20:
        issues.append(f"Suspiciously small deck: {total_cards} cards")
    if total_cards > 250:
        issues.append(f"Suspiciously large deck: {total_cards} cards")

    return issues


def validate_source_tracking(decks: list[dict]) -> dict:
    """Validate source field completeness."""
    results = {
        "total": len(decks),
        "has_source": 0,
        "missing_source": 0,
        "by_source": Counter(),
        "missing_source_samples": [],
    }

    for deck in decks:
        source = deck.get("source")
        if source:
            results["has_source"] += 1
            results["by_source"][source] += 1
        else:
            results["missing_source"] += 1
            if len(results["missing_source_samples"]) < 10:
                results["missing_source_samples"].append(
                    {
                        "deck_id": deck.get("deck_id"),
                        "format": deck.get("format"),
                        "archetype": deck.get("archetype"),
                    }
                )

    return results


def validate_metadata_coverage(decks: list[dict]) -> dict:
    """Validate tournament metadata coverage."""
    results = {
        "total": len(decks),
        "has_player": 0,
        "has_event": 0,
        "has_placement": 0,
        "player_samples": [],
        "event_samples": [],
    }

    for deck in decks:
        if deck.get("player"):
            results["has_player"] += 1
            if len(results["player_samples"]) < 5:
                results["player_samples"].append(
                    {
                        "player": deck["player"],
                        "event": deck.get("event", "N/A"),
                        "archetype": deck.get("archetype", "N/A"),
                    }
                )

        if deck.get("event"):
            results["has_event"] += 1
            if len(results["event_samples"]) < 5:
                results["event_samples"].append(
                    {"event": deck["event"], "format": deck.get("format", "N/A")}
                )

        if deck.get("placement", 0) > 0:
            results["has_placement"] += 1

    return results


def detect_duplicates(decks: list[dict]) -> dict:
    """Detect duplicate decks."""
    url_counts = Counter()
    deck_id_counts = Counter()

    for deck in decks:
        if deck.get("url"):
            url_counts[deck["url"]] += 1
        if deck.get("deck_id"):
            deck_id_counts[deck["deck_id"]] += 1

    duplicates_by_url = {url: count for url, count in url_counts.items() if count > 1}
    duplicates_by_id = {did: count for did, count in deck_id_counts.items() if count > 1}

    return {
        "duplicate_urls": len(duplicates_by_url),
        "duplicate_ids": len(duplicates_by_id),
        "samples": list(duplicates_by_url.items())[:5],
    }


def validate_format_distribution(decks: list[dict]) -> dict:
    """Check format coverage and balance."""
    format_counts = Counter()
    format_archetypes = defaultdict(set)

    for deck in decks:
        fmt = deck.get("format", "unknown")
        archetype = deck.get("archetype", "unknown")
        format_counts[fmt] += 1
        format_archetypes[fmt].add(archetype)

    results = {
        "total_formats": len(format_counts),
        "formats": dict(format_counts.most_common()),
        "archetype_diversity": {},
    }

    for fmt, count in format_counts.items():
        results["archetype_diversity"][fmt] = {
            "unique_archetypes": len(format_archetypes[fmt]),
            "decks": count,
            "diversity_ratio": len(format_archetypes[fmt]) / max(count, 1),
        }

    return results


def validate_card_names(decks: list[dict]) -> dict:
    """Check for card name quality issues."""
    all_card_names = set()
    suspicious_names = []

    for deck in decks:
        for card in deck.get("cards", []):
            name = card.get("name", "")
            all_card_names.add(name)

            # Check for suspicious patterns
            if len(name) < 2:
                suspicious_names.append(("too_short", name))
            elif len(name) > 100:
                suspicious_names.append(("too_long", name))
            elif name.startswith(" ") or name.endswith(" "):
                suspicious_names.append(("whitespace", name))

    return {
        "unique_cards": len(all_card_names),
        "suspicious_count": len(suspicious_names),
        "suspicious_samples": suspicious_names[:20],
    }


def run_validation(jsonl_path: Path):
    """Run all validations."""
    print("=" * 80)
    print("DATA QUALITY VALIDATION")
    print("=" * 80)
    print(f"\nDataset: {jsonl_path}")

    if not jsonl_path.exists():
        print(f"\n❌ File not found: {jsonl_path}")
        print(
            "   Run: cd src/backend && go run ./cmd/export-hetero data-full/games/magic decks_hetero.jsonl"
        )
        return

    # Load decks
    print("\nLoading decks...")
    decks = []
    structural_issues = []

    with open(jsonl_path) as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            try:
                deck = json.loads(line)
                decks.append(deck)

                # Validate structure
                issues = validate_deck_structure(deck)
                if issues:
                    structural_issues.append((i, deck.get("deck_id"), issues))
            except json.JSONDecodeError as e:
                structural_issues.append((i, None, [f"JSON parse error: {e}"]))

    print(f"✅ Loaded {len(decks):,} decks")

    # 1. Source Tracking
    print("\n" + "=" * 80)
    print("1. SOURCE TRACKING VALIDATION")
    print("=" * 80)

    source_results = validate_source_tracking(decks)
    print(f"\nTotal decks: {source_results['total']:,}")
    print(
        f"Has source: {source_results['has_source']:,} ({100.0 * source_results['has_source'] / source_results['total']:.1f}%)"
    )
    print(f"Missing source: {source_results['missing_source']:,}")

    print("\nSource distribution:")
    for source, count in source_results["by_source"].most_common():
        pct = 100.0 * count / source_results["total"]
        print(f"   {source}: {count:,} ({pct:.1f}%)")

    if source_results["missing_source_samples"]:
        print("\nSample decks missing source:")
        for sample in source_results["missing_source_samples"][:5]:
            print(f"   - {sample['deck_id']}: {sample['format']} {sample['archetype']}")

    # 2. Tournament Metadata
    print("\n" + "=" * 80)
    print("2. TOURNAMENT METADATA VALIDATION")
    print("=" * 80)

    metadata_results = validate_metadata_coverage(decks)
    print(f"\nTotal decks: {metadata_results['total']:,}")
    print(
        f"Has player: {metadata_results['has_player']:,} ({100.0 * metadata_results['has_player'] / metadata_results['total']:.2f}%)"
    )
    print(
        f"Has event: {metadata_results['has_event']:,} ({100.0 * metadata_results['has_event'] / metadata_results['total']:.2f}%)"
    )
    print(
        f"Has placement: {metadata_results['has_placement']:,} ({100.0 * metadata_results['has_placement'] / metadata_results['total']:.2f}%)"
    )

    if metadata_results["player_samples"]:
        print("\nSample decks with player metadata:")
        for sample in metadata_results["player_samples"]:
            print(f"   - {sample['player']}: {sample['archetype']} @ {sample['event']}")

    # 3. Structural Issues
    print("\n" + "=" * 80)
    print("3. STRUCTURAL VALIDATION")
    print("=" * 80)

    print(f"\nDecks with structural issues: {len(structural_issues)}")
    if structural_issues:
        print("Sample issues:")
        for line_num, deck_id, issues in structural_issues[:10]:
            print(f"   Line {line_num} ({deck_id}): {', '.join(issues)}")

    # 4. Duplicates
    print("\n" + "=" * 80)
    print("4. DUPLICATE DETECTION")
    print("=" * 80)

    dup_results = detect_duplicates(decks)
    print(f"\nDuplicate URLs: {dup_results['duplicate_urls']}")
    print(f"Duplicate IDs: {dup_results['duplicate_ids']}")

    if dup_results["samples"]:
        print("\nSample duplicates:")
        for url, count in dup_results["samples"]:
            print(f"   {url[:60]}... appears {count}x")

    # 5. Format Distribution
    print("\n" + "=" * 80)
    print("5. FORMAT COVERAGE & DIVERSITY")
    print("=" * 80)

    format_results = validate_format_distribution(decks)
    print(f"\nTotal formats: {format_results['total_formats']}")
    print("\nTop formats:")
    for fmt, count in list(format_results["formats"].items())[:10]:
        div = format_results["archetype_diversity"][fmt]
        print(
            f"   {fmt}: {count:,} decks, {div['unique_archetypes']} archetypes (ratio: {div['diversity_ratio']:.2f})"
        )

    # Check for low-diversity formats
    print("\n⚠️  Low diversity formats (< 0.1 ratio):")
    for fmt, div in format_results["archetype_diversity"].items():
        if div["diversity_ratio"] < 0.1 and div["decks"] > 50:
            print(
                f"   {fmt}: {div['unique_archetypes']} archetypes / {div['decks']} decks = {div['diversity_ratio']:.3f}"
            )

    # 6. Card Names
    print("\n" + "=" * 80)
    print("6. CARD NAME QUALITY")
    print("=" * 80)

    card_results = validate_card_names(decks)
    print(f"\nUnique cards across all decks: {card_results['unique_cards']:,}")
    print(f"Suspicious card names: {card_results['suspicious_count']}")

    if card_results["suspicious_samples"]:
        print("\nSample issues:")
        for issue_type, name in card_results["suspicious_samples"][:10]:
            print(f"   [{issue_type}] '{name}'")

    # Summary
    print("\n" + "=" * 80)
    print("QUALITY SUMMARY")
    print("=" * 80)

    issues_found = []

    if source_results["missing_source"] > source_results["total"] * 0.05:
        issues_found.append(f"❌ {source_results['missing_source']:,} decks missing source (>{5}%)")

    if metadata_results["has_player"] < metadata_results["total"] * 0.5:
        issues_found.append(
            f"⚠️  Low player metadata coverage: {100.0 * metadata_results['has_player'] / metadata_results['total']:.1f}%"
        )

    if len(structural_issues) > 0:
        issues_found.append(f"⚠️  {len(structural_issues)} decks with structural issues")

    if dup_results["duplicate_ids"] > 0:
        issues_found.append(f"⚠️  {dup_results['duplicate_ids']} duplicate deck IDs")

    if card_results["suspicious_count"] > 100:
        issues_found.append(f"⚠️  {card_results['suspicious_count']} suspicious card names")

    if issues_found:
        print("\n❌ Issues Found:")
        for issue in issues_found:
            print(f"   {issue}")
    else:
        print("\n✅ No major issues found!")

    print("\n📊 Overall Quality Score:")

    # Calculate score
    score = 100.0
    score -= (
        source_results["missing_source"] / source_results["total"]
    ) * 20  # -20 for missing sources
    score -= (len(structural_issues) / len(decks)) * 30  # -30 for structural issues
    score -= min((dup_results["duplicate_ids"] / len(decks)) * 20, 10)  # -10 max for duplicates
    score -= min(
        (card_results["suspicious_count"] / card_results["unique_cards"]) * 10, 5
    )  # -5 max for bad names

    print(f"   Quality Score: {score:.1f}/100")

    if score >= 95:
        print("   Grade: A (Excellent)")
    elif score >= 85:
        print("   Grade: B (Good)")
    elif score >= 75:
        print("   Grade: C (Acceptable)")
    else:
        print("   Grade: D (Needs Work)")

    return {
        "score": score,
        "source": source_results,
        "metadata": metadata_results,
        "structural": len(structural_issues),
        "duplicates": dup_results,
        "cards": card_results,
    }


if __name__ == "__main__":
    base = Path(__file__).resolve()
    default = base.parent / "../backend/decks_hetero.jsonl"
    fixture = base.parent / "tests" / "fixtures" / "decks_export_hetero_small.jsonl"
    jsonl_path = default if default.exists() else fixture
    results = run_validation(jsonl_path)

    # Save results
    output_path = Path("../experiments/validation_results_oct_4_2025.json")
    output_path.parent.mkdir(exist_ok=True, parents=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n💾 Results saved to: {output_path}")
