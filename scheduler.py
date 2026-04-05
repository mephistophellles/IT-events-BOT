from datetime import datetime, timedelta
from database import Database
from telegram import Bot
import logging

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Handle scheduled reminders for events"""
    
    def __init__(self, bot: Bot, db: Database, job_queue):
        self.bot = bot
        self.db = db
        self.job_queue = job_queue
    
    def start(self):
        """Start the scheduler using job_queue"""
        # Check for 1-day reminders every hour
        self.job_queue.run_repeating(
            self._send_1day_reminders_wrapper,
            interval=3600,  # 1 hour in seconds
            first=60  # Start after 1 minute
        )
        
        # Check for 1-hour reminders every 15 minutes
        self.job_queue.run_repeating(
            self._send_1hour_reminders_wrapper,
            interval=900,  # 15 minutes in seconds
            first=60  # Start after 1 minute
        )
        
        logger.info("Reminder scheduler started")
    
    async def _send_1day_reminders_wrapper(self, context):
        """Wrapper for send_1day_reminders to work with job_queue"""
        await self.send_1day_reminders()
    
    async def _send_1hour_reminders_wrapper(self, context):
        """Wrapper for send_1hour_reminders to work with job_queue"""
        await self.send_1hour_reminders()
    
    def stop(self):
        """Stop the scheduler"""
        # Job queue will be stopped automatically when application stops
        pass
    
    async def send_1day_reminders(self):
        """Send reminders 1 day before events"""
        registrations = self.db.get_registrations_for_reminder(hours_before=24)
        
        for registration in registrations:
            try:
                event = registration.event
                user = registration.user
                
                message = (
                    f"📅 Напоминание о событии!\n\n"
                    f"🎯 {event.title}\n\n"
                    f"⏰ Событие состоится завтра в {event.event_date.strftime('%H:%M')}\n"
                )
                
                if event.location:
                    message += f"📍 Место: {event.location}\n"
                
                if event.url:
                    message += f"🔗 Подробнее: {event.url}\n"
                
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=message
                )
                
                self.db.mark_reminder_sent(registration.id, '1day')
            except Exception as e:
                logger.error(f"Error sending 1-day reminder: {e}")
    
    async def send_1hour_reminders(self):
        """Send reminders 1 hour before events"""
        registrations = self.db.get_registrations_for_reminder(hours_before=1)
        
        for registration in registrations:
            try:
                event = registration.event
                user = registration.user
                
                message = (
                    f"⏰ Напоминание: событие через час!\n\n"
                    f"🎯 {event.title}\n\n"
                    f"⏰ Начало в {event.event_date.strftime('%H:%M')}\n"
                )
                
                if event.location:
                    message += f"📍 Место: {event.location}\n"
                
                if event.url:
                    message += f"🔗 Подробнее: {event.url}\n"
                
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=message
                )
                
                self.db.mark_reminder_sent(registration.id, '1hour')
            except Exception as e:
                logger.error(f"Error sending 1-hour reminder: {e}")

