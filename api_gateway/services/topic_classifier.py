"""
Topic classifier for congressional data using Ollama LLM.

Classifies votes and member content into policy topics for semantic querying.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# Policy topic taxonomy (includes 2025 hot topics)
TOPICS = [
    "healthcare",           # Healthcare, Medicare, Medicaid, insurance
    "immigration",          # Immigration, border security, asylum, visas
    "defense",              # Military, national security, veterans affairs
    "economy",              # Jobs, trade, tariffs, economic policy
    "environment",          # Climate, EPA, conservation, pollution
    "energy",               # Oil, gas, renewables, pipelines, drilling
    "education",            # Schools, student loans, higher education
    "infrastructure",       # Transportation, roads, bridges, broadband
    "budget",               # Taxes, spending, debt ceiling, appropriations
    "civil_rights",         # Voting rights, discrimination, equality
    "gun_policy",           # Second amendment, firearms, gun control
    "agriculture",          # Farming, rural development, food policy, farm bill
    "foreign_policy",       # International relations, diplomacy, sanctions
    "technology",           # Tech regulation, privacy, cybersecurity, AI
    "crypto",               # Cryptocurrency, digital assets, blockchain, stablecoins
    "housing",              # Housing, HUD, homelessness, rent
    "labor",                # Workers rights, unions, wages, OSHA
    "social_security",      # Social security, retirement, pensions
    "criminal_justice",     # Law enforcement, prisons, courts, crime
    "procedural",           # Parliamentary motions, rules, procedures
]

TOPIC_DESCRIPTIONS = {
    "healthcare": "Healthcare, Medicare, Medicaid, health insurance, hospitals, pharmaceuticals, public health",
    "immigration": "Immigration, border security, asylum, visas, deportation, DACA, refugees",
    "defense": "Military, national security, Pentagon, armed forces, defense spending, veterans",
    "economy": "Jobs, employment, trade, tariffs, economic growth, small business, manufacturing",
    "environment": "Climate change, EPA, conservation, pollution, endangered species, national parks",
    "energy": "Oil, gas, renewable energy, pipelines, drilling, nuclear, solar, wind",
    "education": "Schools, K-12, student loans, higher education, teachers, STEM",
    "infrastructure": "Transportation, roads, bridges, airports, broadband, water systems",
    "budget": "Taxes, federal spending, debt ceiling, appropriations, deficit, fiscal policy",
    "civil_rights": "Voting rights, discrimination, civil liberties, equality, LGBTQ rights",
    "gun_policy": "Second amendment, firearms, gun control, background checks, assault weapons",
    "agriculture": "Farming, rural development, food stamps, SNAP, crop insurance, ranching",
    "foreign_policy": "International relations, diplomacy, sanctions, treaties, foreign aid, NATO",
    "technology": "Tech regulation, data privacy, cybersecurity, AI, social media, antitrust",
    "crypto": "Cryptocurrency, digital assets, blockchain, Bitcoin, stablecoins, CFTC, SEC crypto regulation",
    "housing": "Housing, HUD, homelessness, rent, mortgages, affordable housing",
    "labor": "Workers rights, unions, minimum wage, OSHA, workplace safety, pensions",
    "social_security": "Social security, Medicare, retirement benefits, disability",
    "criminal_justice": "Law enforcement, prisons, courts, sentencing, police reform",
    "procedural": "Parliamentary procedure, motions, rules, amendments, floor votes",
}


@dataclass
class ClassificationResult:
    """Result of topic classification."""

    topics: List[str]
    confidence: float
    reasoning: str


def get_ollama_endpoint() -> str:
    """Get Ollama API endpoint from environment."""
    return os.getenv("OLLAMA_API_ENDPOINT", "http://127.0.0.1:11434")


def get_classification_model() -> str:
    """Get model to use for classification."""
    # Use qwen3-coder which should already be loaded
    return os.getenv("OLLAMA_CLASSIFICATION_MODEL", "qwen3-coder-roo:latest")


def check_ollama_health(timeout: float = 5.0) -> bool:
    """Check if Ollama is responsive."""
    endpoint = get_ollama_endpoint()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{endpoint}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


def warmup_model(timeout: float = 300.0) -> bool:
    """
    Warm up the classification model by loading it into memory.

    This sends a simple prompt to force model loading, which can take
    1-2 minutes for large models on first use.

    Args:
        timeout: Maximum time to wait for model loading

    Returns:
        True if model is ready, False otherwise
    """
    endpoint = get_ollama_endpoint()
    model = get_classification_model()

    logger.info("Warming up model %s (this may take 1-2 minutes)...", model)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{endpoint}/api/generate",
                json={
                    "model": model,
                    "prompt": "Reply with just 'ready'",
                    "stream": False,
                    "options": {"num_predict": 10},
                },
            )
            if response.status_code == 200:
                logger.info("Model %s is ready", model)
                return True
            else:
                logger.error("Model warmup failed: %s", response.text)
                return False
    except httpx.TimeoutException:
        logger.error("Model warmup timed out after %.0fs", timeout)
        return False
    except Exception as e:
        logger.error("Model warmup error: %s", e)
        return False


# Track if model has been warmed up this session
_model_warmed_up = False


def ensure_model_ready(warmup_timeout: float = 300.0) -> bool:
    """
    Ensure the classification model is loaded and ready.

    Only warms up once per session to avoid repeated delays.

    Returns:
        True if model is ready, False otherwise
    """
    global _model_warmed_up

    if _model_warmed_up:
        return True

    if not check_ollama_health():
        logger.error("Ollama is not running at %s", get_ollama_endpoint())
        return False

    if warmup_model(timeout=warmup_timeout):
        _model_warmed_up = True
        return True

    return False


def classify_text(
    title: str,
    content: str,
    max_topics: int = 3,
    timeout: float = 120.0,
) -> ClassificationResult:
    """
    Classify text into policy topics using Ollama LLM.

    Args:
        title: Document or vote title
        content: Main content text (will be truncated)
        max_topics: Maximum number of topics to return
        timeout: Request timeout in seconds

    Returns:
        ClassificationResult with topics, confidence, and reasoning
    """
    # Ensure model is loaded before attempting classification
    if not ensure_model_ready():
        return ClassificationResult(
            topics=[],
            confidence=0.0,
            reasoning="Model not available - Ollama may not be running or model failed to load",
        )

    endpoint = get_ollama_endpoint()
    model = get_classification_model()

    # Truncate content to avoid token limits
    content_preview = content[:2000] if len(content) > 2000 else content

    # Build the prompt
    topics_list = "\n".join(f"- {t}: {TOPIC_DESCRIPTIONS[t]}" for t in TOPICS)

    prompt = f"""Classify this congressional document into 1-{max_topics} policy topics.

AVAILABLE TOPICS:
{topics_list}

DOCUMENT:
Title: {title}
Content: {content_preview}

INSTRUCTIONS:
1. Identify the main policy topics this document relates to
2. Return ONLY topics from the list above
3. Return 1-{max_topics} topics, most relevant first
4. For procedural votes (motions to recommit, rules, etc.), include "procedural"

Respond in JSON format:
{{"topics": ["topic1", "topic2"], "confidence": 0.85, "reasoning": "Brief explanation"}}

JSON response:"""

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{endpoint}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # Low temperature for consistent classification
                        "num_predict": 200,
                    },
                },
            )
            response.raise_for_status()

            result = response.json()
            text = result.get("response", "").strip()

            # Parse JSON from response
            # Handle potential markdown code blocks
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)

            # Validate topics
            valid_topics = [t for t in data.get("topics", []) if t in TOPICS]
            if not valid_topics:
                valid_topics = ["procedural"]  # Default fallback

            return ClassificationResult(
                topics=valid_topics[:max_topics],
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
            )

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse classification JSON: %s", e)
        return ClassificationResult(
            topics=["procedural"],
            confidence=0.3,
            reasoning="Failed to parse LLM response",
        )
    except httpx.HTTPError as e:
        logger.error("Ollama request failed: %s", e)
        return ClassificationResult(
            topics=[],
            confidence=0.0,
            reasoning=f"HTTP error: {e}",
        )
    except Exception as e:
        logger.error("Classification failed: %s", e)
        return ClassificationResult(
            topics=[],
            confidence=0.0,
            reasoning=f"Error: {e}",
        )


def classify_vote(
    vote_question: str,
    bill_number: Optional[str],
    bill_title: Optional[str],
    vote_type: str,
) -> ClassificationResult:
    """
    Classify a congressional vote into policy topics.

    Args:
        vote_question: The question being voted on
        bill_number: Bill number (e.g., "H.R. 1234")
        bill_title: Bill title/description
        vote_type: Type of vote

    Returns:
        ClassificationResult with topics
    """
    # Build content from vote metadata
    parts = [f"Vote Question: {vote_question}"]
    if bill_number:
        parts.append(f"Bill Number: {bill_number}")
    if bill_title:
        parts.append(f"Bill Title: {bill_title}")
    parts.append(f"Vote Type: {vote_type}")

    content = "\n".join(parts)
    title = bill_title or vote_question or "Congressional Vote"

    return classify_text(title, content)


def batch_classify(
    items: List[dict],
    batch_size: int = 10,
    progress_callback=None,
) -> List[ClassificationResult]:
    """
    Classify multiple items in batches.

    Args:
        items: List of dicts with 'title' and 'content' keys
        batch_size: Number of items per progress update
        progress_callback: Optional callback(current, total, message)

    Returns:
        List of ClassificationResult for each item
    """
    results = []
    total = len(items)

    for i, item in enumerate(items):
        result = classify_text(
            title=item.get("title", ""),
            content=item.get("content", ""),
        )
        results.append(result)

        if progress_callback and (i + 1) % batch_size == 0:
            progress_callback(i + 1, total, f"Classified {i + 1}/{total} items")

    if progress_callback:
        progress_callback(total, total, f"Classification complete: {total} items")

    return results


def classify_congressional_collection(
    limit: int = 0,
    skip_classified: bool = True,
    progress_callback=None,
) -> dict:
    """
    Classify all congressional data in Weaviate.

    Args:
        limit: Maximum items to classify (0 = all)
        skip_classified: Skip items that already have policy_topics
        progress_callback: Optional callback(current, total, message)

    Returns:
        Dict with classification statistics
    """
    # Import here to avoid circular imports
    from .weaviate_connection import WeaviateConnection, CONGRESSIONAL_DATA_COLLECTION_NAME

    stats = {
        "total_items": 0,
        "classified": 0,
        "skipped": 0,
        "errors": 0,
    }

    with WeaviateConnection() as client:
        if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
            logger.error("CongressionalData collection does not exist")
            return stats

        collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

        # Get total count
        agg = collection.aggregate.over_all(total_count=True)
        total = agg.total_count or 0
        stats["total_items"] = total

        if total == 0:
            logger.info("No items to classify")
            return stats

        logger.info("Found %d items to process", total)

        # Fetch objects in batches
        classified_count = 0
        processed = 0

        for obj in collection.iterator(
            include_vector=False,
            return_properties=["title", "content_text", "policy_topics"],
        ):
            processed += 1

            # Check if already classified
            existing_topics = obj.properties.get("policy_topics", [])
            if skip_classified and existing_topics:
                stats["skipped"] += 1
                continue

            title = obj.properties.get("title", "")
            content = obj.properties.get("content_text", "")

            if not title and not content:
                stats["skipped"] += 1
                continue

            # Classify
            try:
                result = classify_text(title, content)
                if result.topics:
                    # Update the object
                    collection.data.update(
                        uuid=obj.uuid,
                        properties={"policy_topics": result.topics},
                    )
                    classified_count += 1
                    stats["classified"] += 1

                    if progress_callback:
                        progress_callback(
                            classified_count,
                            total,
                            f"Classified: {title[:50]}... -> {result.topics}",
                        )
                else:
                    stats["errors"] += 1
                    logger.warning("No topics returned for: %s", title[:50])

            except Exception as exc:
                stats["errors"] += 1
                logger.error("Failed to classify %s: %s", title[:50], exc)

            # Check limit
            if limit > 0 and classified_count >= limit:
                logger.info("Reached classification limit of %d", limit)
                break

    logger.info(
        "Classification complete: %d classified, %d skipped, %d errors",
        stats["classified"],
        stats["skipped"],
        stats["errors"],
    )
    return stats


# CLI for testing and bulk classification
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Topic classifier for congressional data")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Test command
    test_parser = subparsers.add_parser("test", help="Test classification")
    test_parser.add_argument("--title", default="Test Vote", help="Document title")
    test_parser.add_argument("--content", default="This is a test", help="Document content")
    test_parser.add_argument("--vote", action="store_true", help="Test vote classification")

    # Classify-all command
    classify_parser = subparsers.add_parser("classify-all", help="Classify all congressional data")
    classify_parser.add_argument("--limit", type=int, default=0, help="Max items to classify (0=all)")
    classify_parser.add_argument("--force", action="store_true", help="Re-classify already classified items")

    # Warmup command
    subparsers.add_parser("warmup", help="Warm up the classification model")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.command == "test" or args.command is None:
        if hasattr(args, "vote") and args.vote:
            result = classify_vote(
                vote_question="On Passage",
                bill_number="H.R. 3668",
                bill_title="Improving Interagency Coordination for Pipeline Reviews Act",
                vote_type="YEA-AND-NAY",
            )
        else:
            title = getattr(args, "title", "Test Vote")
            content = getattr(args, "content", "This is a test")
            result = classify_text(title, content)

        print(f"Topics: {result.topics}")
        print(f"Confidence: {result.confidence}")
        print(f"Reasoning: {result.reasoning}")

    elif args.command == "warmup":
        print("Warming up model...")
        if ensure_model_ready():
            print("Model is ready!")
        else:
            print("Failed to warm up model")

    elif args.command == "classify-all":
        def progress(current, total, msg):
            print(f"[{current}/{total}] {msg}")

        stats = classify_congressional_collection(
            limit=args.limit,
            skip_classified=not args.force,
            progress_callback=progress,
        )
        print(f"\nResults: {json.dumps(stats, indent=2)}")
