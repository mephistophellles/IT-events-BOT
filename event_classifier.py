import os
import logging
import json
import re
from typing import Optional, Tuple
from config import (
    USE_GEMINI_CLASSIFIER,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    CLASSIFIER_CONFIDENCE_THRESHOLD,
    USE_CLAUDE_CLASSIFIER,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
)

logger = logging.getLogger(__name__)


def _build_classification_prompt(text: str) -> str:
    """Build the shared classification prompt for LLM classifiers."""
    return """Ты эксперт по определению релевантности событий для предпринимателей и стартапов.

ОСОБЕННО релевантно (наивысший приоритет):
- Встречи с инвесторами / investor meetings
- Питч-сессии / pitch sessions, Demo Day
- Венчурное финансирование, раунды инвестиций
- Акселераторы, инкубаторы (набор и мероприятия)

Также релевантно:
- Стартапы и предпринимательство
- Бизнес-конференции и митапы для бизнеса
- Технологии для бизнеса (SaaS, B2B)
- Нетворкинг для предпринимателей

НЕ релевантно:
- Дизайн (UI/UX, графический дизайн) без бизнес-контекста
- Искусство, творчество, личные хобби
- HR-конференции, госзакупки, медицина
- События для других профессиональных групп без связи с предпринимательством

Текст события:
{}

Ответь строго в формате JSON: {{"relevant": true/false, "confidence": 0.0-1.0, "reason": "..."}}""".format(text)


class EventClassifier:
    """Classifier to determine if an event is relevant for entrepreneurs/startups.

    Priority order:
    1. Claude API (if USE_CLAUDE_CLASSIFIER=true and ANTHROPIC_API_KEY set)
    2. Gemini API (if USE_GEMINI_CLASSIFIER=true and GEMINI_API_KEY set)
    3. BART zero-shot (local model, ~1.5GB)
    4. Keyword-based fallback
    """

    def __init__(self):
        self.confidence_threshold = CLASSIFIER_CONFIDENCE_THRESHOLD
        self.claude_client = None
        self.gemini_model = None
        self.bart_classifier = None

        # Try Claude first
        if USE_CLAUDE_CLASSIFIER and ANTHROPIC_API_KEY:
            try:
                import anthropic
                self.claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                logger.info(f"Using Claude model '{CLAUDE_MODEL}' for event classification")
            except Exception as e:
                logger.warning(f"Could not initialize Claude client: {e}")

        # Try Gemini if Claude not available
        if not self.claude_client and USE_GEMINI_CLASSIFIER and GEMINI_API_KEY:
            try:
                import google.generativeai as genai  # type: ignore
                genai.configure(api_key=GEMINI_API_KEY)
                self.gemini_model = genai.GenerativeModel(GEMINI_MODEL)
                logger.info(f"Using Gemini model '{GEMINI_MODEL}' for event classification")
            except Exception as e:
                logger.warning(f"Could not initialize Gemini model: {e}, falling back to local model")

        # Load BART if no LLM API available
        if not self.claude_client and not self.gemini_model:
            self._init_bart()

    def _init_bart(self):
        """Initialize local BART model for zero-shot classification."""
        try:
            from transformers import pipeline
            import torch

            try:
                self.bart_classifier = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-large-mnli",
                    device=0 if torch.cuda.is_available() else -1
                )
                logger.info("Using BART zero-shot classifier for event classification")
            except Exception as e:
                logger.warning(f"Could not load BART model: {e}, using keyword-based fallback")
        except ImportError:
            logger.warning("Transformers library not found, using keyword-based classification")

    def is_relevant_event(self, title: str, description: str = "") -> Tuple[bool, float]:
        """Determine if an event is relevant for entrepreneurs/startups.

        Returns:
            (is_relevant, confidence_score)
        """
        if not title:
            return False, 0.0

        text = f"{title}. {description}"[:1000]

        if self.claude_client:
            return self._classify_with_claude(text)
        elif self.gemini_model:
            return self._classify_with_gemini(text)
        elif self.bart_classifier:
            return self._classify_with_bart(text)
        else:
            return self._classify_with_keywords(text)

    def _classify_with_claude(self, text: str) -> Tuple[bool, float]:
        """Classify event using Claude API."""
        try:
            prompt = _build_classification_prompt(text)
            message = self.claude_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}]
            )
            raw_text = message.content[0].text.strip() if message.content else ""
            logger.debug(f"Claude raw response: {raw_text}")

            json_text = self._extract_json(raw_text)
            if not json_text:
                logger.warning("Claude response did not contain JSON, falling back to keywords")
                return self._classify_with_keywords(text)

            data = json.loads(json_text)
            is_relevant = bool(data.get("relevant"))
            confidence = float(data.get("confidence", 0.5))
            return is_relevant, confidence
        except Exception as e:
            logger.error(f"Error classifying with Claude: {e}", exc_info=True)
            return self._classify_with_keywords(text)

    def _classify_with_gemini(self, text: str) -> Tuple[bool, float]:
        """Classify event using Gemini."""
        try:
            prompt = _build_classification_prompt(text)
            response = self.gemini_model.generate_content(prompt)
            raw_text = (response.text or "").strip()
            logger.debug(f"Gemini raw response: {raw_text}")

            json_text = self._extract_json(raw_text)
            if not json_text:
                logger.warning("Gemini response did not contain JSON, falling back to keywords")
                return self._classify_with_keywords(text)

            data = json.loads(json_text)
            is_relevant = bool(data.get("relevant"))
            confidence = float(data.get("confidence", 0.5))
            return is_relevant, confidence
        except Exception as e:
            logger.error(f"Error classifying with Gemini: {e}", exc_info=True)
            return self._classify_with_keywords(text)

    def _classify_with_bart(self, text: str) -> Tuple[bool, float]:
        """Classify event using local BART zero-shot model."""
        try:
            candidate_labels = [
                "событие для предпринимателей и стартапов",
                "бизнес-конференция или митап",
                "событие для дизайнеров",
                "событие для других профессий",
                "общее мероприятие"
            ]

            result = self.bart_classifier(text, candidate_labels)
            top_label = result['labels'][0]
            top_score = result['scores'][0]

            logger.debug(f"BART classification: label={top_label}, score={top_score:.2f}")

            is_relevant = top_label in candidate_labels[:2]
            confidence = top_score if is_relevant else (1.0 - top_score)

            if not is_relevant and top_score > 0.3:
                for i, label in enumerate(candidate_labels[:2]):
                    if result['scores'][i] > 0.25:
                        is_relevant = True
                        confidence = result['scores'][i]
                        logger.debug(f"Overriding classification based on secondary label: {label}")
                        break

            return is_relevant, confidence
        except Exception as e:
            logger.error(f"Error classifying with BART: {e}", exc_info=True)
            return self._classify_with_keywords(text)

    def _classify_with_keywords(self, text: str) -> Tuple[bool, float]:
        """Fallback keyword-based classification."""
        text_lower = text.lower()

        positive_keywords = [
            'стартап', 'startup', 'предприниматель', 'entrepreneur', 'бизнес', 'business',
            'инвестиции', 'investment', 'венчур', 'venture', 'акселератор', 'accelerator',
            'инкубатор', 'incubator', 'питч', 'pitch', 'демо-день', 'demo day',
            'нетворкинг', 'networking', 'saas', 'b2b', 'b2c', 'технологии для бизнеса',
            'бизнес-конференция', 'бизнес-митап', 'entrepreneurship', 'конференция', 'conference',
            'митап', 'meetup', 'workshop', 'воркшоп', 'семинар', 'seminar',
            'инвестор', 'investor', 'раунд', 'round', 'фонд', 'fund',
        ]

        negative_keywords = [
            'дизайн', 'design', 'ui/ux', 'графический дизайн', 'иллюстрация',
            'фотография', 'photography', 'искусство', 'art', 'творчество',
            'хобби', 'hobby', 'личное развитие', 'йога', 'медитация',
            'госзакупки', 'тендер', 'медицина', 'hr-конференция',
        ]

        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)

        logger.debug(f"Keyword classification: positive={positive_count}, negative={negative_count}")

        total_keywords = positive_count + negative_count
        if total_keywords == 0:
            if any(w in text_lower for w in ['event', 'событие', 'конференция', 'conference', 'meetup', 'митап']):
                return True, 0.4
            return False, 0.3

        confidence = positive_count / total_keywords
        if positive_count > 1:
            confidence = min(0.9, confidence + 0.1 * (positive_count - 1))

        is_relevant = positive_count > negative_count and positive_count > 0
        return is_relevant, confidence

    def _extract_json(self, raw_text: str) -> Optional[str]:
        """Extract JSON object from LLM response."""
        try:
            if not raw_text:
                return None

            if "```" in raw_text:
                parts = raw_text.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("{") and part.endswith("}"):
                        return part

            if raw_text.startswith("{") and raw_text.endswith("}"):
                return raw_text

            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                return match.group(0)
        except Exception as e:
            logger.debug(f"Error extracting JSON: {e}")
        return None
