# Agentic Meta-Judge with Multi-Round Conversations

## Overview

The agentic meta-judge system replaces hard-coded rules with a dynamic, conversation-based feedback loop. It acts as an **IAA (Inter-Annotator Agreement) moderator** that:

1. **Reviews annotations** from multiple annotators
2. **Provides specific feedback** via conversation history (not just static prompts)
3. **Moderates consensus** across multiple rounds
4. **Maintains conversation state** to build context over time

## Key Features

### 1. Multi-Round Conversations

Instead of one-shot annotation, the system supports multiple rounds:

```python
# Round 1: Initial annotations
annotations = {
    "annotator_1": annotation_1,
    "annotator_2": annotation_2,
    "annotator_3": annotation_3,
}

# Meta-judge reviews and provides feedback
round_1 = await meta_judge.moderate_annotation_round(round_1)

# Round 2: Annotators revise based on feedback (via conversation history)
round_2 = await meta_judge.moderate_annotation_round(round_2, previous_rounds=[round_1])

# Continue until consensus or max rounds
```

### 2. Dynamic Feedback Injection

Feedback is injected via **conversation history** (Pydantic AI's `message_history`), not static prompt additions:

```python
# Meta-judge provides feedback
feedback = await feedback_agent.run(
    prompt,
    message_history=conversation_history,  # Previous rounds' context
)

# Feedback is added to conversation history
conversation_history.extend(feedback.new_messages())

# Next round uses this history for context
next_result = await annotator_agent.run(
    next_prompt,
    message_history=conversation_history,  # Includes previous feedback
)
```

### 3. IAA Moderation

The meta-judge acts as a moderator, evaluating:

- **Consensus**: Do annotators agree? (Krippendorff's Alpha)
- **Quality**: Are annotations high quality?
- **Convergence**: Are annotations improving across rounds?

```python
consensus_decision = ConsensusDecision(
    consensus_reached=True,
    consensus_score=0.85,  # High agreement
    quality_acceptable=True,
    recommended_action="accept",  # or "revise", "continue_rounds", "reject"
    feedback_for_round="Annotators converged well. Minor calibration differences resolved."
)
```

### 4. Multi-Round Voting Scheme

The system supports a voting/consensus scheme:

1. **Round 1**: Multiple annotators provide initial annotations
2. **Meta-Judge Review**: Evaluates each annotation and provides feedback
3. **Consensus Check**: Determines if consensus is reached
4. **Round 2+**: If not, annotators revise based on feedback
5. **Final Decision**: Accept, reject, or continue based on consensus

## Architecture

### Components

1. **AgenticMetaJudge**: Main orchestrator
   - `feedback_agent`: Reviews individual annotations
   - `consensus_agent`: Evaluates consensus across annotators

2. **AnnotationRound**: Represents one round
   - Annotations from all annotators
   - Meta-judge feedback
   - Conversation history
   - Consensus decision

3. **Feedback Models**:
   - `MetaJudgeFeedback`: Individual annotation feedback
   - `ConsensusDecision`: Multi-annotator consensus decision

### Integration with Existing System

The agentic meta-judge can be integrated with:

- **MultiAnnotatorIAA**: Use meta-judge to moderate IAA rounds
- **LLMAnnotator**: Inject feedback into annotation prompts via conversation history
- **Meta-Judge**: Replace static feedback injection with dynamic conversation-based feedback

## Example Usage

```python
from ml.annotation.agentic_meta_judge import AgenticMetaJudge
from ml.annotation.multi_annotator_iaa import MultiAnnotatorIAA

# Create systems
multi_annotator = MultiAnnotatorIAA()
meta_judge = AgenticMetaJudge(max_rounds=3)

# Round 1: Get initial annotations
result_1 = await multi_annotator.annotate_pair_multi(card1, card2)
initial_annotations = result_1.annotations

# Moderate with meta-judge
final_round, all_rounds = await meta_judge.moderate_multi_round(initial_annotations)

# Check if consensus reached
if final_round.consensus_decision.recommended_action == "accept":
    # Use consensus annotation
    consensus = final_round.consensus_decision
    # ... use consensus annotation
```

## Benefits Over Hard Rules

1. **Context-Aware**: Feedback adapts to specific annotation issues
2. **Iterative Improvement**: Multiple rounds allow convergence
3. **No Rigid Thresholds**: Meta-judge can make nuanced decisions
4. **Conversation History**: Builds context over time
5. **IAA Moderation**: Explicitly handles multi-annotator agreement

## Future Enhancements

1. **Graph-Based Feedback**: Use graph evidence to inform feedback
2. **Annotator-Specific Feedback**: Tailor feedback to each annotator's patterns
3. **Active Learning**: Select pairs that need most improvement
4. **Human-in-the-Loop**: Allow human moderators to override decisions
5. **Quality Tracking**: Track annotator reliability over time
