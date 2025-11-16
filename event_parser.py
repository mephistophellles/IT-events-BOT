import requests
from bs4 import BeautifulSoup
import dateparser
import re
from datetime import datetime
from typing import List, Dict, Optional
from config import EVENT_KEYWORDS, CLASSIFIER_CONFIDENCE_THRESHOLD
from event_classifier import EventClassifier


class EventParser:
    """Parse events from various resource types"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.classifier = EventClassifier()
    
    def parse_resource(self, resource_url: str, resource_type: str) -> List[Dict]:
        """Parse events from a resource"""
        events = []
        
        try:
            if resource_type == 'channel':
                # For Telegram channels, we'd need to use Telegram API
                # This is a placeholder - actual implementation would use Telethon or similar
                pass
            elif resource_type in ['blog', 'website']:
                events = self._parse_website(resource_url)
        except Exception as e:
            print(f"Error parsing resource {resource_url}: {e}")
        
        return events
    
    def _parse_website(self, url: str) -> List[Dict]:
        """Parse events from a website/blog"""
        events = []
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Look for event-related content
            # This is a simplified parser - can be enhanced based on specific site structures
            text_content = soup.get_text().lower()
            
            # Check if page contains event keywords
            has_event_keywords = any(keyword in text_content for keyword in EVENT_KEYWORDS)
            
            if has_event_keywords:
                # Try to extract event information
                # Look for common patterns: dates, titles, descriptions
                event_data = self._extract_event_info(soup, url)
                if event_data:
                    # Classify event using neural network
                    is_relevant, confidence = self.classifier.is_relevant_event(
                        event_data['title'],
                        event_data.get('description', '')
                    )
                    
                    if is_relevant and confidence >= CLASSIFIER_CONFIDENCE_THRESHOLD:
                        events.append(event_data)
                    else:
                        print(f"Event filtered out: {event_data['title']} (confidence: {confidence:.2f})")
        except Exception as e:
            print(f"Error parsing website {url}: {e}")
        
        return events
    
    def _extract_event_info(self, soup: BeautifulSoup, source_url: str) -> Optional[Dict]:
        """Extract event information from parsed HTML"""
        # Try to find title
        title = None
        for tag in ['h1', 'h2', 'h3', 'title']:
            element = soup.find(tag)
            if element:
                title = element.get_text().strip()
                if any(keyword in title.lower() for keyword in EVENT_KEYWORDS):
                    break
        
        if not title:
            # Try meta tags
            meta_title = soup.find('meta', property='og:title')
            if meta_title:
                title = meta_title.get('content', '').strip()
        
        if not title:
            return None
        
        # Try to extract date
        event_date = self._extract_date(soup)
        if not event_date:
            return None
        
        # Extract description
        description = None
        for tag in ['p', 'div']:
            elements = soup.find_all(tag, limit=5)
            for elem in elements:
                text = elem.get_text().strip()
                if len(text) > 50 and any(keyword in text.lower() for keyword in EVENT_KEYWORDS):
                    description = text[:500]  # Limit description length
                    break
            if description:
                break
        
        # Extract location
        location = self._extract_location(soup)
        
        return {
            'title': title,
            'description': description or '',
            'event_date': event_date,
            'location': location,
            'url': source_url
        }
    
    def _extract_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract event date from HTML"""
        # Look for common date patterns
        text = soup.get_text()
        
        # Try to find dates in various formats
        date_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # DD/MM/YYYY or DD-MM-YYYY
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',   # YYYY/MM/DD
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}',
            r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}',
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                parsed_date = dateparser.parse(match)
                if parsed_date and parsed_date > datetime.now():
                    return parsed_date
        
        # Try to find in meta tags
        meta_date = soup.find('meta', property='event:start_time')
        if meta_date:
            date_str = meta_date.get('content', '')
            parsed_date = dateparser.parse(date_str)
            if parsed_date:
                return parsed_date
        
        return None
    
    def _extract_location(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract event location"""
        # Look for location patterns
        text = soup.get_text()
        
        # Common location indicators
        location_indicators = ['location:', 'venue:', 'address:', 'where:', 'at:']
        
        for indicator in location_indicators:
            pattern = f'{indicator}\\s*([^\\n]+)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Try meta tags
        meta_location = soup.find('meta', property='event:location')
        if meta_location:
            return meta_location.get('content', '').strip()
        
        return None
    
    def parse_telegram_channel(self, channel_username: str) -> List[Dict]:
        """Parse events from a Telegram channel
        Note: This requires Telegram API access (Telethon or similar)
        This is a placeholder - actual implementation would fetch channel posts
        """
        # TODO: Implement Telegram channel parsing using Telethon
        # For now, return empty list
        return []

