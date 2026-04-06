import requests
from bs4 import BeautifulSoup
import dateparser
import re
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Iterable
from urllib.parse import urljoin, quote_plus
from config import EVENT_KEYWORDS, CLASSIFIER_CONFIDENCE_THRESHOLD
from event_classifier import EventClassifier

logger = logging.getLogger(__name__)

HTML_EVENT_CLASS_HINTS = [
    'event', 'events', 'meetup', 'conference', 'webinar', 'seminar',
    'workshop', 'hackathon', 'startup', 'entrepreneur', 'pitch', 'networking'
]


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
                events = self._parse_telegram_channel(resource_url)
            elif resource_type in ['blog', 'website']:
                events = self._parse_website(resource_url)
            else:
                logger.warning(f"Unknown resource type: {resource_type}")
        except Exception as e:
            logger.error(f"Error parsing resource {resource_url}: {e}", exc_info=True)
        
        return events
    
    def _parse_website(self, url: str) -> List[Dict]:
        """Parse events from a website/blog"""
        events = []
        
        try:
            logger.info(f"Parsing website: {url}")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Extract events from JSON-LD and HTML tags
            # Both methods will add events directly via _evaluate_candidate
            self._extract_events_from_json_ld(soup, url, events)
            self._extract_events_from_tags(soup, url, events)
        except Exception as e:
            logger.error(f"Error parsing website {url}: {e}", exc_info=True)
        
        logger.info(f"Found {len(events)} events from {url}")
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
        text = soup.get_text()
        date = self._extract_date_from_text(text)
        if date:
            return date
        
        # Fallback to meta tags
        meta_date = soup.find('meta', property='event:start_time')
        if meta_date:
            date_str = meta_date.get('content', '')
            parsed_date = dateparser.parse(date_str, languages=['ru', 'en'])
            if parsed_date and parsed_date > datetime.now():
                return parsed_date
        
        return None
    
    def _extract_date_from_text(self, text: str) -> Optional[datetime]:
        """Extract event date from text snippet"""
        RU_MONTHS = r'(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)'
        EN_MONTHS = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*'
        TIME_OPT = r'(?:\s+\d{1,2}:\d{2})?'

        date_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',                          # DD/MM/YYYY
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',                            # YYYY/MM/DD
            rf'{EN_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}',                   # Jan 8, 2026
            rf'\d{{1,2}}\s+{EN_MONTHS}\s+\d{{4}}',                     # 8 Jan 2026
            rf'\d{{1,2}}\s+{RU_MONTHS}\s+\d{{4}}{TIME_OPT}',           # 8 апреля 2026 10:00
            rf'{RU_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}',                   # апреля 8, 2026
            rf'\d{{1,2}}[-–]\d{{1,2}}\s+{RU_MONTHS}{TIME_OPT}',        # 8-9 апреля
            rf'\d{{1,2}}\s+{RU_MONTHS}{TIME_OPT}',                     # 8 апреля 10:00 (no year)
            rf'\d{{1,2}}\s+{EN_MONTHS}{TIME_OPT}',                     # 8 April 10:00 (no year)
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                parsed_date = dateparser.parse(
                    match,
                    languages=['ru', 'en'],
                    settings={'PREFER_DAY_OF_MONTH': 'first', 'PREFER_DATES_FROM': 'future'},
                )
                if parsed_date and parsed_date > datetime.now():
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
        """Backward compatibility wrapper."""
        return self._parse_telegram_channel(channel_username)
    
    def _extract_events_from_json_ld(self, soup: BeautifulSoup, source_url: str, events: List[Dict]):
        """Extract events from JSON-LD structured data and add them via _evaluate_candidate"""
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                for item in self._iter_json_ld(data):
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get('@type')
                    if isinstance(item_type, list):
                        is_event = any('event' in str(t).lower() for t in item_type)
                    else:
                        is_event = item_type and 'event' in str(item_type).lower()
                    
                    if not is_event:
                        continue
                    
                    title = item.get('name') or item.get('headline')
                    description = item.get('description') or ''
                    start_date = item.get('startDate')
                    location = ''
                    location_data = item.get('location')
                    if isinstance(location_data, dict):
                        location = location_data.get('name') or location_data.get('address', '')
                    
                    event_date = None
                    if start_date:
                        event_date = dateparser.parse(start_date, languages=['ru', 'en'])
                    
                    if title and event_date:
                        candidate_url = item.get('url') or source_url
                        # Handle relative URLs
                        if candidate_url and not candidate_url.startswith('http'):
                            candidate_url = urljoin(source_url, candidate_url)

                        candidate = {
                            'title': title.strip(),
                            'description': description.strip()[:500],
                            'event_date': event_date,
                            'location': location.strip(),
                            'url': candidate_url
                        }
                        self._evaluate_candidate(candidate, events)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                logger.debug(f"Error parsing JSON-LD on {source_url}: {e}")
    
    def _iter_json_ld(self, data: Any) -> Iterable[Any]:
        if isinstance(data, list):
            for item in data:
                yield from self._iter_json_ld(item)
        elif isinstance(data, dict):
            yield data
            for value in data.values():
                yield from self._iter_json_ld(value)
    
    def _extract_events_from_tags(self, soup: BeautifulSoup, source_url: str, events: List[Dict]):
        """Extract events from HTML tags and add them via _evaluate_candidate"""
        selectors = ['article', 'section', 'div', 'li']
        for selector in selectors:
            for element in soup.select(selector):
                classes = ' '.join(element.get('class', [])).lower()
                if any(hint in classes for hint in HTML_EVENT_CLASS_HINTS):
                    candidate = self._extract_event_from_element(element, source_url)
                    if candidate:
                        self._evaluate_candidate(candidate, events)
    
    def _extract_event_from_element(self, element, source_url: str) -> Optional[Dict]:
        title = None
        title_elem = None
        for tag in ['h1', 'h2', 'h3', 'a']:
            elem = element.find(tag)
            if elem and elem.get_text().strip():
                title = elem.get_text().strip()
                title_elem = elem
                break

        if not title:
            return None

        description = ''
        paragraphs = element.find_all('p')
        if paragraphs:
            # Extract only the first valid paragraph (not empty, not too short)
            for p in paragraphs:
                text = p.get_text().strip()
                if text and len(text) > 10:
                    description = text[:500]
                    break
        else:
            description = element.get_text().strip()[:500]

        date_text = element.get_text(separator=' ')
        event_date = self._extract_date_from_text(date_text)
        if not event_date:
            return None

        location = None
        location_elem = element.find(string=re.compile(r'(?:Место|Location|Venue)', re.IGNORECASE))
        if location_elem:
            location = location_elem.parent.get_text().split(':', 1)[-1].strip()

        # Try to find direct link to event
        url = source_url

        # First, look for link within the element
        link = element.find('a', href=True)
        if link and link['href']:
            href = link['href']
            if href.startswith('http'):
                url = href
            elif href.startswith('/'):
                # Relative URL - construct full URL
                from urllib.parse import urljoin
                url = urljoin(source_url, href)
            elif href.startswith('#'):
                # Anchor link - append to source URL
                url = source_url + href

        # For it-event-hub.ru, try to generate a search/filter URL
        if 'it-event-hub.ru' in source_url and url == source_url:
            # Escape title for URL
            encoded_title = quote_plus(title[:30])
            url = f"{source_url}?search={encoded_title}"

        # For leader-id.ru, generate anchor URL
        if 'leader-id.ru' in source_url and url == source_url:
            slug = title.lower().replace(' ', '-')[:50]
            url = f"https://leader-id.ru/#{slug}"

        return {
            'title': title,
            'description': description,
            'event_date': event_date,
            'location': location,
            'url': url
        }
    
    def _is_upcoming_event(self, event_date: datetime) -> bool:
        """Check if event date is in the future within a 90-day window"""
        now = datetime.now()
        return now <= event_date <= now + timedelta(days=90)
    
    def _evaluate_candidate(self, candidate: Dict, events: List[Dict]):
        if not candidate.get('title') or not candidate.get('event_date'):
            return
        
        event_date = candidate['event_date']
        
        # Check if event is upcoming (within 90 days)
        if not self._is_upcoming_event(event_date):
            logger.debug(
                f"Event '{candidate['title']}' rejected: "
                f"date {event_date.strftime('%Y-%m-%d')} is not within 90-day window"
            )
            return
        
        is_relevant, confidence = self.classifier.is_relevant_event(
            candidate['title'],
            candidate.get('description', '')
        )
        
        logger.info(
            f"Classification result for '{candidate['title']}': "
            f"relevant={is_relevant}, confidence={confidence:.2f}, "
            f"threshold={CLASSIFIER_CONFIDENCE_THRESHOLD}, "
            f"date={event_date.strftime('%Y-%m-%d')}"
        )
        
        if is_relevant and confidence >= CLASSIFIER_CONFIDENCE_THRESHOLD:
            events.append(candidate)
            logger.info(f"Event accepted: {candidate['title']} on {event_date.strftime('%Y-%m-%d')}")
        else:
            logger.debug(f"Event rejected: {candidate['title']} (classification failed)")
    
    def _parse_telegram_channel(self, channel_url: str) -> List[Dict]:
        """Parse Telegram channel via public web view using keywords."""
        logger.info(f"Parsing Telegram channel: {channel_url}")
        events = []
        
        if channel_url.startswith('https://t.me/') or channel_url.startswith('http://t.me/'):
            fetch_url = channel_url if '/s/' in channel_url else channel_url.replace('t.me', 't.me/s', 1)
        else:
            fetch_url = f"https://t.me/s/{channel_url.lstrip('@')}"
        
        try:
            response = self.session.get(fetch_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'lxml')
            
            messages = soup.select('.tgme_widget_message')
            logger.debug(f"Found {len(messages)} messages on channel page")
            
            for msg in messages:
                text = msg.get_text(separator=' ').strip()
                text_lower = text.lower()
                
                if not any(keyword in text_lower for keyword in EVENT_KEYWORDS):
                    continue
                
                event_date = self._extract_date_from_text(text)
                if not event_date:
                    continue
                
                title = text.split('\n')[0][:120]
                link_elem = msg.select_one('a.tgme_widget_message_date')
                url = link_elem['href'] if link_elem and link_elem.has_attr('href') else fetch_url
                
                candidate = {
                    'title': title,
                    'description': text[:500],
                    'event_date': event_date,
                    'location': None,
                    'url': url
                }
                
                self._evaluate_candidate(candidate, events)
        except Exception as e:
            logger.error(f"Error parsing Telegram channel {channel_url}: {e}", exc_info=True)
        
        logger.info(f"Found {len(events)} events from Telegram channel {channel_url}")
        return events

