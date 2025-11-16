import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from telegram.constants import ParseMode

from config import BOT_TOKEN, ADMIN_IDS, CHECK_INTERVAL_MINUTES
from database import Database
from event_parser import EventParser
from scheduler import ReminderScheduler

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize components
db = Database('sqlite:///events_bot.db')
event_parser = EventParser()
scheduler = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    # Create or update user in database
    db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    welcome_message = (
        "👋 Добро пожаловать в IT-events-BOT!\n\n"
        "Я помогу вам отслеживать события для предпринимателей и стартапов.\n\n"
        "📋 Доступные команды:\n"
        "/events - Список предстоящих событий\n"
        "/subscribe - Подписаться на рассылку\n"
        "/unsubscribe - Отписаться от рассылки\n"
        "/help - Помощь\n"
    )
    
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = (
        "📚 Помощь по использованию бота:\n\n"
        "🔹 /events - Просмотр всех доступных событий\n"
        "🔹 /subscribe - Подписаться на рассылку новых событий\n"
        "🔹 /unsubscribe - Отписаться от рассылки\n"
        "🔹 /my_events - Список событий, на которые вы зарегистрированы\n\n"
        "Для администраторов:\n"
        "🔹 /admin - Административная панель\n"
    )
    
    await update.message.reply_text(help_text)


async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /events command - list all upcoming events"""
    session = db.get_session()
    try:
        from database import Event
        events = session.query(Event).filter(
            Event.event_date > datetime.utcnow()
        ).order_by(Event.event_date).limit(10).all()
        
        if not events:
            await update.message.reply_text("📭 Пока нет предстоящих событий.")
            return
        
        message = "📅 Предстоящие события:\n\n"
        keyboard = []
        
        for event in events:
            date_str = event.event_date.strftime('%d.%m.%Y %H:%M')
            message += f"🎯 {event.title}\n"
            message += f"📅 {date_str}\n"
            if event.location:
                message += f"📍 {event.location}\n"
            message += "\n"
            
            keyboard.append([InlineKeyboardButton(
                f"📌 {event.title[:30]}...",
                callback_data=f"event_{event.id}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup)
    finally:
        session.close()


async def event_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle event button callbacks"""
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split('_')[1])
    session = db.get_session()
    try:
        from database import Event, EventRegistration, User
        event = session.query(Event).filter_by(id=event_id).first()
        
        if not event:
            await query.edit_message_text("Событие не найдено.")
            return
        
        user = db.get_or_create_user(
            telegram_id=query.from_user.id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        
        # Check if already registered
        existing = session.query(EventRegistration).filter_by(
            user_id=user.id,
            event_id=event_id
        ).first()
        
        date_str = event.event_date.strftime('%d.%m.%Y %H:%M')
        message = f"🎯 {event.title}\n\n"
        message += f"📅 Дата и время: {date_str}\n"
        
        if event.location:
            message += f"📍 Место: {event.location}\n"
        
        if event.description:
            message += f"\n📝 Описание:\n{event.description[:300]}...\n"
        
        if event.url:
            message += f"\n🔗 Подробнее: {event.url}\n"
        
        keyboard = []
        if not existing:
            keyboard.append([InlineKeyboardButton(
                "✅ Зарегистрироваться",
                callback_data=f"register_{event_id}"
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                "❌ Отменить регистрацию",
                callback_data=f"unregister_{event_id}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад к списку", callback_data="back_events")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup)
    finally:
        session.close()


async def register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle registration button"""
    query = update.callback_query
    await query.answer()
    
    event_id = int(query.data.split('_')[1])
    user = db.get_or_create_user(
        telegram_id=query.from_user.id,
        username=query.from_user.username,
        first_name=query.from_user.first_name,
        last_name=query.from_user.last_name
    )
    
    if db.register_for_event(user.id, event_id):
        await query.edit_message_text(
            "✅ Вы успешно зарегистрированы на событие!\n\n"
            "Вы получите напоминания за день и за час до начала события."
        )
    else:
        await query.edit_message_text("❌ Вы уже зарегистрированы на это событие.")


async def unregister_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unregistration button"""
    query = update.callback_query
    await query.answer()
    
    # TODO: Implement unregistration
    await query.edit_message_text("Функция отмены регистрации будет добавлена позже.")


async def back_events_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to events list button"""
    query = update.callback_query
    await query.answer()
    
    # Reuse the list_events logic
    session = db.get_session()
    try:
        from database import Event
        events = session.query(Event).filter(
            Event.event_date > datetime.utcnow()
        ).order_by(Event.event_date).limit(10).all()
        
        if not events:
            await query.edit_message_text("📭 Пока нет предстоящих событий.")
            return
        
        message = "📅 Предстоящие события:\n\n"
        keyboard = []
        
        for event in events:
            date_str = event.event_date.strftime('%d.%m.%Y %H:%M')
            message += f"🎯 {event.title}\n"
            message += f"📅 {date_str}\n"
            if event.location:
                message += f"📍 {event.location}\n"
            message += "\n"
            
            keyboard.append([InlineKeyboardButton(
                f"📌 {event.title[:30]}...",
                callback_data=f"event_{event.id}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup)
    finally:
        session.close()


async def my_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /my_events command"""
    user = db.get_or_create_user(
        telegram_id=update.effective_user.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name
    )
    
    session = db.get_session()
    try:
        from database import EventRegistration, Event
        registrations = session.query(EventRegistration).filter_by(
            user_id=user.id
        ).join(Event).filter(
            Event.event_date > datetime.utcnow()
        ).order_by(Event.event_date).all()
        
        if not registrations:
            await update.message.reply_text("📭 Вы не зарегистрированы ни на одно событие.")
            return
        
        message = "📋 Ваши события:\n\n"
        for reg in registrations:
            event = reg.event
            date_str = event.event_date.strftime('%d.%m.%Y %H:%M')
            message += f"🎯 {event.title}\n"
            message += f"📅 {date_str}\n\n"
        
        await update.message.reply_text(message)
    finally:
        session.close()


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /subscribe command"""
    db.get_or_create_user(
        telegram_id=update.effective_user.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name
    )
    db.update_user_subscription(update.effective_user.id, True)
    await update.message.reply_text("✅ Вы подписались на рассылку новых событий!")


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unsubscribe command"""
    db.get_or_create_user(
        telegram_id=update.effective_user.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name
    )
    db.update_user_subscription(update.effective_user.id, False)
    await update.message.reply_text("❌ Вы отписались от рассылки.")


# Admin commands
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    message = (
        "🔧 Административная панель\n\n"
        "Доступные команды:\n"
        "/add_resource - Добавить ресурс для мониторинга\n"
        "/list_resources - Список ресурсов\n"
        "/check_resources - Проверить ресурсы на новые события\n"
        "/broadcast - Отправить сообщение всем подписчикам\n"
    )
    
    await update.message.reply_text(message)


async def add_resource(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_resource command"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "Использование: /add_resource <название> <URL> <тип>\n"
            "Типы: channel, blog, website"
        )
        return
    
    name = context.args[0]
    url = context.args[1]
    resource_type = context.args[2]
    
    if resource_type not in ['channel', 'blog', 'website']:
        await update.message.reply_text("❌ Неверный тип ресурса. Используйте: channel, blog, website")
        return
    
    resource = db.add_resource(name, url, resource_type)
    await update.message.reply_text(f"✅ Ресурс '{name}' добавлен!")


async def list_resources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_resources command"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    resources = db.get_active_resources()
    
    if not resources:
        await update.message.reply_text("📭 Нет добавленных ресурсов.")
        return
    
    message = "📋 Список ресурсов:\n\n"
    for resource in resources:
        status = "✅" if resource.is_active else "❌"
        message += f"{status} {resource.name} ({resource.type})\n"
        message += f"   {resource.url}\n\n"
    
    await update.message.reply_text(message)


async def check_resources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /check_resources command - manually check for new events"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id) and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    await update.message.reply_text("🔍 Проверяю ресурсы на новые события...")
    
    new_events_count = await check_for_new_events(context.bot)
    
    await update.message.reply_text(f"✅ Проверка завершена. Найдено новых событий: {new_events_count}")


async def check_for_new_events(bot):
    """Check all resources for new events and send notifications"""
    resources = db.get_active_resources()
    new_events_count = 0
    
    for resource in resources:
        try:
            events = event_parser.parse_resource(resource.url, resource.type)
            
            for event_data in events:
                event = db.add_event(
                    resource_id=resource.id,
                    title=event_data['title'],
                    description=event_data.get('description', ''),
                    event_date=event_data['event_date'],
                    location=event_data.get('location'),
                    url=event_data.get('url')
                )
                
                if event:
                    new_events_count += 1
                    # Send notification to all subscribed users
                    await send_event_notification(bot, event)
        except Exception as e:
            logger.error(f"Error checking resource {resource.name}: {e}")
    
    return new_events_count


async def send_event_notification(bot, event):
    """Send event notification to all subscribed users"""
    users = db.get_subscribed_users()
    
    date_str = event.event_date.strftime('%d.%m.%Y %H:%M')
    message = (
        f"🎉 Новое событие!\n\n"
        f"🎯 {event.title}\n"
        f"📅 {date_str}\n"
    )
    
    if event.location:
        message += f"📍 {event.location}\n"
    
    if event.description:
        message += f"\n📝 {event.description[:200]}...\n"
    
    if event.url:
        message += f"\n🔗 Подробнее: {event.url}\n"
    
    keyboard = [[InlineKeyboardButton(
        "📌 Подробнее и регистрация",
        callback_data=f"event_{event.id}"
    )]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    for user in users:
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=message,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error sending notification to user {user.telegram_id}: {e}")
    
    db.mark_event_notified(event.id)


async def periodic_check(context: ContextTypes.DEFAULT_TYPE):
    """Periodically check for new events"""
    await check_for_new_events(context.bot)


def main():
    """Start the bot"""
    global scheduler
    
    # Initialize bot
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Initialize scheduler
    scheduler = ReminderScheduler(application.bot, db)
    scheduler.start()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("events", list_events))
    application.add_handler(CommandHandler("my_events", my_events))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe))
    
    # Admin handlers
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("add_resource", add_resource))
    application.add_handler(CommandHandler("list_resources", list_resources))
    application.add_handler(CommandHandler("check_resources", check_resources))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(event_callback, pattern="^event_"))
    application.add_handler(CallbackQueryHandler(register_callback, pattern="^register_"))
    application.add_handler(CallbackQueryHandler(unregister_callback, pattern="^unregister_"))
    application.add_handler(CallbackQueryHandler(back_events_callback, pattern="^back_events"))
    
    # Periodic event checking
    job_queue = application.job_queue
    job_queue.run_repeating(
        periodic_check,
        interval=CHECK_INTERVAL_MINUTES * 60,
        first=10
    )
    
    # Initialize admins from config
    for admin_id in ADMIN_IDS:
        db.add_admin(admin_id)
    
    # Start the bot
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

