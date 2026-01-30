"""
EchoMem - Multi-modal echo encoding for stronger memory retention.

Inspired by human cognition: when we vocalize or rehearse information,
it creates stronger memory traces than passive observation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from engram.utils.prompts import ECHO_PROCESSING_PROMPT

logger = logging.getLogger(__name__)


class EchoDepth(str, Enum):
    """Echo processing depth levels."""
    SHALLOW = "shallow"   # Keywords only - minimal processing
    MEDIUM = "medium"     # Keywords + paraphrase
    DEEP = "deep"         # Full multi-modal echo


@dataclass
class EchoResult:
    """Result of echo processing."""
    raw: str
    paraphrase: Optional[str]
    keywords: List[str]
    implications: List[str]
    question_form: Optional[str]
    category: Optional[str]
    importance: float  # 0.0 - 1.0
    echo_depth: EchoDepth
    strength_multiplier: float  # Based on echo depth

    def to_metadata(self) -> Dict[str, Any]:
        """Convert to metadata dict for storage."""
        return {
            "echo_paraphrase": self.paraphrase,
            "echo_keywords": self.keywords,
            "echo_implications": self.implications,
            "echo_question_form": self.question_form,
            "echo_category": self.category,
            "echo_importance": self.importance,
            "echo_depth": self.echo_depth.value,
        }


class EchoProcessor:
    """Processes memories through multi-modal echo encoding."""

    # Strength multipliers for each echo depth
    STRENGTH_MULTIPLIERS = {
        EchoDepth.SHALLOW: 1.0,
        EchoDepth.MEDIUM: 1.3,
        EchoDepth.DEEP: 1.6,
    }

    def __init__(self, llm, config: Optional[Dict[str, Any]] = None):
        self.llm = llm
        self.config = config or {}
        self.auto_depth = self.config.get("auto_depth", True)
        self.default_depth = EchoDepth(self.config.get("default_depth", "medium"))

    def process(
        self,
        content: str,
        depth: Optional[EchoDepth] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> EchoResult:
        """
        Process content through echo encoding.

        Args:
            content: The raw memory content
            depth: Override echo depth (if None, auto-detect based on importance)
            context: Additional context for importance assessment

        Returns:
            EchoResult with multi-modal representations
        """
        # Determine echo depth
        if depth is None and self.auto_depth:
            depth = self._assess_depth(content, context)
        elif depth is None:
            depth = self.default_depth

        # Process based on depth
        if depth == EchoDepth.SHALLOW:
            return self._shallow_echo(content)
        elif depth == EchoDepth.MEDIUM:
            return self._medium_echo(content)
        else:
            return self._deep_echo(content)

    def _assess_depth(
        self, content: str, context: Optional[Dict[str, Any]] = None
    ) -> EchoDepth:
        """
        Auto-detect appropriate echo depth based on content signals.

        Signals that increase importance:
        - Explicit importance markers ("important", "remember", "always")
        - Contains numbers (IDs, phone numbers, etc.)
        - Contains proper nouns (names, places)
        - Contains dates
        - Is a preference/habit statement
        - Contains credentials/secrets markers
        - Repeated in context
        """
        signals = 0
        content_lower = content.lower()

        # Explicit importance markers
        importance_patterns = [
            r'\b(important|remember|don\'t forget|always|never|must|critical)\b',
        ]
        for pattern in importance_patterns:
            if re.search(pattern, content_lower):
                signals += 2
                break

        # Contains significant numbers (3+ digits)
        if re.search(r'\d{3,}', content):
            signals += 1

        # Contains dates
        date_patterns = [
            r'\d{1,2}/\d{1,2}(/\d{2,4})?',
            r'\d{1,2}-\d{1,2}(-\d{2,4})?',
            r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\b',
        ]
        for pattern in date_patterns:
            if re.search(pattern, content_lower):
                signals += 1
                break

        # Contains proper nouns (simple heuristic: capitalized words not at start)
        words = content.split()
        if len(words) > 1:
            proper_nouns = [w for w in words[1:] if w and w[0].isupper()]
            if proper_nouns:
                signals += 1

        # Is a preference statement
        preference_patterns = [
            r'\b(prefer|like|love|hate|favorite|always use|never use)\b',
        ]
        for pattern in preference_patterns:
            if re.search(pattern, content_lower):
                signals += 1
                break

        # Contains credential/secret markers
        secret_patterns = [
            r'\b(password|api[_\s]?key|token|secret|credential|auth)\b',
        ]
        for pattern in secret_patterns:
            if re.search(pattern, content_lower):
                signals += 2
                break

        # Context signals
        if context:
            # Mentioned multiple times in conversation
            if context.get("mention_count", 0) > 1:
                signals += 1
            # User explicitly marked as important
            if context.get("user_marked_important"):
                signals += 2

        # Map signals to depth
        if signals >= 3:
            return EchoDepth.DEEP
        elif signals >= 1:
            return EchoDepth.MEDIUM
        return EchoDepth.SHALLOW

    def _shallow_echo(self, content: str) -> EchoResult:
        """Shallow echo: keywords extraction only (no LLM call)."""
        keywords = self._extract_keywords_simple(content)

        return EchoResult(
            raw=content,
            paraphrase=None,
            keywords=keywords,
            implications=[],
            question_form=None,
            category=None,
            importance=0.3,
            echo_depth=EchoDepth.SHALLOW,
            strength_multiplier=self.STRENGTH_MULTIPLIERS[EchoDepth.SHALLOW],
        )

    def _medium_echo(self, content: str) -> EchoResult:
        """Medium echo: keywords + paraphrase."""
        try:
            prompt = ECHO_PROCESSING_PROMPT.format(
                content=content,
                depth="medium",
                depth_instructions="Generate: paraphrase, keywords, category. Skip: implications, question_form.",
            )
            response = self.llm.generate(prompt)
            parsed = self._parse_echo_response(response)

            return EchoResult(
                raw=content,
                paraphrase=parsed.get("paraphrase"),
                keywords=parsed.get("keywords", []),
                implications=[],
                question_form=None,
                category=parsed.get("category"),
                importance=parsed.get("importance", 0.5),
                echo_depth=EchoDepth.MEDIUM,
                strength_multiplier=self.STRENGTH_MULTIPLIERS[EchoDepth.MEDIUM],
            )
        except Exception as e:
            logger.warning(f"Medium echo failed, falling back to shallow: {e}")
            return self._shallow_echo(content)

    def _deep_echo(self, content: str) -> EchoResult:
        """Deep echo: full multi-modal processing."""
        try:
            prompt = ECHO_PROCESSING_PROMPT.format(
                content=content,
                depth="deep",
                depth_instructions="Generate ALL fields: paraphrase, keywords, implications, question_form, category.",
            )
            response = self.llm.generate(prompt)
            parsed = self._parse_echo_response(response)

            return EchoResult(
                raw=content,
                paraphrase=parsed.get("paraphrase"),
                keywords=parsed.get("keywords", []),
                implications=parsed.get("implications", []),
                question_form=parsed.get("question_form"),
                category=parsed.get("category"),
                importance=parsed.get("importance", 0.8),
                echo_depth=EchoDepth.DEEP,
                strength_multiplier=self.STRENGTH_MULTIPLIERS[EchoDepth.DEEP],
            )
        except Exception as e:
            logger.warning(f"Deep echo failed, falling back to medium: {e}")
            return self._medium_echo(content)

    def _extract_keywords_simple(self, content: str) -> List[str]:
        """Simple keyword extraction without LLM."""
        # Remove common stop words and extract significant terms
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
            'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
            'from', 'as', 'into', 'through', 'during', 'before', 'after',
            'above', 'below', 'between', 'under', 'again', 'further', 'then',
            'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all',
            'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
            'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just',
            'and', 'but', 'if', 'or', 'because', 'until', 'while', 'this',
            'that', 'these', 'those', 'i', 'me', 'my', 'myself', 'we', 'our',
            'you', 'your', 'he', 'him', 'his', 'she', 'her', 'it', 'its',
            'they', 'them', 'their', 'what', 'which', 'who', 'whom',
        }

        # Tokenize and filter
        words = re.findall(r'\b[a-zA-Z]+\b', content.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        # Get unique keywords, preserving order
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)

        return unique[:10]  # Limit to 10 keywords

    def _parse_echo_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response for echo data."""
        # Try to extract JSON from response
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try parsing entire response as JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Fallback: extract what we can
        result: Dict[str, Any] = {}

        # Try to find paraphrase
        para_match = re.search(r'"paraphrase":\s*"([^"]+)"', response)
        if para_match:
            result["paraphrase"] = para_match.group(1)

        # Try to find keywords
        kw_match = re.search(r'"keywords":\s*\[([^\]]+)\]', response)
        if kw_match:
            keywords = re.findall(r'"([^"]+)"', kw_match.group(1))
            result["keywords"] = keywords

        return result

    def reecho(self, memory: Dict[str, Any]) -> EchoResult:
        """
        Re-echo a memory on retrieval to strengthen it.

        This simulates the human process of rehearsal strengthening memory.
        """
        content = memory.get("memory", "")
        metadata = memory.get("metadata", {})

        # Get current echo depth and go one level deeper if possible
        current_depth = metadata.get("echo_depth", "shallow")

        if current_depth == "shallow":
            new_depth = EchoDepth.MEDIUM
        elif current_depth == "medium":
            new_depth = EchoDepth.DEEP
        else:
            new_depth = EchoDepth.DEEP  # Already at max

        return self.process(content, depth=new_depth)
