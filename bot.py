import os
import asyncio
import json
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

TOKEN = "8722732480:AAHJxkxpT3lbw0NrZuCZTij3EXMFBfxMR0s"
ADMIN_ID = 8404832881

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_FILE = "data.json"

DEFAULT_DATA = {
    "students": {},
    "tasks": {},
    "submissions": {},
}

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


def load_data():
    if not os.path.exists(DATA_FILE):
        return json.loads(json.dumps(DEFAULT_DATA))
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, value in DEFAULT_DATA.items():
            if key not in data:
                data[key] = value.copy() if isinstance(value, dict) else value
        return data
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_DATA))


def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error(f"Saqlashda xatolik: {e}")


def is_admin(user_id):
    return user_id == ADMIN_ID


class Royxat(StatesGroup):
    ism = State()
    guruh = State()


def oquvchi_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Vazifalar")],
            [KeyboardButton(text="📊 Natijam")],
            [KeyboardButton(text="🏆 Ranking")],
            [KeyboardButton(text="👤 Profilim")],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Vazifa berish")],
            [KeyboardButton(text="👥 O'quvchilar")],
            [KeyboardButton(text="📊 Statistika")],
        ],
        resize_keyboard=True,
    )


@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    if is_admin(user_id):
        await message.answer(
            "👨‍🏫 Salom, teacher!\n\nAdmin panel:",
            reply_markup=admin_menu(),
        )
        return

    data = load_data()
    user_id_str = str(user_id)

    if user_id_str in data["students"] and data["students"][user_id_str].get("ism"):
        student = data["students"][user_id_str]
        await message.answer(
            f"Salom, {student['ism']}!\n\n"
            f"🏫 Guruh: {student['guruh']}",
            reply_markup=oquvchi_menu(),
        )
        return

    await message.answer(
        "👋 Salom! Botdan foydalanish uchun ro'yxatdan o'ting.\n\n"
        "1️⃣ Ism va familiyangizni yozing:"
    )
    await state.set_state(Royxat.ism)


@dp.message(Royxat.ism)
async def royxat_ism(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Ism va familiyangizni matn ko'rinishida yozing:")
        return
    ism = message.text.strip()
    if len(ism) < 3:
        await message.answer("To'liq ism va familiyangizni yozing:")
        return
    await state.update_data(ism=ism)
    await message.answer(f"✅ {ism}\n\n2️⃣ Guruhingizni yozing:")
    await state.set_state(Royxat.guruh)


@dp.message(Royxat.guruh)
async def royxat_guruh(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Guruh nomini yozing:")
        return
    guruh = message.text.strip()
    if len(guruh) < 2:
        await message.answer("Guruh nomi juda qisqa:")
        return

    data_user = await state.get_data()
    ism = data_user.get("ism", "Nomalum")
    user_id = str(message.from_user.id)

    data = load_data()
    data["students"][user_id] = {
        "name": message.from_user.full_name,
        "ism": ism,
        "guruh": guruh,
        "ball": 0,
    }
    save_data(data)

    try:
        await bot.send_message(
            ADMIN_ID,
            f"🆕 Yangi o'quvchi!\n👤 {ism}\n🏫 {guruh}\n🆔 {user_id}",
        )
    except Exception as e:
        logger.error(f"Admin xabari xatosi: {e}")

    await message.answer(
        f"✅ Ro'yxatdan o'tdingiz!\n👤 {ism}\n🏫 {guruh}",
        reply_markup=oquvchi_menu(),
    )
    await state.clear()


@dp.message(F.text == "📚 Vazifalar")
async def vazifalar(message: types.Message):
    if is_admin(message.from_user.id):
        return
    await message.answer("📚 Hozircha vazifalar yo'q.")


@dp.message(F.text == "📊 Natijam")
async def natijam(message: types.Message):
    if is_admin(message.from_user.id):
        return
    user_id = str(message.from_user.id)
    data = load_data()
    if user_id not in data["students"]:
        await message.answer("Avval /start bosing.")
        return
    s = data["students"][user_id]
    await message.answer(
        f"📊 Natijangiz:\n\n"
        f"👤 {s.get('ism')}\n"
        f"🏫 {s.get('guruh')}\n"
        f"💰 Ball: {s.get('ball', 0)}"
    )


@dp.message(F.text == "🏆 Ranking")
async def ranking(message: types.Message):
    if is_admin(message.from_user.id):
        return
    await message.answer("🏆 Ranking: #1")


@dp.message(F.text == "👤 Profilim")
async def profilim(message: types.Message):
    if is_admin(message.from_user.id):
        return
    user_id = str(message.from_user.id)
    data = load_data()
    if user_id not in data["students"]:
        await message.answer("Avval /start bosing.")
        return
    s = data["students"][user_id]
    await message.answer(
        f"👤 Profilingiz:\n\n"
        f"Ism: {s.get('ism')}\n"
        f"Guruh: {s.get('guruh')}\n"
        f"Ball: {s.get('ball', 0)}"
    )


@dp.message(F.text == "👥 O'quvchilar")
async def oquvchilar(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    if not data["students"]:
        await message.answer("Hozircha o'quvchilar yo'q.")
        return
    text = f"👥 O'QUVCHILAR ({len(data['students'])} ta)\n\n"
    for uid, info in data["students"].items():
        text += f"👤 {info.get('ism')} ({info.get('guruh')})\n"
    await message.answer(text)


@dp.message(F.text == "📊 Statistika")
async def statistika(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    await message.answer(
        f"📊 Statistika:\n\n"
        f"👥 O'quvchilar: {len(data['students'])}\n"
        f"📚 Vazifalar: {len(data['tasks'])}"
    )


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
