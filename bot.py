import os
import asyncio
import json
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

TOKEN = os.getenv("TOKEN", "8722732480:AAHJxkxpT3lbw0NrZuCZTij3EXMFBfxMR0s")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8404832881"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_FILE = "data.json"

DEFAULT_DATA = {
    "students": {},
    "tasks": {},
    "submissions": {},
    "extra_tasks": {},
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


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class Royxat(StatesGroup):
    ism = State()
    guruh = State()


class VazifaBerish(StatesGroup):
    nomi = State()
    savol = State()
    deadline = State()
    tasdiqlash = State()


class QoshimchaVazifa(StatesGroup):
    nomi = State()
    savol = State()
    deadline = State()
    tasdiqlash = State()


class AudioYuborish(StatesGroup):
    vazifa_id = State()


def oquvchi_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Vazifalar")],
            [KeyboardButton(text="➕ Qo'shimcha vazifalar")],
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
            [KeyboardButton(text="➕ Qo'shimcha vazifa berish")],
            [KeyboardButton(text="📥 Kelgan javoblar")],
            [KeyboardButton(text="👥 O'quvchilar")],
            [KeyboardButton(text="📊 Statistika")],
        ],
        resize_keyboard=True,
    )


def tasdiqlash_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Yuborish")],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True,
    )


def ortga_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Ortga")]],
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
            f"Salom, {student['ism']}!\n\n🏫 Guruh: {student['guruh']}",
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
        "registered": now_str(),
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


# ==================== ADMIN: VAZIFA BERISH ====================

@dp.message(F.text == "📚 Vazifa berish")
async def vazifa_berish_boshlash(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(tur="asosiy")
    await message.answer(
        "📚 YANGI ASOSIY VAZIFA\n\n1️⃣ Vazifa nomini yozing:",
        reply_markup=ortga_menu(),
    )
    await state.set_state(VazifaBerish.nomi)


@dp.message(VazifaBerish.nomi)
async def vazifa_nomi(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
        await state.clear()
        return
    if not message.text:
        await message.answer("Vazifa nomini matn ko'rinishida yozing:")
        return
    await state.update_data(nomi=message.text.strip())
    await message.answer(
        f"✅ Nomi: {message.text.strip()}\n\n2️⃣ Speaking savolini yozing:"
    )
    await state.set_state(VazifaBerish.savol)


@dp.message(VazifaBerish.savol)
async def vazifa_savol(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
        await state.clear()
        return
    if not message.text:
        await message.answer("Savolni matn ko'rinishida yozing:")
        return
    await state.update_data(savol=message.text.strip())
    await message.answer(
        "✅ Savol qabul qilindi.\n\n3️⃣ Deadline kiriting (masalan: 2026-10-10 20:00):"
    )
    await state.set_state(VazifaBerish.deadline)


@dp.message(VazifaBerish.deadline)
async def vazifa_deadline(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
        await state.clear()
        return
    if not message.text:
        await message.answer("Deadline ni yozing (masalan: 2026-10-10 20:00):")
        return
    await state.update_data(deadline=message.text.strip())

    data_user = await state.get_data()
    nomi = data_user.get("nomi")
    savol = data_user.get("savol")
    deadline = data_user.get("deadline")
    tur = data_user.get("tur", "asosiy")

    data = load_data()
    students_count = len(data["students"])

    text = (
        f"📋 TASDIQLASH\n\n"
        f"📌 Turi: {'📚 Asosiy' if tur == 'asosiy' else '➕ Qo\'shimcha'}\n"
        f"📝 Nomi: {nomi}\n\n"
        f"❓ Savol:\n{savol}\n\n"
        f"⏰ Deadline: {deadline}\n"
        f"👥 O'quvchilar: {students_count} ta\n\n"
        f"Yuborishni tasdiqlaysizmi?"
    )
    await message.answer(text, reply_markup=tasdiqlash_menu())
    await state.set_state(VazifaBerish.tasdiqlash)


@dp.message(VazifaBerish.tasdiqlash)
async def vazifa_tasdiqlash(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
        await state.clear()
        return
    if message.text != "✅ Yuborish":
        await message.answer("Tugmalardan birini tanlang.")
        return

    data_user = await state.get_data()
    nomi = data_user.get("nomi")
    savol = data_user.get("savol")
    deadline = data_user.get("deadline")
    tur = data_user.get("tur", "asosiy")

    data = load_data()
    task_id = str(len(data["tasks"]) + 1)
    data["tasks"][task_id] = {
        "nomi": nomi,
        "savol": savol,
        "deadline": deadline,
        "tur": tur,
        "created": now_str(),
    }
    save_data(data)

    sent = 0
    for uid in data["students"]:
        try:
            await bot.send_message(
                int(uid),
                f"{'📚 YANGI ASOSIY VAZIFA' if tur == 'asosiy' else '➕ YANGI QO\'SHIMCHA VAZIFA'}\n\n"
                f"📝 {nomi}\n\n"
                f"❓ {savol}\n\n"
                f"⏰ Deadline: {deadline}\n\n"
                f"Vazifani topshirish uchun '📚 Vazifalar' tugmasini bosing.",
            )
            sent += 1
        except Exception as e:
            logger.error(f"Xabar yuborish xatosi {uid}: {e}")

    await message.answer(
        f"✅ Vazifa {sent} ta o'quvchiga yuborildi!",
        reply_markup=admin_menu(),
    )
    await state.clear()


# ==================== O'QUVCHI: VAZIFALAR ====================

@dp.message(F.text == "📚 Vazifalar")
async def oquvchi_vazifalar(message: types.Message):
    if is_admin(message.from_user.id):
        return

    data = load_data()
    user_id = str(message.from_user.id)

    if user_id not in data["students"]:
        await message.answer("Avval /start bosing.")
        return

    tasks = [(tid, t) for tid, t in data["tasks"].items() if t.get("tur") == "asosiy"]

    if not tasks:
        await message.answer("📚 Hozircha asosiy vazifalar yo'q.")
        return

    text = "📚 ASOSIY VAZIFALAR\n\n"
    for tid, task in tasks:
        submitted = data["submissions"].get(tid, {})
        if user_id in submitted:
            status = "🟢 Yuborilgan"
        else:
            status = "🔴 Yuborilmagan"

        text += f"{tid}. {task['nomi']}\n"
        text += f"   {status}\n"
        text += f"   ⏰ {task['deadline']}\n\n"

    text += "Vazifani topshirish uchun /submit buyrug'ini bosing."
    await message.answer(text)


@dp.message(F.text == "➕ Qo'shimcha vazifalar")
async def oquvchi_qoshimcha(message: types.Message):
    if is_admin(message.from_user.id):
        return

    data = load_data()
    user_id = str(message.from_user.id)

    if user_id not in data["students"]:
        await message.answer("Avval /start bosing.")
        return

    tasks = [(tid, t) for tid, t in data["tasks"].items() if t.get("tur") == "qoshimcha"]

    if not tasks:
        await message.answer("➕ Hozircha qo'shimcha vazifalar yo'q.")
        return

    text = "➕ QO'SHIMCHA VAZIFALAR\n\n"
    for tid, task in tasks:
        submitted = data["submissions"].get(tid, {})
        if user_id in submitted:
            status = "🟢 Yuborilgan"
        else:
            status = "🔴 Yuborilmagan"

        text += f"{tid}. {task['nomi']}\n"
        text += f"   {status}\n"
        text += f"   ⏰ {task['deadline']}\n\n"

    await message.answer(text)


# ==================== O'QUVCHI: AUDIO YUBORISH ====================

@dp.message(Command("submit"))
async def submit_start(message: types.Message, state: FSMContext):
    if is_admin(message.from_user.id):
        return

    data = load_data()
    if not data["tasks"]:
        await message.answer("Hozircha vazifalar yo'q.")
        return

    text = "Qaysi vazifaga audio yubormoqchisiz?\n\n"
    for tid, task in data["tasks"].items():
        text += f"{tid}. {task['nomi']}\n"

    text += "\nVazifa raqamini yozing:"
    await message.answer(text)
    await state.set_state(AudioYuborish.vazifa_id)


@dp.message(AudioYuborish.vazifa_id)
async def audio_vazifa_id(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Vazifa raqamini yozing:")
        return

    task_id = message.text.strip()
    data = load_data()

    if task_id not in data["tasks"]:
        await message.answer("Bunday vazifa topilmadi. Qaytadan yozing:")
        return

    await state.update_data(task_id=task_id)
    await message.answer(
        f"✅ Vazifa: {data['tasks'][task_id]['nomi']}\n\n"
        f"🎤 Endi audio javobingizni yuboring:",
        reply_markup=ortga_menu(),
    )


@dp.message(AudioYuborish.vazifa_id, F.voice)
async def audio_qabul(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data_user = await state.get_data()
    task_id = data_user.get("task_id")

    if not task_id:
        await message.answer("Vazifa tanlanmagan. /submit bosing.")
        await state.clear()
        return

    data = load_data()
    if task_id not in data["tasks"]:
        await message.answer("Vazifa topilmadi.")
        await state.clear()
        return

    if task_id not in data["submissions"]:
        data["submissions"][task_id] = {}

    data["submissions"][task_id][user_id] = {
        "audio_file_id": message.voice.file_id,
        "submitted_at": now_str(),
        "status": "pending",
    }
    save_data(data)

    ism = data["students"][user_id].get("ism", "Nomalum")
    guruh = data["students"][user_id].get("guruh", "—")

    await message.answer(
        "✅ Audio qabul qilindi!\n\nO'qituvchi tekshiradi.",
        reply_markup=oquvchi_menu(),
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            f"📥 YANGI AUDIO!\n\n"
            f"👤 {ism} ({guruh})\n"
            f"📚 Vazifa: {data['tasks'][task_id]['nomi']}\n"
            f"⏰ {now_str()}",
        )
        await bot.send_voice(ADMIN_ID, message.voice.file_id)
    except Exception as e:
        logger.error(f"Admin xabari xatosi: {e}")

    await state.clear()


# ==================== ADMIN: KELGAN JAVOBLAR ====================

@dp.message(F.text == "📥 Kelgan javoblar")
async def kelgan_javoblar(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    data = load_data()
    if not data["submissions"]:
        await message.answer("📥 Hozircha javoblar yo'q.")
        return

    text = "📥 KELGAN JAVOBLAR\n\n"
    count = 0
    for task_id, subs in data["submissions"].items():
        task_name = data["tasks"].get(task_id, {}).get("nomi", "Nomalum")
        for uid, sub in subs.items():
            if sub.get("status") == "pending":
                student = data["students"].get(uid, {})
                ism = student.get("ism", "Nomalum")
                guruh = student.get("guruh", "—")
                text += f"👤 {ism} ({guruh})\n"
                text += f"📚 {task_name}\n"
                text += f"⏰ {sub.get('submitted_at')}\n\n"
                count += 1

    if count == 0:
        text += "Tekshirilmagan javoblar yo'q."

    await message.answer(text)


# ==================== ADMIN: O'QUVCHILAR ====================

@dp.message(F.text == "👥 O'quvchilar")
async def admin_oquvchilar(message: types.Message):
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
async def admin_statistika(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    data = load_data()
    total_students = len(data["students"])
    total_tasks = len(data["tasks"])

    text = (
        f"📊 STATISTIKA\n\n"
        f"👥 O'quvchilar: {total_students}\n"
        f"📚 Vazifalar: {total_tasks}\n"
    )
    await message.answer(text)


# ==================== O'QUVCHI: NATIJA, RANKING, PROFIL ====================

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

    total_subs = 0
    for task_id, subs in data["submissions"].items():
        if user_id in subs:
            total_subs += 1

    await message.answer(
        f"📊 Natijangiz:\n\n"
        f"👤 {s.get('ism')}\n"
        f"🏫 {s.get('guruh')}\n"
        f"📚 Topshirilgan: {total_subs}\n"
        f"💰 Ball: {s.get('ball', 0)}"
    )


@dp.message(F.text == "🏆 Ranking")
async def ranking(message: types.Message):
    if is_admin(message.from_user.id):
        return
    await message.answer("🏆 Ranking tez orada qo'shiladi.")


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
        f"Ro'yxatdan o'tgan: {s.get('registered')}"
    )


# ==================== WEB SERVER ====================

async def handle(request):
    return web.Response(text="🤖 Speaking Bot ishlayapti!")


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
