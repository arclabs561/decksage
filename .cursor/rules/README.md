# Cursor Rules

This directory contains modular rule files for Cursor IDE. Each `.mdc` file represents a specific domain or concern.

## Rule Files

- **Always Applied** (`alwaysApply: true`):
  - `code-style.mdc` - Code style guidelines and tool preferences
  - `priorities.mdc` - Project priorities and focus areas
  - `anti-sycophancy.mdc` - Critical review and assumption challenging
  - `code-duplication.mdc` - Code duplication prevention
  - `documentation.mdc` - Documentation standards
  - `snyk_rules.mdc` - Security best practices

- **Conditionally Applied** (`alwaysApply: false`, uses globs):
  - `data-lineage.mdc` - Data lineage architecture (Order 0-6)
  - `hybrid-embedding.mdc` - Hybrid embedding system architecture
  - `training-evaluation.mdc` - Training and evaluation workflows
  - `data.mdc` - Data storage and S3 sync
  - `evaluation.mdc` - Evaluation standards and leakage prevention
  - `pipeline-coherence.mdc` - Pipeline data flow and concurrency
  - `model-versioning.mdc` - Model versioning and production management
  - `automation-workflow.mdc` - Automation utilities and dry-run mode
  - `development-workflow.mdc` - Development and experimentation workflows
  - `performance.mdc` - Performance optimization guidelines
  - `annotations.mdc` - Annotation-to-training integration
  - `testing.mdc` - Testing best practices

## Format

Each `.mdc` file uses YAML frontmatter for metadata:
- `description`: Brief description of the rule's purpose
- `alwaysApply`: Whether the rule applies to all files (true) or conditionally (false)
- `globs`: Array of glob patterns for conditional application (when `alwaysApply: false`)

## Migration

All rules have been migrated from the deprecated `.cursorrules` file into this modular structure for better organization and conditional loading.
