import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///events_bot.db')

# Resource Monitoring Configuration
CHECK_INTERVAL_MINUTES = int(os.getenv('CHECK_INTERVAL_MINUTES', '60'))  # Check resources every hour

# Event Detection Keywords
EVENT_KEYWORDS = [
    'meetup', 'event', 'conference', 'workshop', 'seminar', 
    'hackathon', 'networking', 'startup', 'entrepreneurship',
    'pitch', 'demo day', 'webinar', 'training'
]

# Neural Network Classifier Configuration
USE_OLLAMA_CLASSIFIER = os.getenv('USE_OLLAMA_CLASSIFIER', 'true').lower() == 'true'
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.2')  # or 'mistral', 'qwen2.5', etc.
CLASSIFIER_CONFIDENCE_THRESHOLD = float(os.getenv('CLASSIFIER_CONFIDENCE_THRESHOLD', '0.6'))

