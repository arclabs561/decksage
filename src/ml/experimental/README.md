# Experimental Code

This directory contains experimental features, premature sophistication, and archived experiment files.

## Contents

### Research Paper Implementations
- `evolving_experiment_memory.py` - A-Mem networked experiments (Rutgers 2025)
- `memory_management.py` - Memory quality gates (Harvard 2025)
- `meta_learner.py` - Meta-learning across experiments
- `true_closed_loop.py` - Closed-loop learning system
- `self_sustaining_loop.py` - Autonomous experiment evolution

**Status**: These implement sophisticated techniques from 2025 papers but were premature. 
The foundation (basic similarity, tests, diagnostics) needs to be solid first.

**Revisit when**: P@10 > 0.15 and core infrastructure is stable.

### Experiment Tracking Systems (Duplicates)
- `experiment_runner.py` - Alternative experiment logger
- Multiple experiment tracking implementations

**Issue**: We had 3-4 different experiment tracking systems. Consolidated to use `evaluate.py::Evaluator`.

### Old Experiment Files
- `run_exp_*.py` - Individual experiment scripts (56+ experiments)
- `exp_056_verify_baseline.py` - Baseline verification

**Status**: Historical experiments. Current experiments should use the consolidated system.

### Utilities & One-offs
- `attributed_embeddings.py` - Node-attributed embeddings
- `derive_signals_from_graph.py` - Graph signal extraction
- `llm_judge.py`, `multi_perspective_judge.py` - LLM evaluation
- Various data processing utilities

**Status**: One-off scripts for specific experiments. May be useful later.

## Philosophy

This code isn't bad - it's **premature**. Following the principle "experience complexity before abstracting",
we moved this here until the basics work reliably.

When P@10 is consistently > 0.15 and we have:
- All tests passing
- Diagnostic tooling
- Stable baselines
- Clear use cases

...then revisit these techniques.
