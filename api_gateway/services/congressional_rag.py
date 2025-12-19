"""
Congressional RAG (Retrieval-Augmented Generation) service.

Provides natural language question-answering over congressional data
by combining vector search with LLM generation.
"""

from dataclasses import dataclass

import httpx

from ..config import settings
from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .weaviate_connection import CONGRESSIONAL_DATA_COLLECTION_NAME, WeaviateConnection

logger = get_logger("api_gateway.congressional_rag")

# System prompt for the LLM
SYSTEM_PROMPT = """You are an expert analyst of US congressional data. You have access to press releases, official statements, policy positions, and voting records from two House Representatives:

- **Marjorie Taylor Greene** (R-GA) - Republican from Georgia's 14th district
- **Ilhan Omar** (D-MN) - Democrat from Minnesota's 5th district

Your role is to answer questions about their positions, statements, and voting records based ONLY on the provided context documents.

Guidelines:
1. Base your answers strictly on the provided context - do not make up information
2. When comparing the two representatives, highlight specific differences in their positions
3. Cite sources by referencing the document titles when relevant
4. If the context doesn't contain enough information to answer, say so clearly
5. Be objective and factual - present what they've said/done without editorial commentary
6. For voting records, note how each representative voted if the information is available

Format your response in clear, readable paragraphs. Use bullet points for lists of positions or votes."""


@dataclass
class RAGSource:
    """A source document used in the RAG response."""

    member_name: str
    title: str
    content_preview: str
    url: str
    party: str
    state: str


@dataclass
class RAGResponse:
    """Response from the RAG system."""

    answer: str
    sources: list[RAGSource]
    model: str
    tokens_used: int | None = None


def search_congressional_context(
    question: str,
    limit: int = 8,
    member_filter: str | None = None,
) -> list[dict]:
    """
    Search congressional data for relevant context.

    Args:
        question: The user's question
        limit: Maximum number of results
        member_filter: Optional member name to filter by

    Returns:
        List of relevant documents with properties
    """
    query_vector = get_embedding(question)

    results = []
    with WeaviateConnection() as client:
        if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
            logger.error("CongressionalData collection does not exist")
            return []

        collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

        # Build filter if member specified
        from weaviate.classes.query import Filter

        filters = None
        if member_filter:
            filters = Filter.by_property("member_name").equal(member_filter)

        # Perform vector search
        response = collection.query.near_vector(
            near_vector=query_vector,
            limit=limit,
            filters=filters,
            return_properties=[
                "member_name",
                "title",
                "content_text",
                "url",
                "party",
                "state",
                "topic",
            ],
        )

        for obj in response.objects:
            results.append(obj.properties)

    return results


def format_context(documents: list[dict]) -> str:
    """Format search results into context for the LLM."""
    if not documents:
        return "No relevant documents found."

    context_parts = []
    for i, doc in enumerate(documents, 1):
        member = doc.get("member_name", "Unknown")
        party = doc.get("party", "?")
        title = doc.get("title", "Untitled")
        content = doc.get("content_text", "")

        # Truncate content to reasonable length
        if len(content) > 1500:
            content = content[:1500] + "..."

        context_parts.append(
            f"[Document {i}] {member} ({party})\n" f"Title: {title}\n" f"Content: {content}\n"
        )

    return "\n---\n".join(context_parts)


def generate_answer(
    question: str,
    context: str,
    model: str = "qwen3-coder-roo:latest",
    temperature: float = 0.3,
) -> str:
    """
    Generate an answer using Ollama LLM.

    Args:
        question: The user's question
        context: Formatted context from search results
        model: Ollama model to use
        temperature: Generation temperature (lower = more focused)

    Returns:
        Generated answer text
    """
    prompt = f"""Based on the following congressional documents, answer this question:

**Question:** {question}

**Context Documents:**
{context}

**Answer:**"""

    endpoint = settings.OLLAMA_API_ENDPOINT

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{endpoint}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "system": SYSTEM_PROMPT,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": 1024,
                    },
                },
            )
            response.raise_for_status()

            result = response.json()
            return result.get("response", "").strip()

    except httpx.TimeoutException:
        logger.error("Ollama request timed out")
        return "I'm sorry, the request timed out. Please try again with a simpler question."
    except httpx.HTTPError as e:
        logger.error(f"Ollama HTTP error: {e}")
        return f"Error communicating with the language model: {e}"
    except Exception as e:
        logger.error(f"Unexpected error in generate_answer: {e}")
        return f"An unexpected error occurred: {e}"


def answer_question(
    question: str,
    model: str = "qwen3-coder-roo:latest",
    member_filter: str | None = None,
    num_sources: int = 8,
) -> RAGResponse:
    """
    Answer a question about congressional data using RAG.

    Args:
        question: Natural language question
        model: Ollama model to use for generation
        member_filter: Optional filter to focus on one member
        num_sources: Number of source documents to retrieve

    Returns:
        RAGResponse with answer and sources
    """
    logger.info(f"RAG question: {question[:100]}...")

    # Search for relevant documents
    documents = search_congressional_context(
        question=question,
        limit=num_sources,
        member_filter=member_filter,
    )

    if not documents:
        return RAGResponse(
            answer="I couldn't find any relevant information in the congressional data to answer your question.",
            sources=[],
            model=model,
        )

    # Format context
    context = format_context(documents)

    # Generate answer
    answer = generate_answer(
        question=question,
        context=context,
        model=model,
    )

    # Build sources list
    sources = [
        RAGSource(
            member_name=doc.get("member_name", "Unknown"),
            title=doc.get("title", "Untitled"),
            content_preview=(
                doc.get("content_text", "")[:200] + "..."
                if len(doc.get("content_text", "")) > 200
                else doc.get("content_text", "")
            ),
            url=doc.get("url", ""),
            party=doc.get("party", "?"),
            state=doc.get("state", "?"),
        )
        for doc in documents
    ]

    logger.info(f"RAG response generated with {len(sources)} sources")

    return RAGResponse(
        answer=answer,
        sources=sources,
        model=model,
    )


# CLI for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m api_gateway.services.congressional_rag 'your question here'")
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    print(f"\nQuestion: {question}\n")
    print("Searching and generating answer...\n")

    response = answer_question(question)

    print("=" * 60)
    print("ANSWER:")
    print("=" * 60)
    print(response.answer)
    print("\n" + "=" * 60)
    print(f"SOURCES ({len(response.sources)}):")
    print("=" * 60)
    for src in response.sources:
        print(f"  [{src.party}] {src.member_name}: {src.title[:50]}...")
