"""
/settings command handler with FSM-based interactive editing.
"""
from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.database.db import Database
from bot.services.proxy.checker import CheckerConfig
from bot.utils.formatting import settings_message

router = Router(name="settings")


class SettingsFSM(StatesGroup):
    waiting_value = State()


def _kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🌐 Test URL", callback_data="set:test_url")],
        [
            InlineKeyboardButton(text="⏱ Timeout", callback_data="set:timeout"),
            InlineKeyboardButton(text="🔁 Retries", callback_data="set:retries"),
        ],
        [
            InlineKeyboardButton(text="⚡ Concurrency", callback_data="set:concurrency"),
            InlineKeyboardButton(text="👷 Max workers", callback_data="set:max_workers"),
        ],
        [InlineKeyboardButton(text="🔄 Reset defaults", callback_data="set:reset")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


_FIELD_PROMPTS: dict[str, str] = {
    "test_url": "Enter new test URL (e.g. <code>https://httpbin.org/ip</code>):",
    "timeout": "Enter timeout in seconds (1–120):",
    "retries": "Enter retry count (0–5):",
    "concurrency": "Enter concurrency (1–2000):",
    "max_workers": "Enter max workers (1–5000):",
}


@router.message(Command("settings"))
async def cmd_settings(message: Message, db: Database) -> None:
    cfg = await db.get_settings(message.from_user.id)  # type: ignore[union-attr]
    await message.answer(settings_message(cfg), parse_mode="HTML", reply_markup=_kb())


@router.callback_query(F.data.startswith("set:"))
async def settings_button(
    call: CallbackQuery, state: FSMContext, db: Database
) -> None:
    await call.answer()
    field = call.data.split(":", 1)[1]  # type: ignore[union-attr]

    if field == "reset":
        cfg = CheckerConfig()
        await db.save_settings(call.from_user.id, cfg)  # type: ignore[union-attr]
        await call.message.edit_text(  # type: ignore[union-attr]
            "✅ Settings reset to defaults.\n\n" + settings_message(cfg),
            parse_mode="HTML",
            reply_markup=_kb(),
        )
        return

    await state.update_data(editing_field=field)
    await state.set_state(SettingsFSM.waiting_value)
    await call.message.answer(  # type: ignore[union-attr]
        _FIELD_PROMPTS.get(field, "Enter new value:"), parse_mode="HTML"
    )


@router.message(SettingsFSM.waiting_value)
async def receive_setting_value(
    message: Message, state: FSMContext, db: Database
) -> None:
    data = await state.get_data()
    field: str = data.get("editing_field", "")
    raw = (message.text or "").strip()
    uid = message.from_user.id  # type: ignore[union-attr]

    cfg = await db.get_settings(uid)
    error: str | None = None

    try:
        if field == "test_url":
            if not raw.startswith(("http://", "https://")):
                error = "URL must start with http:// or https://"
            else:
                cfg.test_url = raw
        elif field == "timeout":
            v = float(raw)
            if not 1 <= v <= 120:
                error = "Must be between 1 and 120."
            else:
                cfg.timeout = v
        elif field == "retries":
            v = int(raw)
            if not 0 <= v <= 5:
                error = "Must be between 0 and 5."
            else:
                cfg.retries = v
        elif field == "concurrency":
            v = int(raw)
            if not 1 <= v <= 2000:
                error = "Must be between 1 and 2000."
            else:
                cfg.concurrency = v
        elif field == "max_workers":
            v = int(raw)
            if not 1 <= v <= 5000:
                error = "Must be between 1 and 5000."
            else:
                cfg.max_workers = v
        else:
            error = "Unknown setting."
    except ValueError:
        error = "Invalid value. Please enter a number."

    if error:
        await message.answer(f"❌ {error}")
        return

    await db.save_settings(uid, cfg)
    await state.clear()
    await message.answer(
        f"✅ <b>{field}</b> updated.\n\n" + settings_message(cfg),
        parse_mode="HTML",
        reply_markup=_kb(),
    )
