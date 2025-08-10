import os, asyncio
from aiohttp import web
import time
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums.parse_mode import ParseMode
from aiogram.types.input_file import FSInputFile
from aiogram.utils.markdown import hbold

# ---------- Config ----------
@dataclass
class Config:
    token: str
    admin_id: Optional[int]
    pre_save_url: str
    channel_url: str
    audio_path: str = "audio/096_WARRIOR_hotline_8k_mono.wav"  # путь к вашему файлу


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")
    admin = os.getenv("ADMIN_ID", "").strip()
    admin_id = int(admin) if admin.isdigit() else None
    pre = os.getenv("PRE_SAVE_URL", "https://example.com/presave")
    chan = os.getenv("CHANNEL_URL", "https://t.me/your_channel")
    return Config(token, admin_id, pre, chan)


# ---------- Simple in‑memory storage ----------
USERS: set[int] = set()
LAST_ACTION_AT: dict[int, float] = {}
AUDIO_FILE_ID: Optional[str] = None  # будет заполнено после первой отправки
THROTTLE_SECONDS = 5


def throttled(user_id: int) -> bool:
    now = time.time()
    last = LAST_ACTION_AT.get(user_id, 0)
    if now - last < THROTTLE_SECONDS:
        return True
    LAST_ACTION_AT[user_id] = now
    return False


# ---------- Keyboards ----------

def main_kb(pre_url: str, channel_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="PRE‑SAVE", url=pre_url)],
        [InlineKeyboardButton(text="СЕКРЕТ", url=channel_url)],
    ])


WELCOME_TEXT = (
    "Код 096 активирован.\n"
    f"Дата: {hbold('24.08')}\n"
    "Слушай. Нажми кнопку."
)
HELP_TEXT = "Напиши 096 — получишь голос. Кнопки ниже — ссылки."


# ---------- Handlers ----------
async def on_start(message: Message, cfg: Config, bot: Bot):
    USERS.add(message.from_user.id)
    if throttled(message.from_user.id):
        return

    await message.answer(WELCOME_TEXT, parse_mode=ParseMode.HTML)

    global AUDIO_FILE_ID
    kb = main_kb(cfg.pre_save_url, cfg.channel_url)

    try:
        if AUDIO_FILE_ID:
            await message.answer_audio(audio=AUDIO_FILE_ID, caption="096 WARRIOR — голос", reply_markup=kb)
        else:
            # Первая отправка — грузим с диска, дальше Telegram вернёт file_id
            file = FSInputFile(cfg.audio_path)
            msg = await message.answer_audio(audio=file, caption="096 WARRIOR — голос", reply_markup=kb)
            AUDIO_FILE_ID = msg.audio.file_id
    except Exception as e:
        await message.answer("Не удалось отправить голос. Попробуй ещё раз.")
        if cfg.admin_id:
            await bot.send_message(cfg.admin_id, f"Ошибка аудио: {e}")


async def on_help(message: Message):
    await message.answer(HELP_TEXT)


async def on_stats(message: Message, cfg: Config):
    if cfg.admin_id and message.from_user.id == cfg.admin_id:
        await message.answer(f"Users: {len(USERS)}")
    else:
        await message.answer("Команда только для админа.")


async def on_keyword(message: Message, cfg: Config):
    text = (message.text or "").strip().lower()
    if text != "096":
        return
    if throttled(message.from_user.id):
        return
    kb = main_kb(cfg.pre_save_url, cfg.channel_url)
    global AUDIO_FILE_ID
    if AUDIO_FILE_ID:
        await message.answer_audio(audio=AUDIO_FILE_ID, caption="096 WARRIOR — голос", reply_markup=kb)
    else:
        file = FSInputFile(cfg.audio_path)
        msg = await message.answer_audio(audio=file, caption="096 WARRIOR — голос", reply_markup=kb)
        AUDIO_FILE_ID = msg.audio.file_id


# ---------- Bootstrap ----------
async def main():
    cfg = load_config()
    bot = Bot(token=cfg.token)
    dp = Dispatcher()

    dp.message.register(lambda m: on_start(m, cfg, bot), Command(commands=["start"]))
    dp.message.register(on_help, Command(commands=["help"]))
    dp.message.register(lambda m: on_stats(m, cfg), Command(commands=["stats"]))
    dp.message.register(lambda m: on_keyword(m, cfg), F.text)

    print("Bot is running…")
    await dp.start_polling(bot)


# --- KEEP-ALIVE HTTP for Render Web Service ---
import os, asyncio
from aiohttp import web

# --- Мини-HTTP для Render (держим открытый порт) ---
async def _health(request):
    return web.Response(text="ok")

async def _run_web():
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/healthz", _health)
    port = int(os.getenv("PORT", "10000"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"HTTP keep-alive on :{port}")

# ---- Запуск бота и веба параллельно ----
if __name__ == "__main__":
    async def _runner():
        web_task = asyncio.create_task(_run_web())
        bot_task = asyncio.create_task(main())  # это твоя функция, где dp.start_polling(...)
        await asyncio.gather(web_task, bot_task)

    try:
        asyncio.run(_runner())
    except (KeyboardInterrupt, SystemExit):
        print("Stopped")

