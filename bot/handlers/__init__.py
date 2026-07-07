from aiogram import Router

from .basic import router as basic_router
from .check import router as check_router
from .settings import router as settings_router
from .stats import router as stats_router


def get_router() -> Router:
    """Return a parent router with all sub-routers included."""
    router = Router(name="root")
    router.include_router(basic_router)
    router.include_router(settings_router)
    router.include_router(check_router)
    router.include_router(stats_router)
    return router
