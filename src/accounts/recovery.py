# src/accounts/recovery.py
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import select, and_
from src.db import get_session
from src.db.models import Account
from src.accounts.session import is_account_valid

logger = logging.getLogger(__name__)

class AccountRecoveryManager:
    """Менеджер для восстановления статуса аккаунтов"""
    
    # Константы времени
    PAUSE_CHECK_INTERVAL = timedelta(hours=3)  # Проверка аккаунтов на паузе каждые 3 часа
    BAN_CHECK_INTERVAL = timedelta(days=3)     # Проверка забаненных аккаунтов каждые 3 дня
    MAX_FAILS_FOR_PAUSE = 3                   # Максимум ошибок для паузы
    MAX_FAILS_FOR_BAN = 3                     # Максимум критических ошибок для бана
    
    @classmethod
    async def handle_account_error(cls, account_number: str, error_type: str, error_message: str):
        """
        Обрабатывает ошибку аккаунта и обновляет его статус
        
        Args:
            account_number: Номер аккаунта
            error_type: Тип ошибки ('critical', 'flood_wait', 'normal')
            error_message: Сообщение об ошибке
        """
        async with get_session() as session:
            account = await session.get(Account, account_number)
            if not account:
                logger.error(f"Аккаунт {account_number} не найден в БД")
                return
            
            now = datetime.now()
            account.last_error = error_message
            account.last_error_time = now
            account.total_fails += 1
            
            # Определяем действие на основе типа ошибки
            if error_type == 'critical':
                # Критические ошибки: AuthKeyError, ApiIdInvalidError и т.д.
                account.fail += 1
                if account.fail >= cls.MAX_FAILS_FOR_BAN:
                    account.status = 'ban'
                    account.pause_reason = 'critical_error'
                    account.next_check_time = now + cls.BAN_CHECK_INTERVAL
                    logger.warning(f"Аккаунт {account_number} отправлен в БАН после {account.fail} критических ошибок")
                else:
                    account.status = 'pause'
                    account.pause_reason = 'critical_error'
                    account.next_check_time = now + cls.PAUSE_CHECK_INTERVAL
                    logger.warning(f"Аккаунт {account_number} отправлен на ПАУЗУ после критической ошибки ({account.fail}/{cls.MAX_FAILS_FOR_BAN})")
                    
            elif error_type == 'flood_wait':
                # FloodWait - сразу на паузу
                account.status = 'pause'
                account.pause_reason = 'flood_wait'
                account.next_check_time = now + cls.PAUSE_CHECK_INTERVAL
                logger.warning(f"Аккаунт {account_number} отправлен на ПАУЗУ из-за FloodWait")
                
            elif error_type == 'normal':
                # Обычные ошибки
                account.fail += 1
                if account.fail >= cls.MAX_FAILS_FOR_PAUSE:
                    account.status = 'pause'
                    account.pause_reason = 'error'
                    account.next_check_time = now + cls.PAUSE_CHECK_INTERVAL
                    logger.warning(f"Аккаунт {account_number} отправлен на ПАУЗУ после {account.fail} ошибок")
            
            await session.commit()
    
    @classmethod
    async def get_accounts_for_recovery(cls) -> List[Account]:
        """Получает список аккаунтов для проверки восстановления"""
        now = datetime.now()
        
        async with get_session() as session:
            # Получаем аккаунты на паузе или в бане, у которых пришло время проверки
            result = await session.execute(
                select(Account).where(
                    and_(
                        Account.status.in_(['pause', 'ban']),
                        Account.next_check_time <= now
                    )
                )
            )
            return result.scalars().all()
    
    @classmethod
    async def attempt_recovery(cls, account: Account) -> bool:
        """
        Пытается восстановить аккаунт
        
        Returns:
            bool: True если аккаунт восстановлен, False если нет
        """
        logger.info(f"Проверяем возможность восстановления аккаунта {account.number}")
        
        # Проверяем валидность аккаунта
        try:
            is_valid = await is_account_valid(account.session, account.number)
            
            if is_valid:
                # Аккаунт рабочий - восстанавливаем
                async with get_session() as session:
                    # Получаем свежую версию из БД
                    fresh_account = await session.get(Account, account.number)
                    if fresh_account:
                        fresh_account.status = 'active'
                        fresh_account.fail = 0  # Сбрасываем счетчик ошибок
                        fresh_account.pause_reason = None
                        fresh_account.next_check_time = None
                        fresh_account.last_error = None
                        await session.commit()
                        
                        logger.info(f"✅ Аккаунт {account.number} успешно восстановлен!")
                        return True
            else:
                # Аккаунт все еще не работает - планируем следующую проверку
                await cls._schedule_next_check(account)
                logger.warning(f"⚠️ Аккаунт {account.number} все еще не готов к восстановлению")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке аккаунта {account.number}: {e}")
            # При ошибке проверки планируем следующую проверку
            await cls._schedule_next_check(account)
            return False
    
    @classmethod
    async def _schedule_next_check(cls, account: Account):
        """Планирует следующую проверку аккаунта"""
        now = datetime.now()
        
        async with get_session() as session:
            fresh_account = await session.get(Account, account.number)
            if fresh_account:
                if fresh_account.status == 'ban':
                    fresh_account.next_check_time = now + cls.BAN_CHECK_INTERVAL
                else:  # pause
                    fresh_account.next_check_time = now + cls.PAUSE_CHECK_INTERVAL
                
                await session.commit()
                logger.info(f"📅 Следующая проверка аккаунта {account.number}: {fresh_account.next_check_time}")
    
    @classmethod
    async def run_recovery_cycle(cls):
        """Запускает один цикл восстановления аккаунтов"""
        logger.info("🔄 Запуск цикла восстановления аккаунтов")
        
        accounts_to_check = await cls.get_accounts_for_recovery()
        logger.info(f"📋 Найдено аккаунтов для проверки: {len(accounts_to_check)}")
        
        if not accounts_to_check:
            return
        
        recovered_count = 0
        for account in accounts_to_check:
            try:
                if await cls.attempt_recovery(account):
                    recovered_count += 1
                    
                # Небольшая пауза между проверками
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Ошибка при восстановлении аккаунта {account.number}: {e}")
        
        logger.info(f"✅ Цикл восстановления завершен. Восстановлено: {recovered_count}/{len(accounts_to_check)}")

# Фоновая задача для автоматического восстановления
async def account_recovery_background_task():
    """Фоновая задача для периодического восстановления аккаунтов"""
    logger.info("🚀 Запущена фоновая задача восстановления аккаунтов")
    
    while True:
        try:
            await AccountRecoveryManager.run_recovery_cycle()
            
            # Ждем 30 минут перед следующим циклом
            await asyncio.sleep(1800)  # 30 минут
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в задаче восстановления: {e}")
            # При ошибке ждем 5 минут и продолжаем
            await asyncio.sleep(300)