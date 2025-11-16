from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from database import Database
from telegram import Bot
from config import BOT_TOKEN, CHECK_INTERVAL_MINUTES
import asyncio


class ReminderScheduler:
    """Handle scheduled reminders for events"""
    
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler()
    
    def start(self):
        """Start the scheduler"""
        # Check for 1-day reminders every hour
        self.scheduler.add_job(
            self.send_1day_reminders,
            trigger=IntervalTrigger(hours=1),
            id='1day_reminders',
            replace_existing=True
        )
        
        # Check for 1-hour reminders every 15 minutes
        self.scheduler.add_job(
            self.send_1hour_reminders,
            trigger=IntervalTrigger(minutes=15),
            id='1hour_reminders',
            replace_existing=True
        )
        
        self.scheduler.start()
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
    
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
                print(f"Error sending 1-day reminder: {e}")
    
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
                print(f"Error sending 1-hour reminder: {e}")

