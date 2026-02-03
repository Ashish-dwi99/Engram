"""Retrieval scoring functions for Engram memory search."""

import math
import re
from typing import Dict, List, Any, Optional, Set


def composite_score(similarity: float, strength: float) -> float:
    """Calculate composite score from similarity and strength."""
    return similarity * strength


def tokenize(text: str) -> List[str]:
    """Simple tokenization for BM25 scoring."""
    # Lowercase and split on non-alphanumeric
    text = text.lower()
    tokens = re.findall(r'\b\w+\b', text)
    return tokens


def calculate_bm25_score(
    query_terms: Set[str],
    doc_terms: List[str],
    doc_freq: Dict[str, int],
    total_docs: int,
    avg_doc_len: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """Calculate BM25 score for a document against query terms.

    Args:
        query_terms: Set of query terms
        doc_terms: List of terms in the document
        doc_freq: Document frequency for each term (how many docs contain it)
        total_docs: Total number of documents
        avg_doc_len: Average document length
        k1: Term frequency saturation parameter (default 1.5)
        b: Document length normalization parameter (default 0.75)

    Returns:
        BM25 score (higher is better match)
    """
    if not doc_terms or not query_terms:
        return 0.0

    doc_len = len(doc_terms)
    if avg_doc_len == 0:
        avg_doc_len = doc_len or 1

    # Count term frequencies in document
    term_freq: Dict[str, int] = {}
    for term in doc_terms:
        term_freq[term] = term_freq.get(term, 0) + 1

    score = 0.0
    for term in query_terms:
        if term not in term_freq:
            continue

        tf = term_freq[term]
        df = doc_freq.get(term, 1)

        # IDF component with smoothing
        idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)

        # TF component with saturation and length normalization
        tf_component = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_doc_len))

        score += idf * tf_component

    return score


def calculate_keyword_score(
    query_terms: Set[str],
    memory_content: str,
    echo_keywords: Optional[List[str]] = None,
    echo_paraphrases: Optional[List[str]] = None,
) -> float:
    """Calculate keyword match score for a memory.

    This is a simpler alternative to full BM25 when corpus statistics aren't available.

    Args:
        query_terms: Set of query terms (lowercase)
        memory_content: The memory content text
        echo_keywords: Keywords from echo encoding
        echo_paraphrases: Paraphrases from echo encoding

    Returns:
        Keyword match score between 0 and 1
    """
    if not query_terms:
        return 0.0

    # Tokenize memory content
    content_terms = set(tokenize(memory_content))

    # Add echo keywords
    if echo_keywords:
        content_terms.update(kw.lower() for kw in echo_keywords)

    # Add paraphrase terms
    if echo_paraphrases:
        for paraphrase in echo_paraphrases:
            content_terms.update(tokenize(paraphrase))

    # Calculate Jaccard-like overlap score
    if not content_terms:
        return 0.0

    matches = query_terms & content_terms
    if not matches:
        return 0.0

    # Score based on proportion of query terms matched
    # Normalize by query length for consistent scoring
    score = len(matches) / len(query_terms)

    return score


def hybrid_score(
    semantic_score: float,
    keyword_score: float,
    alpha: float = 0.7,
) -> float:
    """Combine semantic and keyword scores using weighted average.

    Args:
        semantic_score: Vector similarity score (0-1)
        keyword_score: Keyword match score (0-1)
        alpha: Weight for semantic score (default 0.7 = 70% semantic, 30% keyword)

    Returns:
        Combined hybrid score
    """
    return alpha * semantic_score + (1 - alpha) * keyword_score


class HybridSearcher:
    """Helper class for hybrid search across memories."""

    def __init__(self, alpha: float = 0.7):
        """Initialize hybrid searcher.

        Args:
            alpha: Weight for semantic vs keyword search (0-1).
                   Higher values favor semantic search.
        """
        self.alpha = alpha

    def score_memory(
        self,
        query_terms: Set[str],
        semantic_similarity: float,
        memory_content: str,
        echo_keywords: Optional[List[str]] = None,
        echo_paraphrases: Optional[List[str]] = None,
        strength: float = 1.0,
    ) -> Dict[str, float]:
        """Score a memory using hybrid search.

        Args:
            query_terms: Tokenized query terms
            semantic_similarity: Vector similarity score
            memory_content: Memory content text
            echo_keywords: Echo-encoded keywords
            echo_paraphrases: Echo-encoded paraphrases
            strength: Memory strength for composite scoring

        Returns:
            Dict with semantic_score, keyword_score, hybrid_score, composite_score
        """
        keyword_score = calculate_keyword_score(
            query_terms=query_terms,
            memory_content=memory_content,
            echo_keywords=echo_keywords,
            echo_paraphrases=echo_paraphrases,
        )

        hybrid = hybrid_score(semantic_similarity, keyword_score, self.alpha)

        return {
            "semantic_score": semantic_similarity,
            "keyword_score": keyword_score,
            "hybrid_score": hybrid,
            "composite_score": composite_score(hybrid, strength),
        }
