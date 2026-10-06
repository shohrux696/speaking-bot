import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiohttp import web

TOKEN = "8722732480:AAHJxkxpT3lbw0NrZuCZTij3EXMFBfxMR0s"
ADMIN_ID = 8404832881

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()


def asosiy_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Vazifalar")],
            [KeyboardButton(text="📊 Natijam")],
            [KeyboardButton(text="🏆 Ranking")],
            [KeyboardButton(text="👤 Profilim")],
        ],
        resize_keyboard=True,
    )


@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        await message.answer("👨‍🏫 Salom, teacher!", reply_markup=asosiy_menu())
    else:
        await message.answer(
            f"👋 Salom, {message.from_user.full_name}!\n\n"
            f"Speaking Bot ga xush kelibsiz!",
            reply_markup=asosiy_menu(),
        )


@dp.message(F.text == "📚 Vazifalar")
async def vazifalar(message: types.Message):
    await message.answer("📚 Hozircha vazifalar yo'q.")


@dp.message(F.text == "📊 Natijam")
async def natijam(message: types.Message):
    await message.answer("📊 Natijangiz: 0%")


@dp.message(F.text == "🏆 Ranking")
async def ranking(message: types.Message):
    await message.answer("🏆 Ranking: #1")


@dp.message(F.text == "👤 Profilim")
async def profilim(message: types.Message):
    await message.answer(f"👤 {message.from_user.full_name}")


async def handle(request):
    return web.Response(text="🤖 Bot ishlayapti!")


async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web server {port}-portda ishga tushdi.")


async def main():
    logger.info("Bot ishga tushmoqda...")
    asyncio.create_task(web_server())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
