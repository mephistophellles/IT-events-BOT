import os
import logging
import requests
from typing import Dict, Optional, Tuple
from config import USE_OLLAMA_CLASSIFIER, OLLAMA_BASE_URL, OLLAMA_MODEL, CLASSIFIER_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)


class EventClassifier:
    """Neural network-based classifier to determine if an event is relevant for entrepreneurs/startups"""
    
    def __init__(self):
        self.use_ollama = USE_OLLAMA_CLASSIFIER
        self.ollama_base_url = OLLAMA_BASE_URL
        self.ollama_model = OLLAMA_MODEL
        self.confidence_threshold = CLASSIFIER_CONFIDENCE_THRESHOLD
        
        if self.use_ollama:
            # Test Ollama connection
            if self._test_ollama_connection():
                logger.info(f"Using Ollama ({self.ollama_model}) for event classification")
            else:
                logger.warning("Ollama connection failed, falling back to local model")
                self.use_ollama = False
        
        if not self.use_ollama:
            self._init_local_model()
    
    def _test_ollama_connection(self) -> bool:
        """Test if Ollama is available"""
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama connection test failed: {e}")
            return False
    
    def _init_local_model(self):
        """Initialize local transformer model for classification"""
        try:
            from transformers import pipeline
            import torch
            
            # Use zero-shot classification - works with multiple languages including Russian
            # BART-large-mnli is multilingual and can handle Russian text
            try:
                self.classifier = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-large-mnli",
                    device=0 if torch.cuda.is_available() else -1
                )
                logger.info("Using BART zero-shot classifier for event classification")
            except Exception as e:
                logger.warning(f"Could not load BART model: {e}, using keyword-based fallback")
                self.classifier = None
                
        except ImportError:
            logger.warning("Transformers library not found, using keyword-based classification")
            self.classifier = None
        except Exception as e:
            logger.error(f"Error initializing local model: {e}")
            self.classifier = None
    
    def is_relevant_event(self, title: str, description: str = "") -> Tuple[bool, float]:
        """
        Determine if an event is relevant for entrepreneurs/startups
        
        Returns:
            (is_relevant, confidence_score)
        """
        if not title:
            return False, 0.0
        
        # Combine title and description for analysis
        text = f"{title}. {description}"[:1000]  # Limit text length
        
        if self.use_ollama:
            return self._classify_with_ollama(text)
        elif self.classifier:
            return self._classify_with_local_model(text)
        else:
            # Fallback to keyword-based classification
            return self._classify_with_keywords(text)
    
    def _classify_with_ollama(self, text: str) -> Tuple[bool, float]:
        """Classify event using Ollama"""
        try:
            prompt = """Определи, относится ли это событие к предпринимательству, стартапам, бизнесу или технологиям для бизнеса.

Событие релевантно, если оно связано с:
- Стартапами и предпринимательством
- Бизнес-конференциями и митапами для бизнеса
- Технологиями для бизнеса (SaaS, B2B)
- Инвестициями и венчурным капиталом
- Бизнес-акселераторами и инкубаторами
- Питчами стартапов
- Нетворкингом для предпринимателей

Событие НЕ релевантно, если оно связано с:
- Дизайном (UI/UX, графический дизайн) без бизнес-контекста
- Искусством и творчеством
- Личными хобби
- Событиями для других профессиональных групп (врачи, учителя и т.д.)

Текст события:
{}

Ответь только "ДА" или "НЕТ", затем через пробел укажи уверенность от 0.0 до 1.0.""".format(text)
            
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 50
                    }
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Ollama API error: {response.status_code}")
                return self._classify_with_keywords(text)
            
            result_data = response.json()
            result = result_data.get('response', '').strip().upper()
            
            if result.startswith("ДА"):
                confidence = 0.9
                try:
                    # Try to extract confidence from response
                    parts = result.split()
                    if len(parts) > 1:
                        confidence = float(parts[-1])
                except:
                    pass
                return True, confidence
            else:
                confidence = 0.1
                try:
                    parts = result.split()
                    if len(parts) > 1:
                        confidence = float(parts[-1])
                except:
                    pass
                return False, confidence
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to Ollama: {e}")
            return self._classify_with_keywords(text)
        except Exception as e:
            logger.error(f"Error classifying with Ollama: {e}")
            return self._classify_with_keywords(text)
    
    def _classify_with_local_model(self, text: str) -> Tuple[bool, float]:
        """Classify event using local transformer model"""
        try:
            # Zero-shot classification labels
            candidate_labels = [
                "событие для предпринимателей и стартапов",
                "бизнес-конференция или митап",
                "событие для дизайнеров",
                "событие для других профессий",
                "общее мероприятие"
            ]
            
            result = self.classifier(text, candidate_labels)
            
            # Get the most likely label and its score
            top_label = result['labels'][0]
            top_score = result['scores'][0]
            
            # Check if it's relevant (first two labels are relevant)
            is_relevant = top_label in candidate_labels[:2]
            
            # Adjust confidence based on score
            confidence = top_score if is_relevant else (1.0 - top_score)
            
            return is_relevant, confidence
            
        except Exception as e:
            logger.error(f"Error classifying with local model: {e}")
            return self._classify_with_keywords(text)
    
    def _classify_with_keywords(self, text: str) -> Tuple[bool, float]:
        """Fallback keyword-based classification"""
        text_lower = text.lower()
        
        # Positive keywords (entrepreneurship/startup related)
        positive_keywords = [
            'стартап', 'startup', 'предприниматель', 'entrepreneur', 'бизнес', 'business',
            'инвестиции', 'investment', 'венчур', 'venture', 'акселератор', 'accelerator',
            'инкубатор', 'incubator', 'питч', 'pitch', 'демо-день', 'demo day',
            'нетворкинг', 'networking', 'saas', 'b2b', 'технологии для бизнеса',
            'бизнес-конференция', 'бизнес-митап', 'entrepreneurship'
        ]
        
        # Negative keywords (not relevant)
        negative_keywords = [
            'дизайн', 'design', 'ui/ux', 'графический дизайн', 'иллюстрация',
            'фотография', 'photography', 'искусство', 'art', 'творчество',
            'хобби', 'hobby', 'личное развитие', 'йога', 'медитация'
        ]
        
        # Count matches
        positive_count = sum(1 for keyword in positive_keywords if keyword in text_lower)
        negative_count = sum(1 for keyword in negative_keywords if keyword in text_lower)
        
        # Calculate confidence
        total_keywords = positive_count + negative_count
        if total_keywords == 0:
            return False, 0.3  # Low confidence if no keywords found
        
        confidence = positive_count / total_keywords if total_keywords > 0 else 0.5
        is_relevant = positive_count > negative_count and positive_count > 0
        
        return is_relevant, confidence

