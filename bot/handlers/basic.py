"""
/start and /help command handlers.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="basic")

_HELP_TEXT = """
<b>🔍 Proxy Checker Bot</b>

<b>Commands</b>
/start   — Welcome message
/help    — This help text
/check   — Start a new check (paste proxies or upload a .txt file)
/settings — View & change your check settings
/stats   — Stats for your last job
/cancel  — Cancel the running job

<b>Accepted formats</b>
<code>ip:port
ip:port:user:pass
user:pass@ip:port
http://ip:port
https://ip:port
socks4://ip:port
socks5://ip:port</code>

<b>Output files</b>
working.txt · dead.txt · http.txt · https.txt
socks4.txt · socks5.txt · auth_failed.txt
timeout.txt · invalid_format.txt

Max <b>100,000</b> proxies per job.
"""

_START_TEXT = (
    "👋 <b>Welcome to Proxy Checker Bot!</b>\n\n"
    "Send /check and paste your proxy list (or upload a .txt file).\n"
    "Type /help for full documentation."
)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(_START_TEXT, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_HELP_TEXT, parse_mode="HTML")
