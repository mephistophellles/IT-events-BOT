import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///events_bot.db')

# Resource Monitoring Configuration
CHECK_INTERVAL_MINUTES = int(os.getenv('CHECK_INTERVAL_MINUTES', '60'))

# Event Detection Keywords
EVENT_KEYWORDS = [
    'meetup', 'event', 'conference', 'workshop', 'seminar',
    'hackathon', 'networking', 'startup', 'entrepreneurship',
    'pitch', 'demo day', 'webinar', 'training',
    'митап', 'конференция', 'воркшоп', 'семинар', 'стартап',
    'инвестор', 'питч', 'нетворкинг',
]

# Claude API Classifier (Anthropic)
USE_CLAUDE_CLASSIFIER = os.getenv('USE_CLAUDE_CLASSIFIER', 'false').lower() == 'true'
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
CLAUDE_MODEL = os.getenv('CLAUDE_MODEL', 'claude-3-5-haiku-20241022')

# Gemini API Classifier (Google)
USE_GEMINI_CLASSIFIER = os.getenv('USE_GEMINI_CLASSIFIER', 'true').lower() == 'true'
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')

# Classifier threshold (0.4 = liberal, 0.6 = balanced, 0.8 = strict)
CLASSIFIER_CONFIDENCE_THRESHOLD = float(os.getenv('CLASSIFIER_CONFIDENCE_THRESHOLD', '0.4'))
