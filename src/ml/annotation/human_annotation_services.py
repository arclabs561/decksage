"""
Human Annotation Service Integrations

Supports programmatic integration with:
- Amazon Mechanical Turk (MTurk)
- Scale AI
- Labelbox
- Appen/Figure Eight
- Custom annotation interfaces

Research-based: These services provide:
- Quality assurance mechanisms
- Annotator qualification systems
- Cost-effective crowdsourcing
- API-based programmatic access
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from ..utils.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


@dataclass
class AnnotationTask:
    """Task to submit to annotation service."""

    task_id: str
    card1: str
    card2: str
    game: str
    instructions: str
    context: dict[str, Any] | None = None


@dataclass
class AnnotationResult:
    """Result from annotation service."""

    task_id: str
    external_task_id: str
    similarity_score: float
    similarity_type: str
    reasoning: str
    is_substitute: bool
    annotator_id: str | None = None
    confidence: float | None = None
    cost: float | None = None


class HumanAnnotationService(ABC):
    """Base class for human annotation services."""

    @abstractmethod
    def submit_task(self, task: AnnotationTask) -> str:
        """Submit task to annotation service.

        Args:
            task: Annotation task

        Returns:
            External task ID
        """
        pass

    @abstractmethod
    def get_result(self, external_task_id: str) -> AnnotationResult | None:
        """Get annotation result.

        Args:
            external_task_id: External service task ID

        Returns:
            Annotation result or None if not ready
        """
        pass

    @abstractmethod
    def estimate_cost(self, num_tasks: int) -> float:
        """Estimate cost for number of tasks.

        Args:
            num_tasks: Number of tasks

        Returns:
            Estimated cost in USD
        """
        pass


class MTurkService(HumanAnnotationService):
    """Amazon Mechanical Turk integration.

    Research: MTurk provides:
    - Large worker pool
    - Low cost ($0.01-$0.10 per task)
    - Qualification system for quality
    - API for programmatic access

    Requires: boto3, AWS credentials
    """

    def __init__(self, aws_access_key: str | None = None, aws_secret_key: str | None = None):
        """Initialize MTurk service.

        Args:
            aws_access_key: AWS access key (or use environment)
            aws_secret_key: AWS secret key (or use environment)
        """
        self.aws_access_key = aws_access_key or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = aws_secret_key or os.getenv("AWS_SECRET_ACCESS_KEY")

        try:
            import boto3

            if self.aws_access_key and self.aws_secret_key:
                self.client = boto3.client(
                    "mturk",
                    aws_access_key_id=self.aws_access_key,
                    aws_secret_access_key=self.aws_secret_key,
                    region_name="us-east-1",  # MTurk region
                )
            else:
                # Use default credentials
                self.client = boto3.client("mturk", region_name="us-east-1")
            logger.info("MTurk client initialized")
        except ImportError:
            logger.warning("boto3 not installed, MTurk integration unavailable")
            self.client = None
        except Exception as e:
            logger.warning(f"Failed to initialize MTurk client: {e}")
            self.client = None

    def submit_task(self, task: AnnotationTask) -> str:
        """Submit task to MTurk.

        Args:
            task: Annotation task

        Returns:
            HIT (Human Intelligence Task) ID
        """
        if not self.client:
            raise RuntimeError("MTurk client not initialized")

        # Create HTML question for MTurk with improved instructions
        # Use improved instructions if provided, otherwise use task.instructions
        instructions = task.instructions
        if not instructions or len(instructions.strip()) < 50:
                # Generate improved instructions
                instructions = f"""
CARD SIMILARITY ANNOTATION TASK

Your task: Rate how similar two {task.game} cards are to each other.

CARDS TO COMPARE:
- Card 1: {task.card1}
- Card 2: {task.card2}

SCORING GUIDELINES (0.0 - 1.0):

0.9 - 1.0: Nearly identical (direct substitutes, same function)
  Example: "Lightning Bolt" vs "Shock" (both deal 3 damage)
  
0.7 - 0.8: Very similar (same role, minor differences)
  Example: "Counterspell" vs "Mana Leak" (both counter spells)
  
0.5 - 0.6: Moderately similar (related function, same archetype)
  Example: "Lightning Bolt" vs "Lava Spike" (both burn spells)
  
0.3 - 0.4: Somewhat similar (loose connection, shared theme)
  Example: "Lightning Bolt" vs "Bolt of Keranos" (both red damage)
  
0.1 - 0.2: Marginally similar (minimal connection)
  Example: "Lightning Bolt" vs "Shocklands" (both red, different purpose)
  
0.0 - 0.1: Unrelated (different function, color, archetype)
  Example: "Lightning Bolt" vs "Plains" (completely different)

SIMILARITY TYPES:
- functional: Cards serve the same function (can replace each other)
- synergy: Cards work well together (combo, synergy)
- archetype: Cards belong to same deck type/strategy
- manabase: Cards are both lands/mana sources
- unrelated: No clear relationship

SUBSTITUTION:
- YES: Card 2 can reasonably replace Card 1 in most decks
- NO: Cards are different enough that substitution is not appropriate

REASONING:
Provide 2-3 sentences explaining:
- Why you chose this score
- What similarities/differences you noticed
- Context where they might be used together

IMPORTANT:
- Be consistent: Similar cards should get similar scores
- Use the full range: Don't cluster scores at 0.0 or 1.0
- Consider context: Some cards are similar in specific decks only
"""
        
        question_html = f"""
        <HTMLQuestion xmlns="http://mechanicalturk.amazonaws.com/AWSMechanicalTurkDataSchemas/2011-11-11/HTMLQuestion.xsd">
            <HTMLContent><![CDATA[
            <!DOCTYPE html>
            <html>
            <head>
                <meta http-equiv='Content-Type' content='text/html; charset=UTF-8'/>
                <title>Card Similarity Annotation</title>
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 20px; }}
                    h2 {{ color: #333; }}
                    .card {{ background: #f5f5f5; padding: 10px; margin: 10px 0; border-left: 3px solid #0066cc; }}
                    .guidelines {{ background: #fff9e6; padding: 15px; margin: 15px 0; border: 1px solid #ffcc00; }}
                    .example {{ background: #e6f3ff; padding: 8px; margin: 5px 0; font-size: 0.9em; }}
                    label {{ display: block; margin: 10px 0; font-weight: bold; }}
                    input[type="number"] {{ width: 100px; padding: 5px; }}
                    select {{ padding: 5px; min-width: 200px; }}
                    textarea {{ width: 100%; min-height: 100px; padding: 5px; }}
                </style>
            </head>
            <body>
                <h2>Card Similarity Annotation</h2>
                <div class="card">
                    <p><strong>Game:</strong> {task.game}</p>
                    <p><strong>Card 1:</strong> {task.card1}</p>
                    <p><strong>Card 2:</strong> {task.card2}</p>
                </div>
                <div class="guidelines">
                    <h3>Instructions:</h3>
                    <pre style="white-space: pre-wrap; font-family: Arial, sans-serif;">{instructions}</pre>
                </div>
                <form>
                    <label>Similarity Score (0.0-1.0): 
                        <input type="number" name="similarity" min="0" max="1" step="0.01" required/>
                        <small>Use full range: 0.0 (unrelated) to 1.0 (nearly identical)</small>
                    </label><br/><br/>
                    <label>Similarity Type: 
                        <select name="type" required>
                            <option value="">-- Select Type --</option>
                            <option value="functional">Functional (same function)</option>
                            <option value="synergy">Synergy (work well together)</option>
                            <option value="archetype">Archetype (same deck type)</option>
                            <option value="manabase">Manabase (both lands/mana)</option>
                            <option value="unrelated">Unrelated (no clear relationship)</option>
                        </select>
                    </label><br/><br/>
                    <label>
                        <input type="checkbox" name="substitute"/> 
                        Can Card 2 substitute for Card 1? (Check if YES)
                    </label><br/><br/>
                    <label>Reasoning (2-3 sentences, required): 
                        <textarea name="reasoning" placeholder="Explain why you chose this score, what similarities/differences you noticed, and context where they might be used together..." required></textarea>
                    </label>
                </form>
            </body>
            </html>
            ]]></HTMLContent>
            <FrameHeight>800</FrameHeight>
        </HTMLQuestion>
        """

        try:
            response = self.client.create_hit(
                MaxAssignments=1,  # One annotation per task
                AutoApprovalDelayInSeconds=86400,  # Auto-approve after 24h
                LifetimeInSeconds=604800,  # 7 days to complete
                AssignmentDurationInSeconds=1800,  # 30 minutes per assignment
                Reward="0.10",  # $0.10 per annotation
                Title="Card Similarity Annotation",
                Description=f"Rate similarity between {task.card1} and {task.card2}",
                Keywords="card,game,similarity,annotation",
                Question=question_html,
                QualificationRequirements=[
                    {
                        "QualificationTypeId": "00000000000000000071",  # US locale
                        "Comparator": "EqualTo",
                        "LocaleValues": [{"Country": "US"}],
                    },
                    {
                        "QualificationTypeId": "000000000000000000L0",  # Approval rate > 95%
                        "Comparator": "GreaterThan",
                        "IntegerValues": [95],
                    },
                ],
            )

            hit_id = response["HIT"]["HITId"]
            logger.info(f"Submitted MTurk task {task.task_id} as HIT {hit_id}")
            return hit_id

        except Exception as e:
            logger.error(f"Failed to submit MTurk task: {e}")
            raise

    def get_result(self, external_task_id: str) -> AnnotationResult | None:
        """Get MTurk result.

        Args:
            external_task_id: HIT ID

        Returns:
            Annotation result or None if not ready
        """
        if not self.client:
            raise RuntimeError("MTurk client not initialized")

        try:
            # Get assignments for this HIT
            response = self.client.list_assignments_for_hit(HITId=external_task_id)

            if not response["Assignments"]:
                return None  # No assignments yet

            assignment = response["Assignments"][0]
            if assignment["AssignmentStatus"] != "Approved":
                return None  # Not approved yet

            # Parse answer from form
            answer_xml = assignment["Answer"]
            # Parse XML to extract form values
            # (Simplified - would need proper XML parsing)
            import xml.etree.ElementTree as ET

            root = ET.fromstring(answer_xml)
            answers = {}
            for answer in root.findall(".//Answer"):
                key = answer.find("QuestionIdentifier").text
                value = answer.find("FreeText").text
                answers[key] = value

            result = AnnotationResult(
                task_id="",  # Will be set by caller
                external_task_id=external_task_id,
                similarity_score=float(answers.get("similarity", 0.0)),
                similarity_type=answers.get("type", "unrelated"),
                reasoning=answers.get("reasoning", ""),
                is_substitute=answers.get("substitute", "false").lower() == "true",
                annotator_id=assignment.get("WorkerId"),
                cost=0.10,  # MTurk cost
            )

            return result

        except Exception as e:
            logger.error(f"Failed to get MTurk result: {e}")
            return None

    def estimate_cost(self, num_tasks: int) -> float:
        """Estimate MTurk cost.

        MTurk pricing (2025-2026):
        - Base reward: $0.10 per HIT (typical for simple tasks)
        - MTurk commission: 20% of reward (for requester)
          - If 10+ assignments per HIT: 40% commission
        - Total: ~$0.12 per HIT (with 20% commission) or ~$0.14 (with 40%)

        Args:
            num_tasks: Number of tasks

        Returns:
            Estimated cost in USD (~$0.12 per task including fees)
        """
        # Base reward per HIT
        reward_per_hit = 0.10
        # MTurk commission (20% for requester, 40% if 10+ assignments)
        # For single assignment HITs, use 20%
        commission_rate = 0.20
        commission = reward_per_hit * commission_rate
        # Total per HIT (reward + commission)
        cost_per_hit = reward_per_hit + commission
        
        return num_tasks * cost_per_hit
    
    def get_account_balance(self) -> dict[str, float]:
        """Get MTurk account balance.

        Returns:
            Dict with 'available' and 'on_hold' balances in USD
        """
        if not self.client:
            raise RuntimeError("MTurk client not initialized")
        
        try:
            response = self.client.get_account_balance()
            
            # Parse response (can be dict or string)
            import json
            if isinstance(response, str):
                response = json.loads(response)
            
            available = response.get('AvailableBalance', {})
            if isinstance(available, dict):
                available_amt = float(available.get('Amount', '0.00'))
            else:
                available_amt = float(available) if available else 0.00
            
            on_hold = response.get('OnHoldBalance', {})
            if isinstance(on_hold, dict):
                hold_amt = float(on_hold.get('Amount', '0.00'))
            else:
                hold_amt = float(on_hold) if on_hold else 0.00
            
            return {
                'available': available_amt,
                'on_hold': hold_amt,
            }
        except Exception as e:
            logger.error(f"Failed to get MTurk account balance: {e}")
            raise


class ScaleAIService(HumanAnnotationService):
    """Scale AI integration.

    Research: Scale AI provides:
    - High-quality annotations
    - Specialized annotators
    - Quality assurance
    - API access

    Requires: Scale AI API key
    """

    def __init__(self, api_key: str | None = None):
        """Initialize Scale AI service.

        Args:
            api_key: Scale AI API key (or use SCALE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("SCALE_API_KEY")
        self.base_url = "https://api.scale.com/v1"

        if not self.api_key:
            logger.warning("Scale AI API key not found")

    def submit_task(self, task: AnnotationTask) -> str:
        """Submit task to Scale AI.

        Args:
            task: Annotation task

        Returns:
            Task ID from Scale AI
        """
        if not self.api_key:
            raise RuntimeError("Scale AI API key not set. Set SCALE_API_KEY environment variable.")

        try:
            import requests
            import base64

            # Scale AI uses Basic auth with API key as username (password empty)
            # Format: base64(api_key:)
            auth_string = f"{self.api_key}:"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')

            # Use improved instructions if provided, otherwise use task.instructions
            instructions = task.instructions
            if not instructions or len(instructions.strip()) < 50:
                instructions = f"""
CARD SIMILARITY ANNOTATION TASK

Your task: Rate how similar two {task.game} cards are to each other.

CARDS TO COMPARE:
- Card 1: {task.card1}
- Card 2: {task.card2}

SCORING GUIDELINES (0.0 - 1.0):
0.9-1.0: Nearly identical (direct substitutes, same function)
0.7-0.8: Very similar (same role, minor differences)
0.5-0.6: Moderately similar (related function, same archetype)
0.3-0.4: Somewhat similar (loose connection, shared theme)
0.1-0.2: Marginally similar (minimal connection)
0.0-0.1: Unrelated (different function, color, archetype)

SIMILARITY TYPES:
- functional: Cards serve the same function (can replace each other)
- synergy: Cards work well together (combo, synergy)
- archetype: Cards belong to same deck type/strategy
- manabase: Cards are both lands/mana sources
- unrelated: No clear relationship

SUBSTITUTION:
- YES: Card 2 can reasonably replace Card 1 in most decks
- NO: Cards are different enough that substitution is not appropriate

REASONING:
Provide 2-3 sentences explaining:
- Why you chose this score
- What similarities/differences you noticed
- Context where they might be used together

IMPORTANT:
- Be consistent: Similar cards should get similar scores
- Use the full range: Don't cluster scores at 0.0 or 1.0
- Consider context: Some cards are similar in specific decks only
"""
            
            payload = {
                "type": "annotation",
                "instruction": instructions,
                "attachment_type": "text",
                "attachment": f"Card 1: {task.card1}\nCard 2: {task.card2}\nGame: {task.game}",
                "metadata": {
                    "task_id": task.task_id,
                    "card1": task.card1,
                    "card2": task.card2,
                    "game": task.game,
                },
            }

            # Scale AI task creation - use textcollection endpoint for text tasks
            # /task/annotation is for image annotation, /task/textcollection is for text
            response = requests.post(
                f"{self.base_url}/task/textcollection",
                headers={
                    "Authorization": f"Basic {auth_b64}",
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()

            result = response.json()
            task_id = result.get("task_id") or result.get("id")
            if not task_id:
                raise ValueError(f"Unexpected response format: {result}")
            
            logger.info(f"Submitted Scale AI task {task.task_id} as {task_id}")
            return str(task_id)

        except ImportError:
            raise RuntimeError("requests library required for Scale AI. Install: pip install requests")
        except Exception as e:
            logger.error(f"Failed to submit Scale AI task: {e}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise

    def get_result(self, external_task_id: str) -> AnnotationResult | None:
        """Get Scale AI result.

        Args:
            external_task_id: Scale AI task ID

        Returns:
            Annotation result or None if not ready
        """
        if not self.api_key:
            raise RuntimeError("Scale AI API key not set. Set SCALE_API_KEY environment variable.")

        try:
            import requests
            import base64

            # Scale AI uses Basic auth with API key as username (password empty)
            auth_string = f"{self.api_key}:"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')

            response = requests.get(
                f"{self.base_url}/task/{external_task_id}",
                headers={
                    "Authorization": f"Basic {auth_b64}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()

            data = response.json()
            status = data.get("status") or data.get("task_status")
            
            if status not in ["completed", "completed_and_approved"]:
                return None  # Not ready yet

            # Parse response (Scale AI format)
            # Response might be in 'response', 'result', or 'annotation' field
            annotation = (
                data.get("response") or 
                data.get("result") or 
                data.get("annotation") or 
                {}
            )
            
            # Handle both dict and string formats
            if isinstance(annotation, str):
                try:
                    import json
                    annotation = json.loads(annotation)
                except:
                    # If it's a string, try to extract key-value pairs
                    annotation = {"raw_response": annotation}
            
            result = AnnotationResult(
                task_id="",  # Will be set by caller
                external_task_id=external_task_id,
                similarity_score=float(annotation.get("similarity_score", annotation.get("score", 0.0))),
                similarity_type=annotation.get("similarity_type", annotation.get("type", "unrelated")),
                reasoning=annotation.get("reasoning", annotation.get("explanation", "")),
                is_substitute=annotation.get("is_substitute", annotation.get("substitute", False)),
                annotator_id=data.get("annotator_id") or data.get("worker_id"),
                cost=0.50,  # Scale AI cost (higher quality)
            )

            return result

        except Exception as e:
            logger.error(f"Failed to get Scale AI result: {e}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None

    def estimate_cost(self, num_tasks: int) -> float:
        """Estimate Scale AI cost.

        Args:
            num_tasks: Number of tasks

        Returns:
            Estimated cost in USD ($0.50 per task)
        """
        return num_tasks * 0.50


class CustomAnnotationService(HumanAnnotationService):
    """Custom annotation interface (for internal use).

    Allows queuing tasks for manual annotation via custom UI.
    """

    def __init__(self, output_dir: Path | None = None):
        """Initialize custom service.

        Args:
            output_dir: Directory to save tasks (default: annotations/human_tasks/)
        """
        if output_dir is None:
            from ..utils.paths import PATHS

            output_dir = PATHS.experiments / "annotations" / "human_tasks"
            output_dir.mkdir(parents=True, exist_ok=True)

        self.output_dir = output_dir

    def submit_task(self, task: AnnotationTask) -> str:
        """Save task to file for manual annotation.

        Args:
            task: Annotation task

        Returns:
            Task file path as ID
        """
        task_file = self.output_dir / f"{task.task_id}.json"

        task_data = {
            "task_id": task.task_id,
            "card1": task.card1,
            "card2": task.card2,
            "game": task.game,
            "instructions": task.instructions,
            "context": task.context,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }

        with open(task_file, "w") as f:
            json.dump(task_data, f, indent=2)

        logger.info(f"Saved custom annotation task to {task_file}")
        return str(task_file)

    def get_result(self, external_task_id: str) -> AnnotationResult | None:
        """Get result from completed task file.

        Args:
            external_task_id: Task file path

        Returns:
            Annotation result or None if not ready
        """
        task_file = Path(external_task_id)
        if not task_file.exists():
            return None

        try:
            with open(task_file) as f:
                data = json.load(f)

            if data.get("status") != "completed":
                return None

            annotation = data.get("annotation", {})
            result = AnnotationResult(
                task_id=data["task_id"],
                external_task_id=external_task_id,
                similarity_score=float(annotation.get("similarity_score", 0.0)),
                similarity_type=annotation.get("similarity_type", "unrelated"),
                reasoning=annotation.get("reasoning", ""),
                is_substitute=annotation.get("is_substitute", False),
                annotator_id=annotation.get("annotator_id"),
                cost=0.0,  # Internal, no cost
            )

            return result

        except Exception as e:
            logger.error(f"Failed to get custom annotation result: {e}")
            return None

    def estimate_cost(self, num_tasks: int) -> float:
        """Estimate custom service cost (free for internal).

        Args:
            num_tasks: Number of tasks

        Returns:
            0.0 (internal service)
        """
        return 0.0


def get_annotation_service(service_name: str) -> HumanAnnotationService:
    """Get annotation service by name.

    Args:
        service_name: Service name ("mturk", "scale", "custom")

    Returns:
        Annotation service instance
    """
    if service_name.lower() == "mturk":
        return MTurkService()
    elif service_name.lower() == "scale":
        return ScaleAIService()
    elif service_name.lower() == "custom":
        return CustomAnnotationService()
    else:
        raise ValueError(f"Unknown annotation service: {service_name}")

