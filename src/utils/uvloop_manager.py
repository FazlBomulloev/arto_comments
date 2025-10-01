import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class UVLoopManager:
    """
    Менеджер для установки и управления uvloop
    """

    def __init__(self):
        self._is_installed = False
        self._error: Optional[str] = None
        self._version: Optional[str] = None

    def install(self) -> Tuple[bool, Optional[str]]:
        """
        Пытается установить и активировать uvloop

        Returns:
            Tuple[bool, Optional[str]]: (Успех, Сообщение об ошибке)
        """
        try:
            import uvloop
            uvloop.install()
            self._is_installed = True
            self._version = uvloop.__version__
            msg = f'UVLOOP v{self._version} успешно установлен и активирован'
            logger.info(msg)
            return True, msg
        except ImportError:
            msg = 'UVLOOP не установлен (pip install uvloop)'
            logger.info(msg)
            self._error = msg
            return False, msg
        except Exception as e:
            msg = f'Ошибка активации UVLOOP: {str(e)}'
            logger.error(msg)
            self._error = msg
            return False, msg

    @property
    def is_installed(self) -> bool:
        """Проверяет, установлен ли uvloop"""
        return self._is_installed

    @property
    def version(self) -> Optional[str]:
        """Возвращает версию uvloop"""
        return self._version

    @property
    def error(self) -> Optional[str]:
        """Возвращает последнюю ошибку"""
        return self._error

    def __str__(self) -> str:
        """Строковое представление статуса"""
        if self._is_installed:
            return f"UVLOOP v{self._version} (активен)"
        return f"UVLOOP недоступен{f' ({self._error})' if self._error else ''}"