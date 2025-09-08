import asyncio
import logging
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .status_manager import AccountStatusManager

logger = logging.getLogger(__name__)

class AccountRecoveryScheduler:
    """Планировщик для автоматического восстановления аккаунтов"""
    
    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.is_running = False
        
    async def start(self):
        """Запускает планировщик"""
        if self.is_running:
            logger.warning("Планировщик восстановления уже запущен")
            return
            
        try:
            self.scheduler = AsyncIOScheduler()
            
            # Добавляем задачу автовосстановления каждые 30 минут
            self.scheduler.add_job(
                self._recovery_job,
                trigger=IntervalTrigger(minutes=30),
                id="account_recovery",
                name="Автовосстановление аккаунтов",
                max_instances=1,  # Только одна инстанция задачи
                coalesce=True,    # Объединять пропущенные запуски
                misfire_grace_time=300  # 5 минут на выполнение пропущенной задачи
            )
            
            # Добавляем задачу статистики каждые 2 часа
            self.scheduler.add_job(
                self._statistics_job,
                trigger=IntervalTrigger(hours=2),
                id="account_statistics",
                name="Статистика аккаунтов",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=600  # 10 минут на выполнение
            )
            
            self.scheduler.start()
            self.is_running = True
            
            logger.info("✅ Планировщик восстановления аккаунтов запущен")
            logger.info("📅 Автовосстановление: каждые 30 минут")
            logger.info("📊 Статистика: каждые 2 часа")
            
            # Запускаем первое восстановление сразу
            await self._recovery_job()
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска планировщика восстановления: {e}")
            raise
    
    async def stop(self):
        """Останавливает планировщик"""
        if not self.is_running or not self.scheduler:
            return
            
        try:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("⏹️ Планировщик восстановления аккаунтов остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки планировщика: {e}")
    
    async def _recovery_job(self):
        """Задача автовосстановления аккаунтов"""
        try:
            logger.info("🔄 Запуск автовосстановления аккаунтов...")
            
            start_time = datetime.now()
            result = await AccountStatusManager.auto_recover_accounts()
            end_time = datetime.now()
            
            duration = (end_time - start_time).total_seconds()
            
            if "error" in result:
                logger.error(f"❌ Ошибка автовосстановления: {result['error']}")
            else:
                total_recovered = result.get("total_recovered", 0)
                if total_recovered > 0:
                    logger.info(
                        f"✅ Автовосстановление завершено за {duration:.2f}с: "
                        f"восстановлено {total_recovered} аккаунтов "
                        f"({result.get('recovered_from_pause', 0)} из паузы, "
                        f"{result.get('recovered_from_ban', 0)} из бана)"
                    )
                else:
                    logger.debug(f"ℹ️ Автовосстановление завершено за {duration:.2f}с: восстановлений не требуется")
                    
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в задаче автовосстановления: {e}")
    
    async def _statistics_job(self):
        """Задача сбора статистики по аккаунтам"""
        try:
            logger.info("📊 Сбор статистики аккаунтов...")
            
            # Получаем общую статистику
            stats = await AccountStatusManager.get_accounts_statistics()
            
            if "error" in stats:
                logger.error(f"❌ Ошибка получения статистики: {stats['error']}")
                return
            
            # Логируем статистику
            total = stats.get("total", 0)
            if total > 0:
                logger.info(
                    f"📈 Статистика аккаунтов (всего: {total}):\n"
                    f"  • Активных: {stats.get('active', 0)} ({stats.get('percentages', {}).get('active', 0)}%)\n"
                    f"  • В паузе: {stats.get('pause', 0)} ({stats.get('percentages', {}).get('pause', 0)}%)\n"
                    f"  • Забанено: {stats.get('ban', 0)} ({stats.get('percentages', {}).get('ban', 0)}%)\n"
                    f"  • Готово к восстановлению: {stats.get('ready_for_recovery', {}).get('total', 0)}"
                )
            else:
                logger.info("📈 Статистика аккаунтов: аккаунты отсутствуют")
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в задаче статистики: {e}")
    
    async def trigger_recovery_now(self):
        """Принудительно запускает восстановление аккаунтов"""
        if not self.is_running:
            logger.warning("Планировщик не запущен")
            return
            
        try:
            logger.info("🔧 Принудительный запуск автовосстановления...")
            await self._recovery_job()
        except Exception as e:
            logger.error(f"❌ Ошибка принудительного восстановления: {e}")
    
    async def get_scheduler_status(self):
        """Возвращает статус планировщика"""
        if not self.is_running or not self.scheduler:
            return {
                "running": False,
                "jobs": []
            }
        
        jobs_info = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else "N/A"
            })
        
        return {
            "running": True,
            "jobs": jobs_info
        }

# Глобальный экземпляр планировщика
recovery_scheduler = AccountRecoveryScheduler()