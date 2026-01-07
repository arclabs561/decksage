"""Agentic QA agent using LLM to reason about quality issues."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from pydantic_ai import Agent, tool
    from pydantic import BaseModel, Field
    
    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    BaseModel = object
    Field = lambda **kwargs: lambda x: x
    tool = lambda **kwargs: lambda x: x

from .agentic_qa_tools import GraphQATools
from ..utils.logging_config import (
    setup_script_logging,
    log_progress,
    log_exception,
    get_correlation_id,
)
from ..utils.pydantic_ai_helpers import get_default_model
from ..utils.lineage import DATA_ORDERS

logger = setup_script_logging()


class QualityAnalysis(BaseModel):
    """LLM analysis of quality issue."""
    issue_description: str = Field(description="Description of the quality issue")
    severity: str = Field(description="critical|warning|info")
    root_cause: str = Field(description="Likely root cause")
    impact: str = Field(description="Impact on graph quality")
    recommended_fix: str = Field(description="Recommended fix")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in analysis")


class AgenticQAAgent:
    """LLM agent for quality assurance."""
    
    def __init__(self, graph_db: Path | None = None, model: str | None = None):
        """Initialize agentic QA agent."""
        if not HAS_PYDANTIC_AI:
            raise ImportError("pydantic-ai required for agentic QA")
        
        self.tools = GraphQATools(graph_db)
        self.model = model or get_default_model("validator")
        self.agent = self._create_agent()
    
    def _create_agent(self) -> Agent:
        """Create LLM agent with tools."""
        # Create tool functions that can be used by the agent
        # Pydantic AI tools need to be decorated with @tool
        tools_instance = self.tools
        
        @tool
        def check_node_exists(card_name: str) -> dict[str, Any]:
            """Check if a node exists in the graph and return its data."""
            logger.debug(f"[TOOL] check_node_exists('{card_name}')")
            try:
                result = tools_instance.check_node_exists(card_name)
                logger.debug(f"[TOOL] check_node_exists returned: exists={result.get('exists', False)}")
                return result
            except Exception as e:
                logger.error(f"[TOOL] check_node_exists failed: {e}")
                return {"exists": False, "error": str(e)}
        
        @tool
        def check_edge_exists(card1: str, card2: str) -> dict[str, Any]:
            """Check if an edge exists between two cards."""
            return tools_instance.check_edge_exists(card1, card2)
        
        @tool
        def get_node_neighbors(card_name: str, limit: int = 10) -> list[dict[str, Any]]:
            """Get neighbors of a node in the graph."""
            return tools_instance.get_node_neighbors(card_name, limit)
        
        @tool
        def validate_game_label(card_name: str, expected_game: str | None = None) -> dict[str, Any]:
            """Validate game label for a card against the card database."""
            return tools_instance.validate_game_label(card_name, expected_game)
        
        @tool
        def sample_high_frequency_edges(limit: int = 10) -> list[dict[str, Any]]:
            """Sample high-frequency edges for validation."""
            return tools_instance.sample_high_frequency_edges(limit)
        
        @tool
        def check_data_integrity() -> dict[str, Any]:
            """Check data integrity - may take time for large graphs."""
            logger.debug("[TOOL] check_data_integrity() called")
            try:
                result = tools_instance.check_data_integrity()
                logger.debug(f"[TOOL] check_data_integrity returned: integrity_score={result.get('integrity_score', 0):.2%}")
                return result
            except Exception as e:
                logger.error(f"[TOOL] check_data_integrity failed: {e}")
                return {"error": str(e), "integrity_score": 0.0}
        
        @tool
        def investigate_unknown_nodes(limit: int = 20) -> list[dict[str, Any]]:
            """Investigate nodes with unknown game labels."""
            return tools_instance.investigate_unknown_nodes(limit)
        
        @tool
        def check_pipeline_dependencies(order: int) -> dict[str, Any]:
            """Check if pipeline dependencies for a data order are satisfied."""
            return tools_instance.check_pipeline_dependencies(order)
        
        @tool
        def validate_pipeline_order(order: int) -> dict[str, Any]:
            """Validate a specific pipeline order and its dependencies."""
            return tools_instance.validate_pipeline_order(order)
        
        @tool
        def get_pipeline_summary() -> dict[str, Any]:
            """Get summary of entire pipeline state across all orders."""
            return tools_instance.get_pipeline_summary()
        
        @tool
        def check_graph_statistics() -> dict[str, Any]:
            """Get comprehensive graph statistics (nodes, edges, games)."""
            return tools_instance.check_graph_statistics()
        
        @tool
        def check_file_timestamp(path: str) -> dict[str, Any]:
            """Check file modification timestamp and age. Critical for detecting stale data."""
            return tools_instance.check_file_timestamp(path)
        
        @tool
        def check_data_freshness(order: int) -> dict[str, Any]:
            """Check if data for an order is fresher than dependencies. Detects stale data issues."""
            return tools_instance.check_data_freshness(order)
        
        @tool
        def compare_file_timestamps(path1: str, path2: str) -> dict[str, Any]:
            """Compare timestamps of two files to determine which is newer."""
            return tools_instance.compare_file_timestamps(path1, path2)
        
        @tool
        def validate_nodes_against_decks(game: str | None = None) -> dict[str, Any]:
            """Check if graph nodes exist in deck data. Validates cross-order consistency."""
            return tools_instance.validate_nodes_against_decks(game)
        
        @tool
        def query_nodes_by_game(game: str, limit: int = 100) -> list[dict[str, Any]]:
            """Query nodes by game. Useful for investigating game-specific issues."""
            return tools_instance.query_nodes_by_game(game, limit)
        
        @tool
        def query_edges_by_weight(min_weight: float = 0, max_weight: float | None = None, limit: int = 100) -> list[dict[str, Any]]:
            """Query edges by weight range. Useful for finding suspicious edges."""
            return tools_instance.query_edges_by_weight(min_weight, max_weight, limit)
        
        @tool
        def find_isolated_nodes(limit: int = 20) -> list[dict[str, Any]]:
            """Find nodes with no edges (isolated). Indicates data quality issues."""
            return tools_instance.find_isolated_nodes(limit)
        
        @tool
        def check_annotation_format(file_path: str) -> dict[str, Any]:
            """Validate annotation file format (JSONL/YAML)."""
            return tools_instance.check_annotation_format(Path(file_path))
        
        @tool
        def check_embedding_exists(component: str, version: str | None = None) -> dict[str, Any]:
            """Check if embeddings exist for a component (cooccurrence, instruction, gnn)."""
            return tools_instance.check_embedding_exists(component, version)
        
        @tool
        def validate_test_set_exists(game: str) -> dict[str, Any]:
            """Check if test set exists for a game and get metadata."""
            return tools_instance.validate_test_set_exists(game)
        
        @tool
        def validate_embedding_vocabulary(component: str = "cooccurrence") -> dict[str, Any]:
            """Validate embedding vocabulary matches graph nodes. Checks coverage and mismatches."""
            return tools_instance.validate_embedding_vocabulary(component)
        
        @tool
        def check_test_set_coverage(game: str) -> dict[str, Any]:
            """Check test set query coverage against graph and embeddings."""
            return tools_instance.check_test_set_coverage(game)
        
        # Enhanced system prompt for the QA agent
        system_prompt = """You are an expert quality assurance agent for a trading card game data pipeline and graph system.

Your role is to:
1. Investigate and diagnose quality issues in the graph data
2. Validate pipeline dependencies and data lineage integrity
3. Analyze root causes of problems and recommend specific fixes
4. Provide clear, actionable insights with evidence

CRITICAL INVESTIGATION WORKFLOW:
When analyzing an issue, follow this systematic approach:

1. **Gather Evidence First**
   - Use check_data_integrity() to find basic problems
   - Use check_graph_statistics() to understand scale
   - Use get_pipeline_summary() to see overall state

2. **Diagnose Root Cause**
   - For stale data: Use check_data_freshness() and compare_file_timestamps()
   - For missing dependencies: Use check_pipeline_dependencies() and validate_pipeline_order()
   - For cross-order issues: Use validate_nodes_against_decks() to check consistency
   - For graph issues: Use query_edges_by_weight(), find_isolated_nodes(), sample_high_frequency_edges()

3. **Validate Specific Components**
   - Annotations: Use check_annotation_format() to validate Order 6
   - Embeddings: Use check_embedding_exists() and validate_embedding_vocabulary() to validate Order 4
   - Test sets: Use validate_test_set_exists() and check_test_set_coverage() to validate Order 5

4. **Provide Actionable Recommendations**
   - Always check timestamps when investigating stale data issues
   - Compare file ages to determine if regeneration is needed
   - Check cross-order consistency when nodes/edges seem wrong
   - Provide specific commands/scripts to fix issues

KEY INSIGHTS TO DETECT:
- Stale data: Order N is older than Order N-1 (use check_data_freshness)
- Orphaned data: Nodes/edges exist but source data does not (use validate_nodes_against_decks)
- Missing dependencies: Order exists but dependencies do not (use check_pipeline_dependencies)
- Format issues: Files exist but are malformed (use check_annotation_format)

Be thorough, systematic, and evidence-based. Use multiple tools to build a complete picture before making recommendations."""
        
        # Create agent with tools
        provider = os.getenv("LLM_PROVIDER", "openrouter")
        from pydantic_ai import ModelSettings
        
        return Agent(
            f"{provider}:{self.model}",
            output_type=QualityAnalysis,
            system_prompt=system_prompt,
            tools=[
                check_node_exists,
                check_edge_exists,
                get_node_neighbors,
                validate_game_label,
                sample_high_frequency_edges,
                check_data_integrity,
                investigate_unknown_nodes,
                check_pipeline_dependencies,
                validate_pipeline_order,
                get_pipeline_summary,
                check_graph_statistics,
                check_file_timestamp,
                check_data_freshness,
                compare_file_timestamps,
                validate_nodes_against_decks,
                query_nodes_by_game,
                query_edges_by_weight,
                find_isolated_nodes,
                check_annotation_format,
                check_embedding_exists,
                validate_test_set_exists,
                validate_embedding_vocabulary,
                check_test_set_coverage,
            ],
            model_settings=ModelSettings(temperature=0.3, max_tokens=2000),
        )
    
    async def analyze_quality_issue(self, issue_description: str) -> QualityAnalysis:
        """Use LLM agent to analyze a quality issue."""
        corr_id = get_correlation_id() or "unknown"
        logger.info(
            f"Analyzing quality issue [correlation_id={corr_id}, "
            f"issue_length={len(issue_description)}]"
        )
        
        if not self.agent:
            logger.warning("Agent not initialized, using fallback analysis")
            # Fallback: return basic analysis
            return QualityAnalysis(
                issue_description=issue_description,
                severity="warning",
                root_cause="Unknown",
                impact="Moderate",
                recommended_fix="Investigate further",
                confidence=0.5,
            )
        
        logger.debug(f"Issue description: {issue_description[:200]}...")
        
        prompt = f"""Analyze this quality issue in the graph/pipeline system:

{issue_description}

SYSTEMATIC INVESTIGATION REQUIRED:

1. **Gather Evidence**
   - Start with check_data_integrity() to see basic problems
   - Use check_graph_statistics() to understand scale
   - If issue mentions specific cards: use check_node_exists(), check_edge_exists()
   - If issue mentions weights: use query_edges_by_weight() to investigate

2. **Check Temporal Issues** (if relevant)
   - Use check_data_freshness() to see if data is stale
   - Use check_file_timestamp() for specific files mentioned
   - Compare timestamps if issue suggests sync problems

3. **Check Cross-Order Consistency** (if relevant)
   - Use validate_nodes_against_decks() if nodes seem wrong
   - Check if embeddings/test sets exist if issue mentions them

4. **Diagnose Root Cause**
   - Connect evidence from multiple tools
   - Identify the underlying problem, not just symptoms
   - Consider pipeline dependencies and data flow

5. **Recommend Specific Fix**
   - Provide exact command/script to run
   - Explain why this fix addresses root cause
   - Consider impact on downstream orders

Be thorough - use multiple tools to build complete picture before concluding."""
        
        try:
            import time
            import asyncio
            analysis_start = time.time()
            logger.debug("Running agent analysis...")
            logger.debug(f"Prompt length: {len(prompt)} chars")
            
            # Add timeout for agent operations (configurable via env var)
            timeout_seconds = float(os.getenv("AGENTIC_QA_TIMEOUT_ANALYSIS", "300.0"))  # Default 5 minutes
            try:
                result = await asyncio.wait_for(
                    self.agent.run(prompt),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                timeout_min = timeout_seconds / 60
                logger.error(f"Agent analysis timed out after {timeout_min:.1f} minutes [correlation_id={corr_id}]")
                raise TimeoutError(f"Agent analysis timed out after {timeout_min:.1f} minutes")
            
            analysis = result.output
            analysis_time = time.time() - analysis_start
            
            # Validate analysis quality
            validation_issues = self._validate_analysis_quality(analysis, corr_id)
            if validation_issues:
                logger.warning(
                    f"Analysis quality issues detected [correlation_id={corr_id}, "
                    f"issues={len(validation_issues)}]: {', '.join(validation_issues[:3])}"
                )
            
            # Log tool usage if available
            if hasattr(result, 'all_messages'):
                tool_calls = sum(1 for msg in result.all_messages if hasattr(msg, 'tool_calls') and msg.tool_calls)
                logger.debug(f"Agent made {tool_calls} tool calls in {analysis_time:.2f}s")
            
            logger.info(
                f"Analysis complete [correlation_id={corr_id}, "
                f"severity={analysis.severity}, confidence={analysis.confidence:.1%}, "
                f"time={analysis_time:.2f}s]"
            )
            
            logger.debug(
                f"Root cause: {analysis.root_cause[:100]}... | "
                f"Recommended fix: {analysis.recommended_fix[:100]}..."
            )
            
            return analysis
        except Exception as e:
            log_exception(logger, "Agent analysis failed", e, include_context=True)
            raise
    
    def _validate_analysis_quality(self, analysis: QualityAnalysis, corr_id: str) -> list[str]:
        """
        Validate analysis quality to detect hallucinations and verify actionability.
        
        Returns list of validation issues found.
        """
        issues = []
        
        # Check for too-short responses (likely incomplete)
        if len(analysis.root_cause) < 20:
            issues.append(f"root_cause_too_short({len(analysis.root_cause)} chars)")
        
        if len(analysis.recommended_fix) < 20:
            issues.append(f"recommended_fix_too_short({len(analysis.recommended_fix)} chars)")
        
        # Check for low confidence with high severity (suspicious)
        if analysis.confidence < 0.3 and analysis.severity == "critical":
            issues.append("low_confidence_critical_severity")
        
        # Check for generic/vague responses (hallucination indicators)
        generic_phrases = [
            "it depends", "may vary", "could be", "might be", "possibly",
            "unknown", "unclear", "uncertain", "needs investigation",
        ]
        root_cause_lower = analysis.root_cause.lower()
        if any(phrase in root_cause_lower for phrase in generic_phrases):
            if len(analysis.root_cause) < 50:  # Only flag if also short
                issues.append("generic_root_cause")
        
        # Check for actionable recommendations (should contain verbs/commands)
        action_verbs = [
            "run", "execute", "check", "verify", "fix", "update", "regenerate",
            "rebuild", "validate", "test", "install", "configure", "set",
        ]
        recommended_lower = analysis.recommended_fix.lower()
        has_action = any(verb in recommended_lower for verb in action_verbs)
        if not has_action and len(analysis.recommended_fix) > 30:
            issues.append("recommendation_not_actionable")
        
        # Check for script/file references (good sign of actionability)
        has_script_ref = bool(re.search(r'(python|script|\.py|\.sh|command)', recommended_lower))
        if has_script_ref:
            # Good - has actionable reference
            pass
        elif len(analysis.recommended_fix) > 50:
            # Long recommendation without script reference might be vague
            issues.append("recommendation_missing_script_reference")
        
        # Check for confidence calibration
        if analysis.confidence > 0.9 and analysis.severity == "info":
            # High confidence for info-level issue is suspicious
            issues.append("overconfident_info_severity")
        
        # Check for contradiction between severity and confidence
        if analysis.severity == "critical" and analysis.confidence < 0.5:
            issues.append("critical_with_low_confidence")
        
        return issues
    
    def analyze_quality_issue_sync(self, issue_description: str) -> QualityAnalysis:
        """Synchronous version of analyze_quality_issue."""
        import asyncio
        return asyncio.run(self.analyze_quality_issue(issue_description))
    
    async def investigate_sample(self, sample_size: int = 10) -> list[dict[str, Any]]:
        """Investigate a sample of graph data using the agent."""
        logger.info(f"Investigating sample of {sample_size} items using agentic tools...")
        
        if not self.agent:
            # Fallback to non-agentic investigation
            logger.debug("Agent not available, using tool-based investigation")
            edges = self.tools.sample_high_frequency_edges(limit=sample_size)
            investigations = []
            for edge in edges:
                try:
                    node1_check = self.tools.check_node_exists(edge["card1"])
                    node2_check = self.tools.check_node_exists(edge["card2"])
                    game1_check = self.tools.validate_game_label(edge["card1"])
                    game2_check = self.tools.validate_game_label(edge["card2"])
                    
                    investigation = {
                        "edge": edge,
                        "node1_valid": node1_check.get("exists", False),
                        "node2_valid": node2_check.get("exists", False),
                        "game1_valid": game1_check.get("valid", False),
                        "game2_valid": game2_check.get("valid", False),
                        "issues": [],
                    }
                    
                    if not investigation["node1_valid"]:
                        investigation["issues"].append(f"Node {edge['card1']} does not exist")
                    if not investigation["node2_valid"]:
                        investigation["issues"].append(f"Node {edge['card2']} does not exist")
                    if not investigation["game1_valid"]:
                        investigation["issues"].append(f"Game label issue for {edge['card1']}")
                    if not investigation["game2_valid"]:
                        investigation["issues"].append(f"Game label issue for {edge['card2']}")
                    
                    investigations.append(investigation)
                except Exception as e:
                    logger.debug(f"Error investigating edge {edge.get('card1', '?')}: {e}")
                    investigations.append({
                        "edge": edge,
                        "error": str(e),
                    })
            logger.info(f"Investigated {len(investigations)} edges [correlation_id={corr_id}]")
            return investigations
        
        # Use agent for comprehensive investigation
        prompt = f"""Investigate a sample of {sample_size} high-frequency edges in the graph.

SYSTEMATIC INVESTIGATION:

1. **Sample Edges**
   - Use sample_high_frequency_edges({sample_size}) to get edges

2. **For Each Edge, Validate:**
   - Use check_node_exists() for both cards
   - Use validate_game_label() to check game labels
   - Use check_edge_exists() to verify edge data
   - Check if weight is suspicious (use query_edges_by_weight if needed)

3. **Identify Patterns**
   - Are issues isolated or systematic?
   - Do issues correlate with specific games?
   - Are there common root causes?

4. **Provide Analysis**
   - Severity of issues found
   - Root cause if pattern detected
   - Recommended fix

Be efficient but thorough - validate multiple edges to detect patterns."""
        
        try:
            result = await self.agent.run(prompt)
            analysis = result.output
            
            # Also get actual edge data for context
            edges = self.tools.sample_high_frequency_edges(limit=sample_size)
            
            logger.info(
                f"Agent investigation complete [correlation_id={corr_id}, "
                f"edges_sampled={len(edges)}, severity={analysis.severity}]"
            )
            return {
                "agent_analysis": {
                    "severity": analysis.severity,
                    "root_cause": analysis.root_cause,
                    "impact": analysis.impact,
                    "recommended_fix": analysis.recommended_fix,
                    "confidence": analysis.confidence,
                },
                "edges_sampled": len(edges),
                "sample_edges": edges[:5],  # Include first 5 for context
            }
        except Exception as e:
            log_exception(logger, "Agent investigation failed", e, include_context=True)
            # Fallback to tool-based investigation
            logger.warning("Falling back to tool-based investigation")
            edges = self.tools.sample_high_frequency_edges(limit=sample_size)
            investigations = []
            for edge in edges:
                try:
                    node1_check = self.tools.check_node_exists(edge["card1"])
                    node2_check = self.tools.check_node_exists(edge["card2"])
                    investigation = {
                        "edge": edge,
                        "node1_valid": node1_check.get("exists", False),
                        "node2_valid": node2_check.get("exists", False),
                        "issues": [],
                    }
                    investigations.append(investigation)
                except Exception as edge_error:
                    logger.debug(f"Error investigating edge: {edge_error}")
                    investigations.append({
                        "edge": edge,
                        "error": str(edge_error),
                    })
            return investigations
    
    async def validate_pipeline(self) -> dict[str, Any]:
        """Validate the entire pipeline using the agent."""
        corr_id = get_correlation_id() or "unknown"
        logger.info(f"Validating pipeline [correlation_id={corr_id}]")
        
        log_progress(logger, "pipeline_validation", progress=0, total=7, stage="initialization")
        
        if not self.agent:
            logger.warning("Agent not initialized, using tool-based validation only")
            # Fallback
            summary = self.tools.get_pipeline_summary()
            log_progress(logger, "pipeline_validation", progress=7, total=7, stage="complete")
            return summary
        
        prompt = """Comprehensively validate the entire data pipeline (Orders 0-6).

SYSTEMATIC INVESTIGATION REQUIRED:

1. **Check Pipeline State**
   - Use get_pipeline_summary() to see overall state
   - Use validate_pipeline_order() for each order with issues

2. **Check Data Freshness** (CRITICAL)
   - Use check_data_freshness() for each order to detect stale data
   - Compare timestamps: if Order N is older than Order N-1, it is stale
   - Use compare_file_timestamps() for specific file comparisons

3. **Check Cross-Order Consistency**
   - Use validate_nodes_against_decks() to verify graph nodes match source decks
   - Check if embeddings exist: check_embedding_exists("cooccurrence"), check_embedding_exists("gnn")
   - Check test sets: validate_test_set_exists("magic"), validate_test_set_exists("pokemon")

4. **Identify Root Causes**
   - If dependencies missing: check if files exist but are empty/corrupted
   - If data stale: determine which order needs regeneration
   - If cross-order mismatch: identify which order is wrong

5. **Provide Specific Fixes**
   - For stale data: recommend specific regeneration command
   - For missing dependencies: recommend which script to run
   - For cross-order issues: recommend which order to fix

Be thorough - use multiple tools to build complete picture. Check timestamps for every order with issues."""
        
        try:
            result = await self.agent.run(prompt)
            analysis = result.output
            
            # Get actual pipeline summary
            summary = self.tools.get_pipeline_summary()
            
            # Also get freshness data for all orders
            freshness_data = {}
            for order in sorted(DATA_ORDERS.keys()):
                try:
                    freshness = self.tools.check_data_freshness(order)
                    freshness_data[order] = freshness
                except Exception:
                    pass
            
            return {
                "pipeline_summary": summary,
                "freshness_analysis": freshness_data,
                "agent_analysis": {
                    "severity": analysis.severity,
                    "root_cause": analysis.root_cause,
                    "impact": analysis.impact,
                    "recommended_fix": analysis.recommended_fix,
                    "confidence": analysis.confidence,
                },
            }
        except TimeoutError:
            logger.error(f"Pipeline validation timed out [correlation_id={corr_id}]")
            return {
                "error": "Pipeline validation timed out",
                "pipeline_summary": self.tools.get_pipeline_summary(),
                "correlation_id": corr_id,
            }
        except Exception as e:
            log_exception(logger, "Agent pipeline validation failed", e, include_context=True)
            return {
                "error": str(e),
                "pipeline_summary": self.tools.get_pipeline_summary(),
                "correlation_id": corr_id,
            }
    
    async def comprehensive_analysis(self) -> dict[str, Any]:
        """Run comprehensive analysis of entire system."""
        corr_id = get_correlation_id() or "unknown"
        logger.info(f"Running comprehensive agentic analysis [correlation_id={corr_id}]")
        
        log_progress(logger, "comprehensive_analysis", progress=0, total=7, stage="initialization")
        
        if not self.agent:
            logger.error("Agent not initialized, cannot run comprehensive analysis")
            return {"error": "Agent not initialized", "correlation_id": corr_id}
        
        prompt = """Perform a comprehensive analysis of the entire graph and pipeline system.

SYSTEMATIC COMPREHENSIVE INVESTIGATION:

1. **Overall Health Check**
   - Use get_pipeline_summary() to see all orders
   - Use check_graph_statistics() to understand graph scale
   - Use check_data_integrity() to find basic problems

2. **Temporal Analysis** (CRITICAL)
   - Use check_data_freshness() for each order (0-6)
   - Identify any stale data issues
   - Compare timestamps to determine sync status

3. **Cross-Order Validation**
   - Use validate_nodes_against_decks() to check graph vs source
   - Use validate_embedding_vocabulary() to check embeddings vs graph
   - Use check_test_set_coverage() to check test sets vs graph/embeddings

4. **Component Validation**
   - Check embeddings: check_embedding_exists("cooccurrence"), check_embedding_exists("gnn")
   - Check test sets: validate_test_set_exists("magic"), validate_test_set_exists("pokemon")
   - Check annotations: check_annotation_format() for annotation files

5. **Deep Investigation of Issues**
   - If orphaned edges: Use check_data_integrity() to get samples, then investigate patterns
   - If stale data: Use compare_file_timestamps() to see exact age differences
   - If coverage issues: Use check_test_set_coverage() to see what is missing

6. **Root Cause Analysis**
   - Connect evidence from multiple tools
   - Identify underlying problems, not just symptoms
   - Consider data flow: Order 0 -> 1 -> 2 -> 3 -> 4 -> 5/6

7. **Prioritized Recommendations**
   - Critical issues first (stale data, missing dependencies)
   - High-impact fixes (cross-order mismatches)
   - Specific commands/scripts to run

Provide a comprehensive analysis with:
- Overall system health assessment
- Critical issues identified
- Root causes with evidence
- Prioritized fix recommendations
- Confidence levels for each finding"""
        
        try:
            import time
            import asyncio
            validation_start = time.time()
            logger.debug("Running comprehensive agent analysis...")
            logger.debug(f"Prompt length: {len(prompt)} chars")
            
            # Add timeout for comprehensive analysis (configurable via env var)
            timeout_seconds = float(os.getenv("AGENTIC_QA_TIMEOUT_COMPREHENSIVE", "900.0"))  # Default 15 minutes
            try:
                result = await asyncio.wait_for(
                    self.agent.run(prompt),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                timeout_min = timeout_seconds / 60
                logger.error(f"Comprehensive analysis timed out after {timeout_min:.1f} minutes [correlation_id={corr_id}]")
                raise TimeoutError(f"Comprehensive analysis timed out after {timeout_min:.1f} minutes")
            
            analysis = result.output
            validation_time = time.time() - validation_start
            
            log_progress(logger, "pipeline_validation", progress=1, total=7, stage="agent_analysis")
            
            # Also gather raw data for context
            logger.debug("Gathering pipeline summary...")
            pipeline_summary = self.tools.get_pipeline_summary()
            log_progress(logger, "pipeline_validation", progress=2, total=7, stage="pipeline_summary")
            
            logger.debug("Checking graph statistics...")
            graph_stats = self.tools.check_graph_statistics()
            log_progress(logger, "pipeline_validation", progress=3, total=7, stage="graph_stats")
            
            logger.debug("Checking data integrity...")
            integrity = self.tools.check_data_integrity()
            log_progress(logger, "pipeline_validation", progress=4, total=7, stage="integrity")
            
            # Get freshness for all orders
            logger.debug("Checking data freshness for all orders...")
            freshness_data = {}
            for i, order in enumerate(sorted(DATA_ORDERS.keys()), start=5):
                try:
                    freshness_data[order] = self.tools.check_data_freshness(order)
                    log_progress(logger, "pipeline_validation", progress=i, total=7, stage=f"freshness_order_{order}")
                except Exception as e:
                    logger.debug(f"Could not check freshness for order {order}: {e}")
                    pass
            
            log_progress(logger, "pipeline_validation", progress=7, total=7, stage="complete")
            
            orders_with_issues = pipeline_summary.get("orders_with_issues", 0)
            integrity_score = integrity.get("integrity_score", 0)
            
            logger.info(
                f"Pipeline validation complete [correlation_id={corr_id}, "
                f"orders_with_issues={orders_with_issues}, "
                f"integrity_score={integrity_score:.2%}]"
            )
            
            return {
                "agent_analysis": {
                    "severity": analysis.severity,
                    "root_cause": analysis.root_cause,
                    "impact": analysis.impact,
                    "recommended_fix": analysis.recommended_fix,
                    "confidence": analysis.confidence,
                },
                "pipeline_summary": pipeline_summary,
                "graph_statistics": graph_stats,
                "data_integrity": integrity,
                "freshness_analysis": freshness_data,
                "timestamp": datetime.now().isoformat(),
                "correlation_id": corr_id,
            }
        except Exception as e:
            log_exception(logger, "Comprehensive analysis failed", e, include_context=True)
            return {
                "error": str(e),
                "pipeline_summary": self.tools.get_pipeline_summary(),
                "correlation_id": corr_id,
            }
    
    def close(self) -> None:
        """Close resources."""
        self.tools.close()


