import os
import re
import asyncio
import json
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
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

DATA_FILE = "data.json"

DEFAULT_DATA = {
    "students": {},
    "pending_students": {},
    "tasks": {},
    "submissions": {},
    "free_audios": {},
}

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ==================== MA'LUMOTLAR ====================
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


def is_student(user_id):
    data = load_data()
    return str(user_id) in data["students"]


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


class VazifaTopshirish(StatesGroup):
    task_tanlash = State()
    savol_tanlash = State()
    audio_kutish = State()


class QoshimchaSpeaking(StatesGroup):
    kutish = State()


# ==================== MENYULAR ====================
def oquvchi_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Vazifa topshirish")],
            [KeyboardButton(text="🎤 Qo'shimcha speaking tashlash")],
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


TUGMA_MATNLARI = {
    "📝 Vazifa topshirish", "🎤 Qo'shimcha speaking tashlash",
    "📊 Natijam", "🏆 Ranking", "👤 Profilim",
    "📚 Vazifa berish", "📥 Kelgan javoblar", "👥 O'quvchilar", "📊 Statistika",
    "🔙 Ortga", "✅ Yuborish", "❌ Bekor qilish",
}


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

    if user_id_str in data["students"]:
        student = data["students"][user_id_str]
        await message.answer(
            f"👋 Salom, {student.get('ism', 'o\'quvchi')}!\n\n"
            f"🏫 Guruh: {student.get('guruh', '—')}\n"
            f"💰 Ball: {student.get('ball', 0)}",
            reply_markup=oquvchi_menu(),
        )
        return

    if user_id_str in data["pending_students"]:
        await message.answer("⏳ So'rovingiz admin tasdiqlashini kutmoqda.")
        return

    await message.answer(
        "👋 Salom! Botdan foydalanish uchun ro'yxatdan o'ting.\n\n"
        "1️⃣ Ism va familiyangizni yozing:\n(Masalan: Shohrux Karimov)"
    )
    await state.set_state(Royxat.ism)


@dp.message(Royxat.ism)
async def royxat_ism(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Ism-familiyangizni matn ko'rinishida yozing:")
        return

    ism = message.text.strip()

    if ism in TUGMA_MATNLARI or ism.startswith("/"):
        await message.answer("❗ Iltimos, ism-familiyangizni matn ko'rinishida yozing:")
        return

    if len(ism) < 3 or len(ism) > 60:
        await message.answer("Ism juda qisqa yoki juda uzun. Qaytadan yozing:")
        return

    await state.update_data(ism=ism)
    await message.answer(f"✅ {ism}\n\n2️⃣ Guruhingizni yozing:\n(Masalan: A1 guruh)")
    await state.set_state(Royxat.guruh)


@dp.message(Royxat.guruh)
async def royxat_guruh(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Guruh nomini matn ko'rinishida yozing:")
        return

    guruh = message.text.strip()

    if guruh in TUGMA_MATNLARI or guruh.startswith("/"):
        await message.answer("❗ Iltimos, guruh nomini matn ko'rinishida yozing:")
        return

    if len(guruh) < 2 or len(guruh) > 40:
        await message.answer("Guruh nomi juda qisqa yoki juda uzun. Qaytadan yozing:")
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
            f"🆕 YANGI SO'ROV!\n\n"
            f"👤 {ism}\n🏫 {guruh}\n"
            f"📱 {message.from_user.full_name}\n🆔 {user_id}\n\nTasdiqlaysizmi?",
            reply_markup=kb,
        )
    except Exception as e:
        logger.error(f"Admin xabari xatosi: {e}")

    await message.answer(
        "⏳ So'rovingiz adminga yuborildi.\nAdmin tasdiqlagach xabar yuboriladi."
    )
    await state.clear()


# ==================== TASDIQLASH / RAD ETISH ====================
@dp.callback_query(F.data.startswith("approve_"))
async def approve_student(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Siz admin emassiz!")
        return

    user_id = callback.data.replace("approve_", "")
    data = load_data()

    if user_id not in data["pending_students"]:
        await callback.answer("Allaqachon tasdiqlangan.")
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
            f"✅ So'rovingiz tasdiqlandi!\n\n"
            f"👤 {student['ism']}\n🏫 {student['guruh']}\n\n"
            f"Endi botdan to'liq foydalanishingiz mumkin:",
            reply_markup=oquvchi_menu(),
        )
    except Exception as e:
        logger.error(f"Xabar xatosi: {e}")

    await callback.message.edit_text(f"✅ TASDIQLANDI: {student['ism']} ({student['guruh']})")
    await callback.answer("Tasdiqlandi!")


@dp.callback_query(F.data.startswith("reject_"))
async def reject_student(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Siz admin emassiz!")
        return

    user_id = callback.data.replace("reject_", "")
    data = load_data()

    if user_id not in data["pending_students"]:
        await callback.answer("Allaqachon tasdiqlangan.")
        return

    student = data["pending_students"][user_id]
    del data["pending_students"][user_id]
    save_data(data)

    try:
        await bot.send_message(int(user_id), "❌ So'rovingiz rad etildi.")
    except Exception as e:
        logger.error(f"Xabar xatosi: {e}")

    await callback.message.edit_text(f"❌ RAD ETILDI: {student['ism']} ({student['guruh']})")
    await callback.answer("Rad etildi!")


# ==================== ADMIN: VAZIFA BERISH ====================
@dp.message(F.text == "📚 Vazifa berish")
async def vazifa_berish_boshlash(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "📚 YANGI VAZIFA\n\n"
        "1️⃣ Vazifa nomini yozing:\n(Masalan: Part 1.1)",
        reply_markup=ortga_menu(),
    )
    await state.set_state(VazifaBerish.nomi)


@dp.message(VazifaBerish.nomi)
async def vazifa_nomi(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Asosiy menyu.", reply_markup=admin_menu())
        await state.clear()
        return
    if not message.text:
        await message.answer("Vazifa nomini yozing:")
        return

    nomi = message.text.strip()
    if len(nomi) < 2:
        await message.answer("Vazifa nomi juda qisqa:")
        return

    await state.update_data(nomi=nomi)
    await message.answer(
        f"✅ Nomi: {nomi}\n\n"
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
        await message.answer("⬅️ Bitta qadam orqaga.\n\n1️⃣ Vazifa nomini qaytadan yozing:")
        await state.set_state(VazifaBerish.nomi)
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
        f"3️⃣ Deadline kiriting:\n(Masalan: 2026-10-15 20:00)"
    )
    await state.set_state(VazifaBerish.deadline)


@dp.message(VazifaBerish.deadline)
async def vazifa_deadline(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("⬅️ Bitta qadam orqaga.\n\n2️⃣ Savollarni qaytadan kiriting:")
        await state.set_state(VazifaBerish.savollar)
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

    text = "📋 TASDIQLASH\n\n"
    text += f"📝 Nomi: {nomi}\n"
    text += f"🔢 Savollar: {len(savollar)} ta\n"
    text += f"⏰ Deadline: {deadline}\n"
    text += f"👥 O'quvchilar: {students_count} ta\n\n"
    text += "❓ Savollar:\n"
    for i, s in enumerate(savollar, 1):
        text += f"{i}. {s}\n"
    text += f"\n💰 Maksimal ball: {len(savollar)}\n\n✅ Tasdiqlaysizmi?"

    await message.answer(text, reply_markup=tasdiqlash_menu())
    await state.set_state(VazifaBerish.tasdiqlash)


@dp.message(VazifaBerish.tasdiqlash)
async def vazifa_tasdiqlash(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
        await state.clear()
        return
    if message.text == "🔙 Ortga":
        await message.answer("⬅️ Bitta qadam orqaga.\n\n3️⃣ Deadline ni qaytadan kiriting:")
        await state.set_state(VazifaBerish.deadline)
        return
    if message.text != "✅ Yuborish":
        await message.answer("Iltimos, ✅ Yuborish yoki ❌ Bekor qilish tugmasini tanlang.")
        return

    data_user = await state.get_data()
    nomi = data_user.get("nomi")
    savollar = data_user.get("savollar", [])
    deadline = data_user.get("deadline")

    data = load_data()
    existing = [int(k) for k in data["tasks"].keys() if k.isdigit()]
    task_id = str(max(existing) + 1) if existing else "1"

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
            text = "📚 YANGI VAZIFA\n\n"
            text += f"📝 Nomi: {nomi}\n"
            text += f"🔢 Savollar: {len(savollar)} ta\n"
            text += f"⏰ Deadline: {deadline}\n\n"
            text += "❓ Savollar:\n"
            for i, s in enumerate(savollar, 1):
                text += f"{i}. {s}\n"
            text += f"\n💰 Maksimal ball: {len(savollar)}\n\n"
            text += "Topshirish uchun '📝 Vazifa topshirish' tugmasini bosing."
            await bot.send_message(int(uid), text)
            sent += 1
        except Exception as e:
            logger.error(f"Xabar xatosi {uid}: {e}")

    await message.answer(
        f"✅ Vazifa {sent} ta o'quvchiga yuborildi!\n💰 Maksimal ball: {len(savollar)}",
        reply_markup=admin_menu(),
    )
    await state.clear()


# ==================== O'QUVCHI: VAZIFA TOPSHIRISH ====================
@dp.message(F.text == "📝 Vazifa topshirish")
async def vazifa_topshirish_boshlash(message: types.Message, state: FSMContext):
    if is_admin(message.from_user.id):
        return
    await state.clear()

    user_id = str(message.from_user.id)
    if not is_student(user_id):
        await message.answer("Avval /start bosing va tasdiqlanishni kuting.")
        return

    data = load_data()
    if not data["tasks"]:
        await message.answer(
            "📚 Hozircha vazifalar yo'q.\n\n"
            "🎤 'Qo'shimcha speaking tashlash' tugmasi orqali audio yuboring — AI tekshiradi."
        )
        return

    # AI javob yo'q — faqat vazifalar ro'yxati
    text = "📋 VAZIFALAR RO'YXATI\n\n"
    for tid, task in sorted(data["tasks"].items(), key=lambda x: int(x[0])):
        sub = data["submissions"].get(tid, {}).get(user_id, {})
        audios = sub.get("audios", {})
        max_b = task.get('savollar_soni', 0)
        text += f"{tid}. {task['nomi']}  🎤 {len(audios)}/{max_b}\n"

    text += "\n━━━━━━━━━━━━━━━\n"
    text += "✍️ Vazifa raqamini yozing:"

    await message.answer(text, reply_markup=ortga_menu())
    await state.set_state(VazifaTopshirish.task_tanlash)


@dp.message(VazifaTopshirish.task_tanlash, F.text)
async def task_tanlash(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Asosiy menyu.", reply_markup=oquvchi_menu())
        await state.clear()
        return

    task_id = message.text.strip()
    data = load_data()
    user_id = str(message.from_user.id)

    if task_id not in data["tasks"]:
        mavjud = ', '.join(sorted(data['tasks'].keys(), key=lambda x: int(x) if x.isdigit() else 0))
        await message.answer(
            f"❌ '{task_id}' raqamli vazifa topilmadi.\n\n"
            f"Mavjud vazifalar: {mavjud}\n\nQaytadan raqam kiriting:"
        )
        return

    task = data["tasks"][task_id]
    savollar = task.get("savollar", [])

    sub = data["submissions"].get(task_id, {}).get(user_id, {})
    audios = sub.get("audios", {})

    text = f"✅ Vazifa: {task['nomi']}\n\n"
    text += f"❓ Savollar ({len(savollar)} ta):\n\n"
    for i, savol in enumerate(savollar, 1):
        status = "🟢 Yuborilgan" if str(i) in audios else "🔴 Yuborilmagan"
        text += f"{i}. {savol}\n   {status}\n\n"

    text += f"🎤 Qaysi savolga audio yubormoqchisiz?\nSavol raqamini yozing (1-{len(savollar)}):"

    await state.update_data(task_id=task_id)
    await message.answer(text, reply_markup=ortga_menu())
    await state.set_state(VazifaTopshirish.savol_tanlash)


@dp.message(VazifaTopshirish.savol_tanlash, F.text)
async def savol_tanlash(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        data = load_data()
        user_id = str(message.from_user.id)
        text = "📋 VAZIFALAR RO'YXATI\n\n"
        for tid, task in sorted(data["tasks"].items(), key=lambda x: int(x[0])):
            sub = data["submissions"].get(tid, {}).get(user_id, {})
            audios = sub.get("audios", {})
            max_b = task.get('savollar_soni', 0)
            text += f"{tid}. {task['nomi']}  🎤 {len(audios)}/{max_b}\n"
        text += "\n✍️ Vazifa raqamini yozing:"
        await message.answer("⬅️ Bitta qadam orqaga.\n\n" + text, reply_markup=ortga_menu())
        await state.set_state(VazifaTopshirish.task_tanlash)
        return

    data_user = await state.get_data()
    task_id = data_user.get("task_id")

    if not task_id:
        await message.answer("Xatolik. '📝 Vazifa topshirish' tugmasini qaytadan bosing.")
        await state.clear()
        return

    try:
        savol_raqami = int(message.text.strip())
    except ValueError:
        await message.answer("Iltimos, faqat raqam kiriting (masalan: 1, 2, 3...):")
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
        f"🎤 Endi audio javobingizni yuboring:\n\n"
        f"ℹ️ Xohlagancha qayta yuborishingiz mumkin."
    )
    await state.set_state(VazifaTopshirish.audio_kutish)


@dp.message(VazifaTopshirish.audio_kutish, F.text)
async def audio_kutish_text(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        data_user = await state.get_data()
        task_id = data_user.get("task_id")
        data = load_data()
        user_id = str(message.from_user.id)

        if task_id and task_id in data["tasks"]:
            task = data["tasks"][task_id]
            savollar = task.get("savollar", [])
            sub = data["submissions"].get(task_id, {}).get(user_id, {})
            audios = sub.get("audios", {})

            text = f"✅ Vazifa: {task['nomi']}\n\n"
            text += f"❓ Savollar ({len(savollar)} ta):\n\n"
            for i, savol in enumerate(savollar, 1):
                status = "🟢 Yuborilgan" if str(i) in audios else "🔴 Yuborilmagan"
                text += f"{i}. {savol}\n   {status}\n\n"
            text += f"🎤 Savol raqamini yozing (1-{len(savollar)}):"

            await message.answer("⬅️ Bitta qadam orqaga.\n\n" + text, reply_markup=ortga_menu())
            await state.set_state(VazifaTopshirish.savol_tanlash)
            return

        await message.answer("Asosiy menyu.", reply_markup=oquvchi_menu())
        await state.clear()
        return

    await message.answer("🎤 Iltimos, audio (voice) yuboring yoki 🔙 Ortga bosing.")


@dp.message(VazifaTopshirish.audio_kutish, F.voice)
async def audio_vazifa_qabul(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data_user = await state.get_data()
    task_id = data_user.get("task_id")
    savol_raqami = data_user.get("savol_raqami")

    if not task_id or not savol_raqami:
        await message.answer("Xatolik. '📝 Vazifa topshirish' tugmasini qaytadan bosing.")
        await state.clear()
        return

    data = load_data()
    task = data["tasks"].get(task_id)
    if not task:
        await message.answer("Vazifa topilmadi.")
        await state.clear()
        return

    savollar = task.get("savollar", [])
    if savol_raqami < 1 or savol_raqami > len(savollar):
        await message.answer("Savol raqami xato.")
        await state.clear()
        return

    savol = savollar[savol_raqami - 1]
    await process_audio(message, state, task_id, savol_raqami, savol, task)


# ==================== QO'SHIMCHA SPEAKING TASHLASH ====================
@dp.message(F.text == "🎤 Qo'shimcha speaking tashlash")
async def qoshimcha_speaking_boshlash(message: types.Message, state: FSMContext):
    if is_admin(message.from_user.id):
        return
    await state.clear()

    user_id = str(message.from_user.id)
    if not is_student(user_id):
        await message.answer("Avval /start bosing va tasdiqlanishni kuting.")
        return

    await message.answer(
        "🎤 QO'SHIMCHA SPEAKING TASHLASH\n\n"
        "Xohlagan mavzuda yoki erkin savolga javob yuboring.\n"
        "AI tahlil qiladi va foizda baho beradi.\n\n"
        "🎤 Audioni yuboring:",
        reply_markup=ortga_menu(),
    )
    await state.set_state(QoshimchaSpeaking.kutish)


@dp.message(QoshimchaSpeaking.kutish, F.text)
async def qoshimcha_speaking_text(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Asosiy menyu.", reply_markup=oquvchi_menu())
        await state.clear()
        return
    await message.answer("🎤 Iltimos, audio (voice) yuboring:")


@dp.message(QoshimchaSpeaking.kutish, F.voice)
async def qoshimcha_speaking_qabul(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if not is_student(user_id):
        await message.answer("Avval /start bosing.")
        await state.clear()
        return

    savol = "Qo'shimcha speaking (savolsiz)"
    await process_audio(message, state, None, None, savol, None)


# ==================== ASOSIY AUDIO QAYTA ISHLASH ====================
async def process_audio(message, state, task_id, savol_raqami, savol, task):
    user_id = str(message.from_user.id)
    data = load_data()

    if savol_raqami:
        await message.answer(f"⏳ {savol_raqami}-savol audio qabul qilindi. AI tahlil qilmoqda...")
    else:
        await message.answer("⏳ Audio qabul qilindi. AI tahlil qilmoqda...")

    try:
        file = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file.file_path)
        audio_data = file_bytes.read()
    except Exception as e:
        logger.error(f"Audio yuklash xatosi: {e}")
        await message.answer("❌ Audio yuklab olishda xatolik. Qayta urinib ko'ring.")
        return

    ai_tahlil = "⚠️ AI tahlil qila olmadi."
    overall = 0
    try:
        prompt = f"""Sen IELTS Speaking examiner va ingliz tili o'qituvchisisan.
O'quvchi quyidagi savolga javob berdi:

SAVOL: {savol}

Audioni TO'LIQ va TABIIY tahlil qil. O'quvchiga do'stona munosabatda bo'l.
BARCHA IZOHLAR O'ZBEK TILIDA BO'LISHI SHART! Faqat ingliz tilidagi misollar ingliz tilida bo'lsin.

1. 📝 TRANSCRIPT — o'quvchi aytgan gaplarni so'zma-so'z yoz

2. 📊 BAHO — foizda (FAQAT raqam yoz, % belgisisiz):
🎯 Accuracy: X
📚 Vocabulary: X
🗣 Fluency: X
📖 Grammar: X
🔊 Pronunciation: X
⭐ Overall: X

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

10. 💡 TAVSIYA — 3-5 ta maslahat

MUHIM:
- BARCHA IZOHLAR O'ZBEK TILIDA!
- Tabiiy, jonli tilda yoz
- Xatolarni "yaxshilash mumkin" deb yoz
- Oxirida rag'batlantir
- Markdown belgilar ishlatma
- Overall ni aniq raqamda ko'rsat (masalan: ⭐ Overall: 72)"""

        tr = groq_client.audio.transcriptions.create(
            file=("audio.ogg", audio_data),
            model="whisper-large-v3-turbo",
        )
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"{prompt}\n\nO'quvchi javobi:\n{tr.text}"}],
        )
        ai_tahlil = response.choices[0].message.content

        match = re.search(r'Overall[\s:]*(\d{1,3})', ai_tahlil, re.IGNORECASE)
        if match:
            overall = int(match.group(1))
            if overall > 100:
                overall = 100
        else:
            nums = re.findall(r'(\d{1,3})\s*%?', ai_tahlil)
            nums = [int(n) for n in nums if 0 <= int(n) <= 100]
            if nums:
                overall = sum(nums[:5]) // min(5, len(nums))
    except Exception as e:
        logger.error(f"Groq xatosi: {e}")
        ai_tahlil = "⚠️ AI tahlil qilishda xatolik. Keyinroq qayta urinib ko'ring."

    if overall >= 60:
        ball = 1.0
    elif overall >= 50:
        ball = 0.5
    else:
        ball = 0.0

    if task_id is not None:
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
            "savol": savol,
        }

        total_ball = sum(
            a.get("ball", 0)
            for a in data["submissions"][task_id][user_id]["audios"].values()
        )
        data["submissions"][task_id][user_id]["total_ball"] = total_ball
        if user_id in data["students"]:
            data["students"][user_id]["ball"] = total_ball
    else:
        if user_id not in data["free_audios"]:
            data["free_audios"][user_id] = {}
        eid = str(len(data["free_audios"][user_id]) + 1)
        data["free_audios"][user_id][eid] = {
            "audio_file_id": message.voice.file_id,
            "submitted_at": now_str(),
            "ai_tahlil": ai_tahlil,
            "overall": overall,
            "ball": ball,
        }

    save_data(data)

    ism = data["students"][user_id].get("ism", "Nomalum")
    guruh = data["students"][user_id].get("guruh", "—")

    header = "🤖 AI TAHLIL\n\n"
    if savol_raqami:
        header = f"🤖 AI TAHLIL — {savol_raqami}-savol\n\n"
    full_text = header + ai_tahlil
    full_text += "\n\n━━━━━━━━━━━━━━━\n"
    full_text += f"📊 UMUMIY BAHO: {overall}%"
    if task_id is not None:
        full_text += f"\n🎯 Bu audio uchun ball: {ball}"
        full_text += f"\n💰 Vazifadagi jami: {data['submissions'][task_id][user_id].get('total_ball', 0)}/{task.get('savollar_soni', 0)}"

    if len(full_text) > 4000:
        for i in range(0, len(full_text), 4000):
            await message.answer(full_text[i:i+4000])
    else:
        await message.answer(full_text)

    if task_id is not None:
        await message.answer(
            f"✅ {savol_raqami}-savol topshirildi!\n\n"
            f"🎤 Boshqa savolga audio tashlang yoki qayta yuboring.",
            reply_markup=oquvchi_menu(),
        )
    else:
        await message.answer(
            "✅ Audio tahlil qilindi!\n\n🎤 Yana audio yuborishingiz mumkin.",
            reply_markup=oquvchi_menu(),
        )

    try:
        if task_id is not None:
            task_name = task['nomi'] if task else "—"
            info = f"📚 {task_name} — {savol_raqami}-savol"
        else:
            info = "🎤 Qo'shimcha speaking"

        await bot.send_message(
            ADMIN_ID,
            f"📥 YANGI AUDIO!\n\n"
            f"👤 {ism} ({guruh})\n"
            f"{info}\n"
            f"⏰ {now_str()}\n"
            f"📊 Overall: {overall}% | Ball: {ball}",
        )
        await bot.send_voice(ADMIN_ID, message.voice.file_id)
    except Exception as e:
        logger.error(f"Admin xabari xatosi: {e}")


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

    for task_id in sorted(data["submissions"].keys(), key=lambda x: int(x) if x.isdigit() else 0):
        subs = data["submissions"][task_id]
        task_name = data["tasks"].get(task_id, {}).get("nomi", "Nomalum")
        max_ball = data["tasks"].get(task_id, {}).get("savollar_soni", 0)
        for uid, sub in subs.items():
            audios = sub.get("audios", {})
            if not audios:
                continue
            student = data["students"].get(uid, {})
            ism = student.get("ism", "Nomalum")
            guruh = student.get("guruh", "—")
            total = sub.get("total_ball", 0)
            text += f"👤 {ism} ({guruh})\n"
            text += f"📚 {task_name}\n"
            text += f"🎤 {len(audios)}/{max_ball} audio\n"
            text += f"💰 {total}/{max_ball} ball\n\n"
            count += 1

    if count == 0:
        text += "Hozircha javoblar yo'q."

    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i+4000])
    else:
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
        text += f"👤 {info.get('ism')} ({info.get('guruh')}) — 💰 {info.get('ball', 0)}\n"

    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i+4000])
    else:
        await message.answer(text)


@dp.message(F.text == "📊 Statistika")
async def admin_statistika(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    data = load_data()
    total_students = len(data["students"])
    total_pending = len(data["pending_students"])
    total_tasks = len(data["tasks"])
    total_audios = sum(
        len(sub.get("audios", {}))
        for subs in data["submissions"].values()
        for sub in subs.values()
    )
    free_audios = sum(len(v) for v in data.get("free_audios", {}).values())

    text = (
        f"📊 STATISTIKA\n\n"
        f"👥 O'quvchilar: {total_students}\n"
        f"⏳ Kutilayotgan: {total_pending}\n"
        f"📚 Vazifalar: {total_tasks}\n"
        f"🎤 Vazifa audiolari: {total_audios}\n"
        f"🎤 Qo'shimcha speaking: {free_audios}\n"
    )
    await message.answer(text)


# ==================== O'QUVCHI: NATIJA, RANKING, PROFIL ====================
@dp.message(F.text == "📊 Natijam")
async def natijam(message: types.Message, state: FSMContext):
    await state.clear()
    if is_admin(message.from_user.id):
        return
    user_id = str(message.from_user.id)
    data = load_data()

    if user_id not in data["students"]:
        await message.answer("Avval /start bosing.")
        return

    s = data["students"][user_id]
    text = "📊 NATIJANGIZ\n\n"
    text += f"👤 {s.get('ism')}\n"
    text += f"🏫 {s.get('guruh')}\n\n"

    has_results = False
    for tid in sorted(data["tasks"].keys(), key=lambda x: int(x) if x.isdigit() else 0):
        task = data["tasks"][tid]
        sub = data["submissions"].get(tid, {}).get(user_id, {})
        audios = sub.get("audios", {})
        max_b = task.get("savollar_soni", 0)
        total = sub.get("total_ball", 0)
        if audios:
            text += f"📚 {task['nomi']}: {total}/{max_b} ball ({len(audios)} audio)\n"
            has_results = True

    if not has_results:
        text += "Hozircha natijalar yo'q.\n"

    free_count = len(data.get("free_audios", {}).get(user_id, {}))
    if free_count:
        text += f"\n🎤 Qo'shimcha speaking: {free_count} ta\n"

    text += f"\n💰 UMUMIY BALL: {s.get('ball', 0)}"
    await message.answer(text, reply_markup=oquvchi_menu())


@dp.message(F.text == "🏆 Ranking")
async def ranking(message: types.Message, state: FSMContext):
    await state.clear()
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

    text = "🏆 RANKING (Top 10)\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, info) in enumerate(sorted_students[:10], 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        text += f"{medal} {info.get('ism')} ({info.get('guruh')}) — 💰 {info.get('ball', 0)}\n"

    user_id = str(message.from_user.id)
    user_rank = None
    for i, (uid, info) in enumerate(sorted_students, 1):
        if uid == user_id:
            user_rank = i
            break

    if user_rank:
        user_ball = data["students"][user_id].get("ball", 0)
        text += f"\n━━━━━━━━━━━━━━━\n"
        text += f"📊 Sizning o'rningiz: #{user_rank}\n"
        text += f"💰 Sizning ballingiz: {user_ball}\n"
        text += f"👥 Jami o'quvchilar: {len(data['students'])}\n"

    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i+4000])
    else:
        await message.answer(text, reply_markup=oquvchi_menu())


@dp.message(F.text == "👤 Profilim")
async def profilim(message: types.Message, state: FSMContext):
    await state.clear()
    if is_admin(message.from_user.id):
        return
    user_id = str(message.from_user.id)
    data = load_data()
    if user_id not in data["students"]:
        await message.answer("Avval /start bosing.")
        return
    s = data["students"][user_id]
    await message.answer(
        f"👤 PROFILINGIZ\n\n"
        f"Ism: {s.get('ism')}\n"
        f"Guruh: {s.get('guruh')}\n"
        f"Ro'yxatdan o'tgan: {s.get('registered')}\n"
        f"💰 Umumiy ball: {s.get('ball', 0)}",
        reply_markup=oquvchi_menu(),
    )


# ==================== TEST ====================
@dp.message(Command("test"))
async def test_groq(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Salom, sen ishlaysanmi? Qisqa javob ber."}],
        )
        await message.answer(f"✅ Groq ishlayapti:\n\n{response.choices[0].message.content}")
    except Exception as e:
        await message.answer(f"❌ Groq xatosi:\n\n{e}")


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
