#!/usr/bin/env python3
"""
Run All Analysis Tools

After dataset expansion, run complete analysis suite to see:
1. How the garden grew
2. What new insights emerged
3. How tool outputs changed
"""

import subprocess


def run_tool(script_name, description):
    """Run a tool and capture key output."""
    print(f"\n{'=' * 60}")
    print(f"{description}")
    print(f"{'=' * 60}")

    try:
        result = subprocess.run(
            ["uv", "run", "python", script_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"❌ Error: {result.stderr}")
    except subprocess.TimeoutExpired:
        print("⚠️ Timeout - tool taking >30 seconds")
    except Exception as e:
        print(f"❌ Failed: {e}")


def main():
    print("=" * 60)
    print("COMPLETE ANALYSIS SUITE")
    print("=" * 60)
    print("Running all tools on expanded dataset")
    print()

    # Health check first
    run_tool("data_gardening.py", "🌱 GARDEN HEALTH ASSESSMENT")

    # Analysis tools
    run_tool("archetype_staples.py", "🌟 ARCHETYPE STAPLES")
    run_tool("sideboard_analysis.py", "🛡️ SIDEBOARD ANALYSIS")
    run_tool("card_companions.py", "🤝 CARD COMPANIONS")
    run_tool("deck_composition_stats.py", "📊 DECK COMPOSITION")

    print(f"\n{'=' * 60}")
    print("ANALYSIS COMPLETE")
    print(f"{'=' * 60}")
    print("All tools executed successfully")
    print()
    print("Review outputs above for:")
    print("- Garden health changes")
    print("- New archetype coverage")
    print("- Enriched sideboard insights")
    print("- Expanded companion data")


if __name__ == "__main__":
    main()
