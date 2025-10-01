from src.db.base import Base
from sqlalchemy import Column, Integer, String, DateTime, func, BigInteger,ForeignKey, Text, Boolean, Float
from sqlalchemy.orm import relationship

class AIAgent(Base):
    """Модель для хранения данных AI агентов"""
    __tablename__ = 'ai_agent'

    agent_id = Column(Integer, primary_key=True, autoincrement=True)
    api_id = Column(String(255), nullable=False)  # Добавлено поле для API ID
    description = Column(String(255), nullable=True)
    channel_id = Column(Integer)
    status = Column(Boolean, default=True)  # Активен/неактивен


class Channel(Base):
    """Модель для хранения каналов"""
    __tablename__ = 'channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # @channelname (username канала)
    discussion_group_invite = Column(String(255), nullable=False)  # https://t.me/+xxxxx (инвайт на группу)
    discussion_group_id = Column(BigInteger, nullable=True)  # ID группы (определяется автоматически)
    
    acc_male_name_list = Column(Text)
    acc_female_name_list = Column(Text)
    acc_male_photo_list = Column(Text)
    acc_female_photo_list = Column(Text)
    
    # Параметры комментирования
    comments_chance = Column(Integer, default=30)  # Шанс в %
    comments_number = Column(Integer, default=10)  # Базовое число
    comments_number_range = Column(Integer, default=10)  # Разброс
    
    # Новые параметры для рандома публикаций
    post_selection_chance = Column(Integer, default=50)  # Шанс выбора поста для комментирования
    post_min_interval = Column(Integer, default=30)  # Минимальный интервал между постами (минуты)
    post_max_interval = Column(Integer, default=120)  # Максимальный интервал между постами (минуты)
    
    # Параметры лайков
    likes_on_posts_chance = Column(Integer, default=20)  # Шанс лайка на пост
    likes_on_comments_chance = Column(Integer, default=15)  # Шанс лайка на комментарий
    likes_reaction_types = Column(String(255), default="❤️,👍,🔥")  # Типы реакций через запятую

class Account(Base):
    """Модель для хранения аккаунтов"""
    __tablename__ = 'accounts'

    # Основные поля
    number = Column(String(20), primary_key=True)  # Номер телефона как PK
    session = Column(Text, nullable=False)  # Сессия в формате строки/JSON
    channel_id = Column(Integer, ForeignKey('channels.id'))
    fail = Column(Integer, default=0)  # Счетчик неудачных попыток
    status = Column(String(10), default='active')  # active, pause, ban
    joined_group = Column(Boolean, default=False)  # Вступил ли в группу обсуждений
    
    # Новые поля для статистики
    comments_sent = Column(Integer, default=0)  # Количество отправленных комментариев
    likes_given = Column(Integer, default=0)  # Количество поставленных лайков
    last_activity = Column(DateTime, default=func.now())  # Последняя активность
    
    # НОВЫЕ ПОЛЯ для системы восстановления статуса
    last_error = Column(Text)  # Последняя ошибка
    last_error_time = Column(DateTime)  # Время последней ошибки
    next_check_time = Column(DateTime)  # Время следующей проверки для восстановления
    total_fails = Column(Integer, default=0)  # Общий счетчик ошибок
    pause_reason = Column(String(50))  # Причина паузы: 'flood_wait', 'error', 'ban'

class CommentActivity(Base):
    """Модель для отслеживания комментариев для лайков"""
    __tablename__ = 'comment_activity'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_name = Column(String(100), nullable=False)
    post_id = Column(BigInteger, nullable=False)
    comment_id = Column(BigInteger, nullable=False)
    account_number = Column(String(20), ForeignKey('accounts.number'))
    created_at = Column(DateTime, default=func.now())
    likes_received = Column(Integer, default=0)  # Количество лайков на комментарий

class PostActivity(Base):
    """Модель для отслеживания активности по постам"""
    __tablename__ = 'post_activity'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_name = Column(String(100), nullable=False)
    post_id = Column(BigInteger, nullable=False)
    last_comment_time = Column(DateTime, default=func.now())  # Время последнего комментария
    total_comments = Column(Integer, default=0)  # Общее количество комментариев
    total_likes = Column(Integer, default=0)  # Общее количество лайков