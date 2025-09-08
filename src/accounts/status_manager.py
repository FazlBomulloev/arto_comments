import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from src.db import get_session
from src.db.models import Account
from src.cfg import config

logger = logging.getLogger(__name__)

class AccountStatusManager:
    """Менеджер для управления статусами аккаунтов"""
    
    # Константы для статусов
    STATUS_ACTIVE = "active"
    STATUS_PAUSE = "pause" 
    STATUS_BAN = "ban"
    
    # Константы для автовосстановления
    PAUSE_RECOVERY_HOURS = 1    # Восстановление из паузы через 1 час
    BAN_RECOVERY_HOURS = 72     # Восстановление из бана через 72 часа
    
    # Пороги для изменения статусов
    PAUSE_FAIL_THRESHOLD = 3    # Пауза после 3 неудач
    BAN_FAIL_THRESHOLD = 5      # Бан после 5 неудач
    
    # Типы ошибок для определения статуса
    PAUSE_ERRORS = [
        "FloodWaitError", "FloodWait", "Требуется ожидание",
        "ChatWriteForbiddenError", "Нет прав на комментирование",
        "ChatAdminRequiredError", "Требуются права администратора"
    ]
    
    BAN_ERRORS = [
        "AuthKeyError", "AuthKeyInvalidError", "Ошибка протокола",
        "SessionPasswordNeededError", "AccessTokenExpiredError",
        "UserDeactivatedError", "UserBannedInChannelError"
    ]

    @classmethod
    async def update_account_status(
        cls, 
        account_number: str, 
        success: bool, 
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Обновляет статус аккаунта на основе результата операции
        
        Args:
            account_number: Номер аккаунта
            success: Успешность операции
            error_message: Сообщение об ошибке (если есть)
            
        Returns:
            Словарь с информацией об изменениях
        """
        async with get_session() as session:
            try:
                account = await session.get(Account, account_number)
                if not account:
                    logger.warning(f"Аккаунт {account_number} не найден")
                    return {"status": "not_found"}
                
                old_status = account.status
                old_fail_count = account.fail
                
                if success:
                    # При успехе сбрасываем счетчик неудач
                    account.fail = 0
                    account.last_activity = datetime.now()
                    
                    # Если аккаунт был в паузе из-за временных проблем - восстанавливаем
                    if account.status == cls.STATUS_PAUSE:
                        account.status = cls.STATUS_ACTIVE
                        logger.info(f"✅ [{account_number}] Восстановлен из паузы после успешной операции")
                    
                else:
                    # При неудаче увеличиваем счетчик
                    account.fail += 1
                    account.last_activity = datetime.now()
                    
                    # Определяем новый статус на основе ошибки и количества неудач
                    new_status = cls._determine_status_by_error(
                        error_message, 
                        account.fail, 
                        account.status
                    )
                    
                    if new_status != account.status:
                        account.status = new_status
                        logger.warning(
                            f"⚠️ [{account_number}] Статус изменен: {old_status} -> {new_status} "
                            f"(неудач: {account.fail}, ошибка: {error_message})"
                        )
                
                await session.commit()
                
                return {
                    "status": "updated",
                    "account_number": account_number,
                    "old_status": old_status,
                    "new_status": account.status,
                    "old_fail_count": old_fail_count,
                    "new_fail_count": account.fail,
                    "success": success
                }
                
            except Exception as e:
                logger.error(f"❌ Ошибка обновления статуса аккаунта {account_number}: {e}")
                await session.rollback()
                return {"status": "error", "error": str(e)}

    @classmethod
    def _determine_status_by_error(
        cls, 
        error_message: Optional[str], 
        fail_count: int, 
        current_status: str
    ) -> str:
        """
        Определяет новый статус на основе ошибки и количества неудач
        """
        if not error_message:
            return current_status
            
        error_str = str(error_message)
        
        # Критические ошибки -> сразу в бан
        if any(ban_error in error_str for ban_error in cls.BAN_ERRORS):
            return cls.STATUS_BAN
            
        # Временные ошибки
        if any(pause_error in error_str for pause_error in cls.PAUSE_ERRORS):
            if fail_count >= cls.PAUSE_FAIL_THRESHOLD:
                return cls.STATUS_PAUSE
                
        # По количеству неудач
        if fail_count >= cls.BAN_FAIL_THRESHOLD:
            return cls.STATUS_BAN
        elif fail_count >= cls.PAUSE_FAIL_THRESHOLD:
            return cls.STATUS_PAUSE
            
        return current_status

    @classmethod
    async def get_active_accounts(cls, channel_id: int, limit: Optional[int] = None) -> List[Account]:
        """
        Получает только активные аккаунты для канала
        
        Args:
            channel_id: ID канала
            limit: Максимальное количество аккаунтов
            
        Returns:
            Список активных аккаунтов
        """
        async with get_session() as session:
            try:
                query = select(Account).where(
                    and_(
                        Account.channel_id == channel_id,
                        Account.status == cls.STATUS_ACTIVE
                    )
                ).order_by(Account.last_activity.asc())  # Берем менее активные первыми
                
                if limit:
                    query = query.limit(limit)
                    
                result = await session.execute(query)
                accounts = result.scalars().all()
                
                logger.info(f"📋 Найдено активных аккаунтов для канала {channel_id}: {len(accounts)}")
                return list(accounts)
                
            except Exception as e:
                logger.error(f"❌ Ошибка получения активных аккаунтов: {e}")
                return []

    @classmethod
    async def auto_recover_accounts(cls) -> Dict[str, int]:
        """
        Автоматически восстанавливает аккаунты из паузы и бана
        
        Returns:
            Статистика восстановления
        """
        async with get_session() as session:
            try:
                now = datetime.now()
                recovered_from_pause = 0
                recovered_from_ban = 0
                
                # Восстановление из паузы (через 1 час)
                pause_recovery_time = now - timedelta(hours=cls.PAUSE_RECOVERY_HOURS)
                paused_accounts = await session.execute(
                    select(Account).where(
                        and_(
                            Account.status == cls.STATUS_PAUSE,
                            Account.last_activity <= pause_recovery_time
                        )
                    )
                )
                
                for account in paused_accounts.scalars():
                    account.status = cls.STATUS_ACTIVE
                    account.fail = 0  # Сбрасываем счетчик неудач
                    recovered_from_pause += 1
                    logger.info(f"🔄 [{account.number}] Восстановлен из паузы")
                
                # Восстановление из бана (через 72 часа)
                ban_recovery_time = now - timedelta(hours=cls.BAN_RECOVERY_HOURS)
                banned_accounts = await session.execute(
                    select(Account).where(
                        and_(
                            Account.status == cls.STATUS_BAN,
                            Account.last_activity <= ban_recovery_time
                        )
                    )
                )
                
                for account in banned_accounts.scalars():
                    account.status = cls.STATUS_ACTIVE
                    account.fail = 0  # Сбрасываем счетчик неудач
                    recovered_from_ban += 1
                    logger.info(f"🔄 [{account.number}] Восстановлен из бана")
                
                await session.commit()
                
                total_recovered = recovered_from_pause + recovered_from_ban
                if total_recovered > 0:
                    logger.info(
                        f"✅ Автовосстановление завершено: {recovered_from_pause} из паузы, "
                        f"{recovered_from_ban} из бана (всего: {total_recovered})"
                    )
                
                return {
                    "recovered_from_pause": recovered_from_pause,
                    "recovered_from_ban": recovered_from_ban,
                    "total_recovered": total_recovered
                }
                
            except Exception as e:
                logger.error(f"❌ Ошибка автовосстановления аккаунтов: {e}")
                await session.rollback()
                return {"error": str(e)}

    @classmethod
    async def get_accounts_statistics(cls, channel_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Получает статистику по аккаунтам
        
        Args:
            channel_id: ID канала (если None - по всем каналам)
            
        Returns:
            Статистика по статусам
        """
        async with get_session() as session:
            try:
                base_query = select(Account)
                if channel_id:
                    base_query = base_query.where(Account.channel_id == channel_id)
                
                # Общее количество
                total_result = await session.execute(base_query)
                total_accounts = len(total_result.scalars().all())
                
                # По статусам
                active_result = await session.execute(
                    base_query.where(Account.status == cls.STATUS_ACTIVE)
                )
                active_count = len(active_result.scalars().all())
                
                pause_result = await session.execute(
                    base_query.where(Account.status == cls.STATUS_PAUSE)
                )
                pause_count = len(pause_result.scalars().all())
                
                ban_result = await session.execute(
                    base_query.where(Account.status == cls.STATUS_BAN)
                )
                ban_count = len(ban_result.scalars().all())
                
                # Аккаунты готовые к восстановлению
                now = datetime.now()
                pause_recovery_time = now - timedelta(hours=cls.PAUSE_RECOVERY_HOURS)
                ban_recovery_time = now - timedelta(hours=cls.BAN_RECOVERY_HOURS)
                
                ready_from_pause_result = await session.execute(
                    base_query.where(
                        and_(
                            Account.status == cls.STATUS_PAUSE,
                            Account.last_activity <= pause_recovery_time
                        )
                    )
                )
                ready_from_pause = len(ready_from_pause_result.scalars().all())
                
                ready_from_ban_result = await session.execute(
                    base_query.where(
                        and_(
                            Account.status == cls.STATUS_BAN,
                            Account.last_activity <= ban_recovery_time
                        )
                    )
                )
                ready_from_ban = len(ready_from_ban_result.scalars().all())
                
                return {
                    "channel_id": channel_id,
                    "total": total_accounts,
                    "active": active_count,
                    "pause": pause_count,
                    "ban": ban_count,
                    "ready_for_recovery": {
                        "from_pause": ready_from_pause,
                        "from_ban": ready_from_ban,
                        "total": ready_from_pause + ready_from_ban
                    },
                    "percentages": {
                        "active": round((active_count / total_accounts * 100) if total_accounts > 0 else 0, 1),
                        "pause": round((pause_count / total_accounts * 100) if total_accounts > 0 else 0, 1),
                        "ban": round((ban_count / total_accounts * 100) if total_accounts > 0 else 0, 1)
                    }
                }
                
            except Exception as e:
                logger.error(f"❌ Ошибка получения статистики аккаунтов: {e}")
                return {"error": str(e)}

    @classmethod
    async def force_recover_account(cls, account_number: str) -> Dict[str, Any]:
        """
        Принудительно восстанавливает аккаунт в активный статус
        
        Args:
            account_number: Номер аккаунта
            
        Returns:
            Результат операции
        """
        async with get_session() as session:
            try:
                account = await session.get(Account, account_number)
                if not account:
                    return {"status": "not_found", "message": f"Аккаунт {account_number} не найден"}
                
                old_status = account.status
                account.status = cls.STATUS_ACTIVE
                account.fail = 0
                account.last_activity = datetime.now()
                
                await session.commit()
                
                logger.info(f"🔧 [{account_number}] Принудительно восстановлен: {old_status} -> active")
                
                return {
                    "status": "success",
                    "account_number": account_number,
                    "old_status": old_status,
                    "new_status": cls.STATUS_ACTIVE,
                    "message": f"Аккаунт {account_number} восстановлен"
                }
                
            except Exception as e:
                logger.error(f"❌ Ошибка принудительного восстановления аккаунта {account_number}: {e}")
                await session.rollback()
                return {"status": "error", "error": str(e)}