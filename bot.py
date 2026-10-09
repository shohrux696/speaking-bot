import os
import asyncio
import json
import re
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from groq import Groq

# ==================== SOZLAMALAR ====================
TOKEN = os.environ.get("TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8404832881"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

groq_client = Groq(api_key=GROQ_API_KEY)

DATA_FILE = "/data/data.json"

DEFAULT_DATA = {
    "students": {},
    "pending_students": {},
    "tasks": {},
    "submissions": {},
    "warnings": {},
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
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error(f"Saqlashda xatolik: {e}")


def is_admin(user_id):
    return user_id == ADMIN_ID


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ==================== HOLATLAR ====================
class Royxat(StatesGroup):
    ism = State()
    guruh = State()


class VazifaBerish(StatesGroup):
    nomi = State()
    savollar = State()
    deadline = State()
    tasdiqlash = State()


class AudioYuborish(StatesGroup):
    vazifa_id = State()
    savol_raqami = State()


class VazifaOchirish(StatesGroup):
    vazifa_id = State()


class OquvchiOchirish(StatesGroup):
    user_id = State()


# ==================== MENYULAR ====================
def oquvchi_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Vazifani topshirish")],
            [KeyboardButton(text="📋 Tugallanmagan vazifalar")],
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
            [KeyboardButton(text="📥 Kelgan javoblar")],
            [KeyboardButton(text="👥 O'quvchilar")],
            [KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="🗑 Vazifani o'chirish")],
            [KeyboardButton(text="🗑 O'quvchini o'chirish")],
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


# ==================== START ====================
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    if is_admin(user_id):
        await message.answer("👨‍🏫 Salom, teacher!\n\nAdmin panel:", reply_markup=admin_menu())
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

    if user_id_str in data["pending_students"]:
        await message.answer("⏳ Sizning so'rovingiz admin tasdiqlashini kutmoqda.")
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

    data["pending_students"][user_id] = {
        "name": message.from_user.full_name,
        "ism": ism,
        "guruh": guruh,
        "registered": now_str(),
    }
    save_data(data)

    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{user_id}"),
            ]
        ])
        await bot.send_message(
            ADMIN_ID,
            f"🆕 YANGI RO'YXATDAN O'TISH SO'ROVI!\n\n"
            f"👤 Ism: {ism}\n"
            f"🏫 Guruh: {guruh}\n"
            f"📱 Telegram: {message.from_user.full_name}\n"
            f"🆔 ID: {user_id}\n\n"
            f"Tasdiqlaysizmi?",
            reply_markup=kb,
        )
    except Exception as e:
        logger.error(f"Admin xabari xatosi: {e}")

    await message.answer(
        "⏳ So'rovingiz adminga yuborildi.\n\n"
        "Admin tasdiqlagandan keyin botdan foydalanishingiz mumkin.",
    )
    await state.clear()


# ==================== ADMIN: TASDIQLASH / RAD ETISH ====================
@dp.callback_query(F.data.startswith("approve_"))
async def approve_student(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Siz admin emassiz!")
        return

    user_id = callback.data.replace("approve_", "")
    data = load_data()

    if user_id not in data["pending_students"]:
        await callback.answer("Bu o'quvchi allaqachon tasdiqlangan.")
        return

    student = data["pending_students"][user_id]
    data["students"][user_id] = {
        "name": student.get("name", ""),
        "ism": student.get("ism", "Nomalum"),
        "guruh": student.get("guruh", "—"),
        "ball": 0,
        "registered": now_str(),
    }
    del data["pending_students"][user_id]
    save_data(data)

    try:
        await bot.send_message(
            int(user_id),
            f"✅ Sizning so'rovingiz tasdiqlandi!\n\n"
            f"👤 {student['ism']}\n"
            f"🏫 {student['guruh']}\n\n"
            f"Botdan foydalanishingiz mumkin.",
            reply_markup=oquvchi_menu(),
        )
    except Exception as e:
        logger.error(f"O'quvchiga xabar xatosi: {e}")

    await callback.message.edit_text(
        f"✅ TASDIQLANDI: {student['ism']} ({student['guruh']})"
    )
    await callback.answer("Tasdiqlandi!")


@dp.callback_query(F.data.startswith("reject_"))
async def reject_student(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Siz admin emassiz!")
        return

    user_id = callback.data.replace("reject_", "")
    data = load_data()

    if user_id not in data["pending_students"]:
        await callback.answer("Bu o'quvchi allaqachon tasdiqlangan.")
        return

    student = data["pending_students"][user_id]
    del data["pending_students"][user_id]
    save_data(data)

    try:
        await bot.send_message(
            int(user_id),
            "❌ Sizning so'rovingiz rad etildi.",
        )
    except Exception as e:
        logger.error(f"O'quvchiga xabar xatosi: {e}")

    await callback.message.edit_text(
        f"❌ RAD ETILDI: {student['ism']} ({student['guruh']})"
    )
    await callback.answer("Rad etildi!")


# ==================== ADMIN: VAZIFA BERISH ====================
@dp.message(F.text == "📚 Vazifa berish")
async def vazifa_berish_boshlash(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "📚 YANGI VAZIFA\n\n"
        "1️⃣ Vazifa nomini yozing:\n\n"
        "Masalan: Part 1.1",
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
        f"✅ Nomi: {message.text.strip()}\n\n"
        f"2️⃣ Savollarni kiriting (har bir qatorda bittadan):\n\n"
        f"Masalan:\n"
        f"1. What is your name?\n"
        f"2. Where are you from?\n"
        f"3. Do you like reading?\n"
        f"..."
    )
    await state.set_state(VazifaBerish.savollar)


@dp.message(VazifaBerish.savollar)
async def vazifa_savollar(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
        await state.clear()
        return
    if not message.text:
        await message.answer("Savollarni kiriting:")
        return

    lines = message.text.strip().split("\n")
    savollar = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        cleaned = re.sub(r'^\d+[\.\)\-\:]\s*', '', line)
        if cleaned:
            savollar.append(cleaned)

    if not savollar:
        await message.answer("Kamida 1 ta savol kiriting:")
        return

    await state.update_data(savollar=savollar)
    await message.answer(
        f"✅ {len(savollar)} ta savol qabul qilindi.\n\n"
        f"3️⃣ Deadline kiriting (masalan: 2026-10-15 20:00):"
    )
    await state.set_state(VazifaBerish.deadline)


@dp.message(VazifaBerish.deadline)
async def vazifa_deadline(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
        await state.clear()
        return
    if not message.text:
        await message.answer("Deadline ni yozing (masalan: 2026-10-15 20:00):")
        return
    await state.update_data(deadline=message.text.strip())

    data_user = await state.get_data()
    nomi = data_user.get("nomi")
    savollar = data_user.get("savollar", [])
    deadline = data_user.get("deadline")

    data = load_data()
    students_count = len(data["students"])

    text = f"📋 TASDIQLASH\n\n"
    text += f"📝 Nomi: {nomi}\n"
    text += f"🔢 Savollar: {len(savollar)} ta\n"
    text += f"⏰ Deadline: {deadline}\n"
    text += f"👥 O'quvchilar: {students_count} ta\n\n"
    text += f"❓ Savollar:\n"
    for i, s in enumerate(savollar, 1):
        text += f"{i}. {s}\n"

    text += f"\n💰 Maksimal ball: {len(savollar)}\n\n"
    text += f"✅ Tasdiqlaysizmi?"

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
    savollar = data_user.get("savollar", [])
    deadline = data_user.get("deadline")

    data = load_data()
    task_id = str(len(data["tasks"]) + 1)
    data["tasks"][task_id] = {
        "nomi": nomi,
        "savollar": savollar,
        "savollar_soni": len(savollar),
        "deadline": deadline,
        "created": now_str(),
    }
    save_data(data)

    sent = 0
    for uid in data["students"]:
        try:
            text = f"📚 YANGI VAZIFA\n\n"
            text += f"📝 Nomi: {nomi}\n"
            text += f"🔢 Savollar: {len(savollar)} ta\n"
            text += f"⏰ Deadline: {deadline}\n\n"
            text += f"❓ Savollar:\n"
            for i, s in enumerate(savollar, 1):
                text += f"{i}. {s}\n"
            text += f"\n💰 Maksimal ball: {len(savollar)}\n\n"
            text += f"Topshirish uchun '📝 Vazifani topshirish' tugmasini bosing."

            await bot.send_message(int(uid), text)
            sent += 1
        except Exception as e:
            logger.error(f"Xabar yuborish xatosi {uid}: {e}")

    await message.answer(
        f"✅ Vazifa {sent} ta o'quvchiga yuborildi!\n"
        f"💰 Maksimal ball: {len(savollar)}",
        reply_markup=admin_menu(),
    )
    await state.clear()


# ==================== ADMIN: VAZIFANI O'CHIRISH ====================
@dp.message(F.text == "🗑 Vazifani o'chirish")
async def vazifa_ochirish_boshlash(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = load_data()
    if not data["tasks"]:
        await message.answer("Hozircha vazifalar yo'q.", reply_markup=admin_menu())
        return

    text = "🗑 VAZIFANI O'CHIRISH\n\nQaysi vazifani o'chirmoqchisiz?\n\n"
    for tid, task in data["tasks"].items():
        text += f"{tid}. {task['nomi']} ({task.get('savollar_soni', 0)} ta savol)\n"

    text += "\nVazifa raqamini yozing:"
    await message.answer(text, reply_markup=ortga_menu())
    await state.set_state(VazifaOchirish.vazifa_id)


@dp.message(VazifaOchirish.vazifa_id)
async def vazifa_ochirish(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
        await state.clear()
        return

    task_id = message.text.strip()
    data = load_data()

    if task_id not in data["tasks"]:
        await message.answer("Bunday vazifa topilmadi. Qaytadan yozing:")
        return

    task_nomi = data["tasks"][task_id]["nomi"]
    del data["tasks"][task_id]

    if task_id in data["submissions"]:
        del data["submissions"][task_id]

    save_data(data)

    await message.answer(
        f"✅ Vazifa o'chirildi!\n\n📝 {task_nomi}",
        reply_markup=admin_menu(),
    )
    await state.clear()


# ==================== ADMIN: O'QUVCHINI O'CHIRISH ====================
@dp.message(F.text == "🗑 O'quvchini o'chirish")
async def oquvchi_ochirish_boshlash(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = load_data()
    if not data["students"]:
        await message.answer("Hozircha o'quvchilar yo'q.", reply_markup=admin_menu())
        return

    text = "🗑 O'QUVCHINI O'CHIRISH\n\nQaysi o'quvchini o'chirmoqchisiz?\n\n"
    for uid, info in data["students"].items():
        text += f"🆔 {uid}\n👤 {info.get('ism')} ({info.get('guruh')})\n\n"

    text += "O'quvchi ID raqamini yozing:"
    await message.answer(text, reply_markup=ortga_menu())
    await state.set_state(OquvchiOchirish.user_id)


@dp.message(OquvchiOchirish.user_id)
async def oquvchi_ochirish(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
        await state.clear()
        return

    user_id = message.text.strip()
    data = load_data()

    if user_id not in data["students"]:
        await message.answer("Bunday o'quvchi topilmadi. Qaytadan yozing:")
        return

    ism = data["students"][user_id].get("ism", "Nomalum")

    del data["students"][user_id]

    for task_id in list(data["submissions"].keys()):
        if user_id in data["submissions"][task_id]:
            del data["submissions"][task_id][user_id]

    save_data(data)

    await message.answer(
        f"✅ O'quvchi o'chirildi!\n\n👤 {ism}",
        reply_markup=admin_menu(),
    )
    await state.clear()


# ==================== O'QUVCHI: TUGALLANMAGAN VAZIFALAR ====================
@dp.message(F.text == "📋 Tugallanmagan vazifalar")
async def tugallanmagan_vazifalar(message: types.Message):
    if is_admin(message.from_user.id):
        return

    data = load_data()
    user_id = str(message.from_user.id)

    if user_id not in data["students"]:
        await message.answer("Avval /start bosing.")
        return

    tugallanmagan = []
    for tid, task in data["tasks"].items():
        submitted = data["submissions"].get(tid, {}).get(user_id, {})
        savollar_soni = task.get("savollar_soni", 0)
        audiolar = len(submitted.get("audios", {}))
        if audiolar < savollar_soni:
            tugallanmagan.append((tid, task, audiolar, savollar_soni))

    if not tugallanmagan:
        await message.answer("✅ Sizda tugallanmagan vazifalar yo'q!")
        return

    text = f"📋 TUGALLANMAGAN VAZIFALAR ({len(tugallanmagan)} ta)\n\n"
    for tid, task, audiolar, savollar_soni in tugallanmagan:
        text += f"📚 {tid}. {task['nomi']}\n"
        text += f"   🎤 {audiolar}/{savollar_soni} audio\n"
        text += f"   ⏰ {task['deadline']}\n\n"

    await message.answer(text)


# ==================== O'QUVCHI: VAZIFA TOPSHIRISH ====================
@dp.message(F.text == "📝 Vazifani topshirish")
async def vazifa_topshirish_boshlash(message: types.Message, state: FSMContext):
    if is_admin(message.from_user.id):
        return

    data = load_data()
    if not data["tasks"]:
        await message.answer("Hozircha vazifalar yo'q.")
        return

    user_id = str(message.from_user.id)

    text = "📝 VAZIFA TOPSHIRISH\n\nQaysi vazifani topshirmoqchisiz?\n\n"
    for tid, task in data["tasks"].items():
        submitted = data["submissions"].get(tid, {}).get(user_id, {})
        savollar_soni = task.get("savollar_soni", 0)
        audiolar = len(submitted.get("audios", {}))
        text += f"{tid}. {task['nomi']} — 🎤 {audiolar}/{savollar_soni}\n"

    text += "\nVazifa raqamini yozing:"
    await message.answer(text, reply_markup=ortga_menu())
    await state.set_state(AudioYuborish.vazifa_id)


@dp.message(AudioYuborish.vazifa_id, F.text)
async def audio_vazifa_id(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Asosiy menyu:", reply_markup=oquvchi_menu())
        await state.clear()
        return

    task_id = message.text.strip()
    data = load_data()
    user_id = str(message.from_user.id)

    if task_id not in data["tasks"]:
        await message.answer("Bunday vazifa topilmadi. Qaytadan yozing:")
        return

    task = data["tasks"][task_id]
    savollar = task.get("savollar", [])

    submitted = data["submissions"].get(task_id, {}).get(user_id, {})
    audios = submitted.get("audios", {})

    text = f"✅ Vazifa: {task['nomi']}\n\n"
    text += f"❓ Savollar ({len(savollar)} ta):\n\n"

    for i, savol in enumerate(savollar, 1):
        status = "🟢 Yuborilgan" if str(i) in audios else "🔴 Yuborilmagan"
        text += f"{i}. {savol} — {status}\n"

    text += f"\n🎤 Qaysi savolga audio yubormoqchisiz?\n"
    text += f"Savol raqamini yozing (1-{len(savollar)}):"

    await state.update_data(task_id=task_id)
    await message.answer(text, reply_markup=ortga_menu())
    await state.set_state(AudioYuborish.savol_raqami)


@dp.message(AudioYuborish.savol_raqami, F.text)
async def audio_savol_raqami(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Asosiy menyu:", reply_markup=oquvchi_menu())
        await state.clear()
        return

    data_user = await state.get_data()
    task_id = data_user.get("task_id")

    if not task_id:
        await message.answer("Xatolik. Qaytadan boshlang.")
        await state.clear()
        return

    try:
        savol_raqami = int(message.text.strip())
    except ValueError:
        await message.answer("Faqat raqam kiriting:")
        return

    data = load_data()
    task = data["tasks"].get(task_id)

    if not task:
        await message.answer("Vazifa topilmadi.")
        await state.clear()
        return

    savollar = task.get("savollar", [])
    if savol_raqami < 1 or savol_raqami > len(savollar):
        await message.answer(f"1 dan {len(savollar)} gacha raqam kiriting:")
        return

    savol = savollar[savol_raqami - 1]
    await state.update_data(savol_raqami=savol_raqami)

    await message.answer(
        f"📌 {savol_raqami}-savol:\n\n"
        f"❓ {savol}\n\n"
        f"🎤 Endi audio javobingizni yuboring:"
    )


@dp.message(AudioYuborish.savol_raqami, F.voice)
async def audio_qabul(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data_user = await state.get_data()
    task_id = data_user.get("task_id")
    savol_raqami = data_user.get("savol_raqami")

    if not task_id or not savol_raqami:
        await message.answer("Xatolik. '📝 Vazifani topshirish' tugmasini bosing.")
        await state.clear()
        return

    data = load_data()
    if task_id not in data["tasks"]:
        await message.answer("Vazifa topilmadi.")
        await state.clear()
        return

    task = data["tasks"][task_id]
    savollar = task.get("savollar", [])
    savol = savollar[savol_raqami - 1]

    await message.answer(f"⏳ {savol_raqami}-savol audio qabul qilindi. AI tahlil qilmoqda...")

    try:
        file = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file.file_path)
        audio_data = file_bytes.read()
    except Exception as e:
        logger.error(f"Audio yuklab olish xatosi: {e}")
        await message.answer("❌ Audio yuklab olishda xatolik.")
        await state.clear()
        return

    ai_tahlil = "⚠️ AI tahlil qila olmadi."
    overall = 0
    try:
        prompt = f"""Sen IELTS Speaking examiner va ingliz tili o'qituvchisisan.
O'quvchi quyidagi savolga javob berdi:

SAVOL: {savol}

Quyidagi audioni TO'LIQ va TABIIY tahlil qil. O'quvchiga do'stona va iliq munosabatda bo'l.
BARCHA IZOHLAR O'ZBEK TILIDA BO'LISHI SHART! Faqat ingliz tilidagi misollar ingliz tilida bo'lsin.

1. 📝 TRANSCRIPT — o'quvchi aytgan gaplarni so'zma-so'z yoz

2. 📊 BAHO — foizda:
🎯 Accuracy: X%
📚 Vocabulary: X%
🗣 Fluency: X%
📖 Grammar: X%
🔊 Pronunciation: X%
⭐ Overall: X%

3. 📝 IZOH — O'ZBEK TILIDA:
✅ Zo'r tomonlaringiz:
- [yaxshi tomonlar]
⚠️ Yaxshilash mumkin:
- [o'rtacha tomonlar]
❌ Bu joylarga e'tibor bering:
- [zaif tomonlar]

4. ❌ GRAMMAR — xato → to'g'ri

5. 📚 VOCABULARY — oddiy → kuchli variantlar

6. 🔗 COLLOCATIONS — to'g'ri/noto'g'ri

7. 📍 PREPOSITIONS — xato → to'g'ri

8. 🗣 FLUENCY — pauzalar, filler words

9. 🧠 CONTENT — javob to'liqligi

10. ✨ IMPROVED VERSION — o'quvchining speaking'ini to'liq yaxshilangan holda qayta yoz (IELTS 8+ darajada)

11. 💡 TAVSIYA — 3-5 ta maslahat

MUHIM: 
- BARCHA IZOHLAR O'ZBEK TILIDA!
- Tabiiy, jonli tilda yoz
- O'quvchiga do'stona munosabatda bo'l
- Xatolarni "yaxshilash mumkin" deb yoz
- Oxirida rag'batlantir
- Markdown belgilar ishlatma
- Overall ni aniq foizda ko'rsat
O'zbek tilida yoz. Qisqa va aniq."""

        tr = groq_client.audio.transcriptions.create(
            file=("audio.ogg", audio_data),
            model="whisper-large-v3-turbo",
        )
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": f"{prompt}\n\nO'quvchi javobi:\n{tr.text}"}],
        )
        ai_tahlil = response.choices[0].message.content

        match = re.search(r'Overall[:\s]+(\d+)', ai_tahlil, re.IGNORECASE)
        if match:
            overall = int(match.group(1))
    except Exception as e:
        logger.error(f"Groq xatosi: {e}")
        ai_tahlil = f"⚠️ AI xatosi: {e}"

    # ==================== BALL HISOBLASH MANTIQI ====================
    # 60%+ -> 1 ball, 50-59% -> 0.5 ball, 50% dan kam -> 0 ball
    if overall >= 60:
        ball = 1.0
    elif overall >= 50:
        ball = 0.5
    else:
        ball = 0.0
    # ================================================================

    if task_id not in data["submissions"]:
        data["submissions"][task_id] = {}
    if user_id not in data["submissions"][task_id]:
        data["submissions"][task_id][user_id] = {"audios": {}}

    data["submissions"][task_id][user_id]["audios"][str(savol_raqami)] = {
        "audio_file_id": message.voice.file_id,
        "submitted_at": now_str(),
        "ai_tahlil": ai_tahlil,
        "overall": overall,
        "ball": ball,
    }

    total_ball = 0
    for a in data["submissions"][task_id][user_id]["audios"].values():
        total_ball += a.get("ball", 0)

    data["submissions"][task_id][user_id]["total_ball"] = total_ball

    # O'quvchining umumiy balliga qo'shish
    if user_id in data["students"]:
        data["students"][user_id]["ball"] = data["students"][user_id].get("ball", 0) + ball

    save_data(data)

    # AI tahlilni o'quvchiga yuborish
    try:
        await message.answer(ai_tahlil)
    except Exception as e:
        logger.error(f"AI tahlil yuborishda xatolik: {e}")
        await message.answer("⚠️ AI tahlilini yuborishda xatolik yuz berdi.")

    # Adminga xabar yuborish
    try:
        student_ism = data["students"].get(user_id, {}).get("ism", "Nomalum")
        await bot.send_message(
            ADMIN_ID,
            f"🎤 YANGI AUDIO TOPSHIRILDI!\n\n"
            f"👤 O'quvchi: {student_ism}\n"
            f"📚 Vazifa: {task['nomi']} (ID: {task_id})\n"
            f"❓ Savol: {savol_raqami}. {savol}\n"
            f"📊 Overall: {overall}%\n"
            f"💰 Berilgan ball: {ball}\n"
            f"🕐 Vaqt: {now_str()}",
        )
    except Exception as e:
        logger.error(f"Adminga xabar yuborishda xatolik: {e}")

    # O'quvchiga qisqa xulosa
    if ball == 1.0:
        xulosa = "✅ Ajoyib! To'liq ball oldingiz."
    elif ball == 0.5:
        xulosa = "⚠️ Yaxshi harakat! Ammo yana ozgina mashq qilish kerak."
    else:
        xulosa = "❌ Javobingiz yetarli emas. Iltimos, yana urinib ko'ring."

    umumiy_ball = data["students"].get(user_id, {}).get("ball", 0)

    await message.answer(
        f"{xulosa}\n\n"
        f"💰 Bu savol uchun ball: {ball}\n"
        f"📊 Umumiy ballingiz: {umumiy_ball}",
        reply_markup=oquvchi_menu(),
    )

    await state.clear()


# ==================== ADMIN: KELGAN JAVOBLAR ====================
@dp.message(F.text == "📥 Kelgan javoblar")
async def kelgan_javoblar(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    data = load_data()
    if not data["submissions"]:
        await message.answer("Hozircha javoblar yo'q.", reply_markup=admin_menu())
        return

    text = "📥 KELGAN JAVOBLAR\n\n"
    for task_id, users in data["submissions"].items():
        task = data["tasks"].get(task_id, {})
        text += f"📚 {task_id}. {task.get('nomi', 'Nomalum')}\n"
        for user_id, sub in users.items():
            student = data["students"].get(user_id, {})
            audios = sub.get("audios", {})
            text += f"   👤 {student.get('ism', 'Nomalum')} — 🎤 {len(audios)} ta audio\n"
        text += "\n"

    text += "Batafsil ma'lumot uchun '📊 Statistika' bo'limiga o'ting."
    await message.answer(text, reply_markup=admin_menu())


# ==================== O'QUVCHI: NATIJAM ====================
@dp.message(F.text == "📊 Natijam")
async def natijam(message: types.Message):
    if is_admin(message.from_user.id):
        return

    data = load_data()
    user_id = str(message.from_user.id)

    if user_id not in data["students"]:
        await message.answer("Avval /start bosing.")
        return

    student = data["students"][user_id]
    text = f"📊 SIZNING NATIJANGIZ\n\n"
    text += f"👤 {student.get('ism')}\n"
    text += f"🏫 {student.get('guruh')}\n"
    text += f"💰 Umumiy ball: {student.get('ball', 0)}\n\n"

    for task_id, task in data["tasks"].items():
        sub = data["submissions"].get(task_id, {}).get(user_id, {})
        audios = sub.get("audios", {})
        if audios:
            savollar_soni = task.get("savollar_soni", 0)
            text += f"📚 {task['nomi']} ({len(audios)}/{savollar_soni}):\n"
            for savol_raqami, audio in audios.items():
                ball = audio.get("ball", 0)
                text += f"   {savol_raqami}-savol: {ball} ball\n"
            text += f"   Jami: {sub.get('total_ball', 0)} ball\n\n"

    await message.answer(text, reply_markup=oquvchi_menu())


# ==================== O'QUVCHI: RANKING ====================
@dp.message(F.text == "🏆 Ranking")
async def ranking(message: types.Message):
    if is_admin(message.from_user.id):
        return

    data = load_data()
    if not data["students"]:
        await message.answer("Hozircha o'quvchilar yo'q.")
        return

    sorted_students = sorted(
        data["students"].items(),
        key=lambda x: x[1].get("ball", 0),
        reverse=True,
    )

    text = "🏆 RANKING\n\n"
    for i, (uid, student) in enumerate(sorted_students, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        text += f"{medal} {i}. {student.get('ism', 'Nomalum')} — {student.get('ball', 0)} ball\n"

    await message.answer(text, reply_markup=oquvchi_menu())


# ==================== O'QUVCHI: PROFILIM ====================
@dp.message(F.text == "👤 Profilim")
async def profilim(message: types.Message):
    if is_admin(message.from_user.id):
        return

    data = load_data()
    user_id = str(message.from_user.id)

    if user_id not in data["students"]:
        await message.answer("Avval /start bosing.")
        return

    student = data["students"][user_id]
    text = f"👤 PROFILINGIZ\n\n"
    text += f"👤 Ism: {student.get('ism')}\n"
    text += f"🏫 Guruh: {student.get('guruh')}\n"
    text += f"📱 Telegram: {student.get('name')}\n"
    text += f"💰 Umumiy ball: {student.get('ball', 0)}\n"
    text += f"📅 Ro'yxatdan o'tgan: {student.get('registered')}\n"

    await message.answer(text, reply_markup=oquvchi_menu())


# ==================== ADMIN: STATISTIKA ====================
@dp.message(F.text == "📊 Statistika")
async def statistika(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    data = load_data()
    text = "📊 STATISTIKA\n\n"
    text += f"👥 O'quvchilar: {len(data['students'])} ta\n"
    text += f"📚 Vazifalar: {len(data['tasks'])} ta\n"
    text += f"📥 Topshirilgan javoblar: {len(data['submissions'])} ta\n\n"

    if data["students"]:
        text += "🏆 TOP 5 O'QUVCHI:\n"
        sorted_students = sorted(
            data["students"].items(),
            key=lambda x: x[1].get("ball", 0),
            reverse=True,
        )[:5]
        for i, (uid, student) in enumerate(sorted_students, 1):
            text += f"{i}. {student.get('ism', 'Nomalum')} — {student.get('ball', 0)} ball\n"

    await message.answer(text, reply_markup=admin_menu())


# ==================== ADMIN: O'QUVCHILAR ====================
@dp.message(F.text == "👥 O'quvchilar")
async def oquvchilar(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    data = load_data()
    if not data["students"]:
        await message.answer("Hozircha o'quvchilar yo'q.", reply_markup=admin_menu())
        return

    text = "👥 O'QUVCHILAR\n\n"
    for uid, student in data["students"].items():
        text += f"🆔 {uid}\n"
        text += f"👤 {student.get('ism')} ({student.get('guruh')})\n"
        text += f"💰 Ball: {student.get('ball', 0)}\n\n"

    await message.answer(text, reply_markup=admin_menu())


# ==================== WEB SERVER ====================
async def handle(request):
    return web.Response(text="Bot ishlayapti!")


async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()

    logger.info("Bot ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
