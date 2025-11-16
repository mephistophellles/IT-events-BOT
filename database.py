from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

Base = declarative_base()


class Resource(Base):
    """Resources (channels/blogs) to monitor for events"""
    __tablename__ = 'resources'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    type = Column(String, nullable=False)  # 'channel', 'blog', 'website'
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    events = relationship("Event", back_populates="resource")


class Event(Base):
    """Detected events from resources"""
    __tablename__ = 'events'
    
    id = Column(Integer, primary_key=True)
    resource_id = Column(Integer, ForeignKey('resources.id'))
    title = Column(String, nullable=False)
    description = Column(Text)
    event_date = Column(DateTime, nullable=False)
    location = Column(String)
    url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    notified = Column(Boolean, default=False)
    
    resource = relationship("Resource", back_populates="events")
    registrations = relationship("EventRegistration", back_populates="event")


class User(Base):
    """Telegram users"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    is_subscribed = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    registrations = relationship("EventRegistration", back_populates="user")


class EventRegistration(Base):
    """Users registered for events"""
    __tablename__ = 'event_registrations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    event_id = Column(Integer, ForeignKey('events.id'))
    registered_at = Column(DateTime, default=datetime.utcnow)
    reminder_1day_sent = Column(Boolean, default=False)
    reminder_1hour_sent = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="registrations")
    event = relationship("Event", back_populates="registrations")


class Admin(Base):
    """Admin users"""
    __tablename__ = 'admins'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Database:
    def __init__(self, database_url):
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self):
        return self.Session()
    
    def add_admin(self, telegram_id):
        """Add an admin user"""
        session = self.get_session()
        try:
            admin = session.query(Admin).filter_by(telegram_id=telegram_id).first()
            if not admin:
                admin = Admin(telegram_id=telegram_id)
                session.add(admin)
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    def is_admin(self, telegram_id):
        """Check if user is admin"""
        session = self.get_session()
        try:
            admin = session.query(Admin).filter_by(telegram_id=telegram_id).first()
            return admin is not None
        finally:
            session.close()
    
    def get_or_create_user(self, telegram_id, username=None, first_name=None, last_name=None):
        """Get or create a user"""
        session = self.get_session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if not user:
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name
                )
                session.add(user)
                session.commit()
                session.refresh(user)
            else:
                # Update user info
                if username:
                    user.username = username
                if first_name:
                    user.first_name = first_name
                if last_name:
                    user.last_name = last_name
                session.commit()
                session.refresh(user)
            return user
        finally:
            session.close()
    
    def add_resource(self, name, url, resource_type):
        """Add a resource to monitor"""
        session = self.get_session()
        try:
            resource = Resource(name=name, url=url, type=resource_type)
            session.add(resource)
            session.commit()
            return resource
        finally:
            session.close()
    
    def get_active_resources(self):
        """Get all active resources"""
        session = self.get_session()
        try:
            return session.query(Resource).filter_by(is_active=True).all()
        finally:
            session.close()
    
    def add_event(self, resource_id, title, description, event_date, location=None, url=None):
        """Add a new event"""
        session = self.get_session()
        try:
            # Check if event already exists
            existing = session.query(Event).filter_by(
                resource_id=resource_id,
                title=title,
                event_date=event_date
            ).first()
            
            if existing:
                return None
            
            event = Event(
                resource_id=resource_id,
                title=title,
                description=description,
                event_date=event_date,
                location=location,
                url=url
            )
            session.add(event)
            session.commit()
            return event
        finally:
            session.close()
    
    def get_unnotified_events(self):
        """Get events that haven't been notified yet"""
        session = self.get_session()
        try:
            return session.query(Event).filter_by(notified=False).all()
        finally:
            session.close()
    
    def mark_event_notified(self, event_id):
        """Mark event as notified"""
        session = self.get_session()
        try:
            event = session.query(Event).filter_by(id=event_id).first()
            if event:
                event.notified = True
                session.commit()
        finally:
            session.close()
    
    def register_for_event(self, user_id, event_id):
        """Register a user for an event"""
        session = self.get_session()
        try:
            # Check if already registered
            existing = session.query(EventRegistration).filter_by(
                user_id=user_id,
                event_id=event_id
            ).first()
            
            if existing:
                return False
            
            registration = EventRegistration(user_id=user_id, event_id=event_id)
            session.add(registration)
            session.commit()
            return True
        finally:
            session.close()
    
    def get_event_registrations(self, event_id):
        """Get all registrations for an event"""
        session = self.get_session()
        try:
            return session.query(EventRegistration).filter_by(event_id=event_id).all()
        finally:
            session.close()
    
    def get_subscribed_users(self):
        """Get all subscribed users"""
        session = self.get_session()
        try:
            return session.query(User).filter_by(is_subscribed=True).all()
        finally:
            session.close()
    
    def get_registrations_for_reminder(self, hours_before=24):
        """Get registrations that need reminders"""
        session = self.get_session()
        from datetime import timedelta
        now = datetime.utcnow()
        target_time = now + timedelta(hours=hours_before)
        
        try:
            registrations = session.query(EventRegistration).join(Event).filter(
                Event.event_date <= target_time,
                Event.event_date > now
            ).all()
            
            result = []
            for reg in registrations:
                if hours_before == 24 and not reg.reminder_1day_sent:
                    result.append(reg)
                elif hours_before == 1 and not reg.reminder_1hour_sent:
                    result.append(reg)
            
            return result
        finally:
            session.close()
    
    def mark_reminder_sent(self, registration_id, reminder_type):
        """Mark reminder as sent"""
        session = self.get_session()
        try:
            reg = session.query(EventRegistration).filter_by(id=registration_id).first()
            if reg:
                if reminder_type == '1day':
                    reg.reminder_1day_sent = True
                elif reminder_type == '1hour':
                    reg.reminder_1hour_sent = True
                session.commit()
        finally:
            session.close()
    
    def update_user_subscription(self, telegram_id, is_subscribed):
        """Update user subscription status"""
        session = self.get_session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if user:
                user.is_subscribed = is_subscribed
                session.commit()
                return True
            return False
        finally:
            session.close()

