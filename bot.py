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
    savol = State()
    deadline = State()
    tasdiqlash = State()


class AudioYuborish(StatesGroup):
    vazifa_id = State()


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


def baho_tugmalari(user_id, task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ 1 ball", callback_data=f"ball_{user_id}_{task_id}_1.0"),
            InlineKeyboardButton(text="⚠️ 0.5 ball", callback_data=f"ball_{user_id}_{task_id}_0.5"),
            InlineKeyboardButton(text="❌ 0 ball", callback_data=f"ball_{user_id}_{task_id}_0.0"),
        ]
    ])


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


# ==================== BAHOLASH CALLBACK ====================
@dp.callback_query(F.data.startswith("ball_"))
async def ball_qoyish(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Siz admin emassiz!")
        return

    parts = callback.data.split("_")
    user_id = parts[1]
    task_id = parts[2]
    ball = float(parts[3])

    data = load_data()

    if task_id not in data["submissions"] or user_id not in data["submissions"][task_id]:
        await callback.answer("Bu javob allaqachon baholangan.")
        return

    sub = data["submissions"][task_id][user_id]
    if sub.get("status") == "evaluated":
        await callback.answer("Bu javob allaqachon baholangan.")
        return

    sub["status"] = "evaluated"
    sub["ball"] = ball
    sub["evaluated_at"] = now_str()

    data["students"][user_id]["ball"] = data["students"][user_id].get("ball", 0) + ball
    save_data(data)

    ism = data["students"][user_id].get("ism", "Nomalum")
    task_nomi = data["tasks"].get(task_id, {}).get("nomi", "Nomalum")
    jami = data["students"][user_id]["ball"]

    try:
        await bot.send_message(
            int(user_id),
            f"🎯 Javobingiz baholandi!\n\n"
            f"📚 Vazifa: {task_nomi}\n"
            f"💰 Ball: {ball}\n"
            f"📊 Umumiy ball: {jami}",
        )
    except Exception as e:
        logger.error(f"O'quvchiga xabar xatosi: {e}")

    try:
        await callback.message.edit_text(
            f"✅ {ism} baholandi!\n\n"
            f"📚 {task_nomi}\n"
            f"💰 Ball: {ball}\n"
            f"📊 Umumiy: {jami}"
        )
    except Exception as e:
        logger.error(f"Xabarni tahrirlash xatosi: {e}")

    await callback.answer(f"Ball: {ball}")


# ==================== ADMIN: VAZIFA BERISH ====================
@dp.message(F.text == "📚 Vazifa berish")
async def vazifa_berish_boshlash(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(tur="asosiy")
    await message.answer("📚 YANGI VAZIFA\n\n1️⃣ Vazifa nomini yozing:", reply_markup=ortga_menu())
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
    await message.answer(f"✅ Nomi: {message.text.strip()}\n\n2️⃣ Speaking savolini yozing:")
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
    await message.answer("✅ Savol qabul qilindi.\n\n3️⃣ Deadline kiriting (masalan: 2026-10-10 20:00):")
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

    data = load_data()
    students_count = len(data["students"])

    text = (
        f"📋 TASDIQLASH\n\n"
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

    data = load_data()
    task_id = str(len(data["tasks"]) + 1)
    data["tasks"][task_id] = {
        "nomi": nomi,
        "savol": savol,
        "deadline": deadline,
        "created": now_str(),
    }
    save_data(data)

    sent = 0
    for uid in data["students"]:
        try:
            await bot.send_message(
                int(uid),
                f"📚 YANGI VAZIFA\n\n📝 {nomi}\n\n❓ {savol}\n\n⏰ Deadline: {deadline}\n\n"
                f"Topshirish uchun '📝 Vazifani topshirish' tugmasini bosing.",
            )
            sent += 1
        except Exception as e:
            logger.error(f"Xabar yuborish xatosi {uid}: {e}")

    await message.answer(f"✅ Vazifa {sent} ta o'quvchiga yuborildi!", reply_markup=admin_menu())
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
        text += f"{tid}. {task['nomi']}\n"

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
        submitted = data["submissions"].get(tid, {})
        if user_id not in submitted:
            tugallanmagan.append((tid, task))

    if not tugallanmagan:
        await message.answer("✅ Sizda tugallanmagan vazifalar yo'q!\n\nBarcha vazifalarni topshirgansiz.")
        return

    text = f"📋 TUGALLANMAGAN VAZIFALAR ({len(tugallanmagan)} ta)\n\n"
    for tid, task in tugallanmagan:
        text += f"📚 {tid}. {task['nomi']}\n"
        text += f"⏰ Deadline: {task['deadline']}\n\n"

    text += "Topshirish uchun '📝 Vazifani topshirish' tugmasini bosing."
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
        submitted = data["submissions"].get(tid, {})
        if user_id in submitted:
            sub = submitted[user_id]
            if sub.get("status") == "evaluated":
                status = f"🟢 {sub.get('ball', 0)} ball"
            else:
                status = "🟡 Tekshirilmoqda"
        else:
            status = "🔴 Yuborilmagan"
        text += f"{tid}. {task['nomi']} — {status}\n"

    text += "\nVazifa raqamini yozing:"
    await message.answer(text)
    await state.set_state(AudioYuborish.vazifa_id)


@dp.message(AudioYuborish.vazifa_id, F.text)
async def audio_vazifa_id(message: types.Message, state: FSMContext):
    tugmalar = [
        "📝 Vazifani topshirish", "📋 Tugallanmagan vazifalar",
        "📊 Natijam", "🏆 Ranking", "👤 Profilim",
        "🔙 Ortga", "✅ Yuborish", "❌ Bekor qilish",
    ]

    if message.text in tugmalar:
        await state.clear()
        if message.text == "📝 Vazifani topshirish":
            await vazifa_topshirish_boshlash(message, state)
        elif message.text == "📋 Tugallanmagan vazifalar":
            await tugallanmagan_vazifalar(message)
        elif message.text == "📊 Natijam":
            await natijam(message)
        elif message.text == "🏆 Ranking":
            await ranking(message)
        elif message.text == "👤 Profilim":
            await profilim(message)
        return

    task_id = message.text.strip()
    data = load_data()
    user_id = str(message.from_user.id)

    if task_id not in data["tasks"]:
        await message.answer("Bunday vazifa topilmadi. Qaytadan yozing:")
        return

    tasks = sorted(data["tasks"].items(), key=lambda x: int(x[0]))
    for tid, task in tasks:
        if tid == task_id:
            break
        subs = data["submissions"].get(tid, {})
        if user_id not in subs:
            await message.answer(
                f"⚠️ Avval {tid}-vazifani bajaring!\n\n"
                f"📝 {task['nomi']}\n\n"
                f"Keyin {task_id}-vazifaga o'tishingiz mumkin."
            )
            return

    await state.update_data(task_id=task_id)
    await message.answer(
        f"✅ Vazifa: {data['tasks'][task_id]['nomi']}\n\n🎤 Endi audio javobingizni yuboring:",
        reply_markup=ortga_menu(),
    )


@dp.message(AudioYuborish.vazifa_id, F.voice)
async def audio_qabul(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data_user = await state.get_data()
    task_id = data_user.get("task_id")

    if not task_id:
        await message.answer("Vazifa tanlanmagan. '📝 Vazifani topshirish' tugmasini bosing.")
        await state.clear()
        return

    data = load_data()
    if task_id not in data["tasks"]:
        await message.answer("Vazifa topilmadi.")
        await state.clear()
        return

    task = data["tasks"][task_id]
    await message.answer("⏳ Audio qabul qilindi. AI tahlil qilmoqda... (30-60 soniya)")

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
    try:
                prompt = f"""Sen IELTS Speaking examiner va ingliz tili o'qituvchisisan.
O'quvchi speaking topshirig'ini bajardi.

SAVOL: {task['savol']}

Quyidagi audioni TO'LIQ va TABIIY tahlil qil. O'quvchiga do'stona va iliq munosabatda bo'l.
O'zbek tilida yoz, lekin misollar ingliz tilida bo'lsin.

1. 📝 TRANSCRIPT — o'quvchi aytgan gaplarni so'zma-so'z yoz

2. 📊 BAHO — foizda:
🎯 Accuracy: X%
📚 Vocabulary: X%
🗣 Fluency: X%
📖 Grammar: X%
🔊 Pronunciation: X%
⭐ Overall: X%

3. 📝 IZOH — quyidagi tarzda:
✅ Zo'r tomonlaringiz:
- [yaxshi tomonlar]
⚠️ Yaxshilash mumkin:
- [o'rtacha tomonlar]
❌ Bu joylarga e'tibor bering:
- [zaif tomonlar]

4. ❌ GRAMMAR — xato → to'g'ri (yumshoq ohangda)

5. 📚 VOCABULARY — oddiy → kuchli variantlar

6. 🔗 COLLOCATIONS — to'g'ri/noto'g'ri

7. 📍 PREPOSITIONS — xato → to'g'ri

8. 🗣 FLUENCY — pauzalar, filler words

9. 🧠 CONTENT — javob to'liqligi

10. ✨ IMPROVED VERSION — o'quvchining speaking'ini to'liq yaxshilangan holda qayta yoz (IELTS 8+ darajada). O'quvchining o'z mazmuni saqlansin, lekin grammatika, vocabulary va ravonlik yaxshilansin.

11. 💡 TAVSIYA — 3-5 ta maslahat

MUHIM:
- Tabiiy, jonli tilda yoz (robot kabi emas)
- O'quvchiga do'stona va samimiy munosabatda bo'l
- "Siz" deb murojaat qil, lekin rasmiy emas, iliq ohangda
- Har bir bo'lim oldiga mos emoji qo'y
- Xatolarni aytganda, "xato" emas, "yaxshilash mumkin" deb yoz
- Maqtashni unutma: "Yaxshi harakat!", "Zo'r!", "Davom eting!" kabi
- Oxirida o'quvchini rag'batlantir
- Markdown belgilar ishlatma. Faqat emoji va oddiy matn.
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
    except Exception as e:
        logger.error(f"Groq xatosi: {e}")
        ai_tahlil = f"⚠️ AI xatosi: {e}"

    if task_id not in data["submissions"]:
        data["submissions"][task_id] = {}

    data["submissions"][task_id][user_id] = {
        "audio_file_id": message.voice.file_id,
        "submitted_at": now_str(),
        "status": "pending",
        "ai_tahlil": ai_tahlil,
    }
    save_data(data)

    ism = data["students"][user_id].get("ism", "Nomalum")
    guruh = data["students"][user_id].get("guruh", "—")

    header = "🤖 AI SPEAKING TAHLILI\n\n"
    full_text = header + ai_tahlil

    if len(full_text) > 4000:
        for i in range(0, len(full_text), 4000):
            await message.answer(full_text[i:i+4000])
    else:
        await message.answer(full_text)

    try:
        await bot.send_message(
            ADMIN_ID,
            f"📥 YANGI AUDIO!\n\n"
            f"👤 {ism} ({guruh})\n"
            f"📚 Vazifa: {task['nomi']}\n"
            f"🆔 {user_id}\n"
            f"⏰ {now_str()}\n\n"
            f"🎯 Baholash:",
            reply_markup=baho_tugmalari(user_id, task_id),
        )
        await bot.send_voice(ADMIN_ID, message.voice.file_id)

        admin_text = f"🤖 AI TAHLIL ({ism}):\n\n{ai_tahlil}"
        if len(admin_text) > 4000:
            for i in range(0, len(admin_text), 4000):
                await bot.send_message(ADMIN_ID, admin_text[i:i+4000])
        else:
            await bot.send_message(ADMIN_ID, admin_text)
    except Exception as e:
        logger.error(f"Admin xabari xatosi: {e}")

    await message.answer(
        "✅ Audio yuborildi!\n\n📌 O'qituvchi baholagandan keyin ball olasiz.",
        reply_markup=oquvchi_menu(),
    )
    await state.clear()


# ==================== ADMIN: KELGAN JAVOBLAR (YANGI) ====================
@dp.message(F.text == "📥 Kelgan javoblar")
async def kelgan_javoblar(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    data = load_data()

    pending_list = []
    evaluated_list = []

    for task_id, subs in data["submissions"].items():
        task_name = data["tasks"].get(task_id, {}).get("nomi", "Nomalum")
        for uid, sub in subs.items():
            student = data["students"].get(uid, {})
            ism = student.get("ism", "Nomalum")
            guruh = student.get("guruh", "—")

            item = {
                "task_id": task_id,
                "task_name": task_name,
                "user_id": uid,
                "ism": ism,
                "guruh": guruh,
                "submitted_at": sub.get("submitted_at", "—"),
                "status": sub.get("status", "pending"),
                "ball": sub.get("ball", 0),
            }

            if sub.get("status") == "pending":
                pending_list.append(item)
            else:
                evaluated_list.append(item)

    if not pending_list and not evaluated_list:
        await message.answer("📥 Hozircha javoblar yo'q.")
        return

    text = "📥 KELGAN JAVOBLAR\n\n"

    if pending_list:
        text += f"⏳ BAHOLANMAGAN ({len(pending_list)} ta):\n\n"
        for item in pending_list:
            text += f"👤 {item['ism']} ({item['guruh']})\n"
            text += f"📚 {item['task_name']}\n"
            text += f"🆔 {item['user_id']}\n"
            text += f"⏰ {item['submitted_at']}\n\n"

    if evaluated_list:
        text += f"\n✅ BAHOLANGAN ({len(evaluated_list)} ta):\n\n"
        for item in evaluated_list:
            text += f"👤 {item['ism']} ({item['guruh']})\n"
            text += f"📚 {item['task_name']}\n"
            text += f"💰 {item['ball']} ball\n\n"

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
        text += f"👤 {info.get('ism')} ({info.get('guruh')})\n💰 {info.get('ball', 0)} ball\n🆔 {uid}\n\n"

    await message.answer(text)


@dp.message(F.text == "📊 Statistika")
async def admin_statistika(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    data = load_data()
    total_students = len(data["students"])
    total_pending = len(data["pending_students"])
    total_tasks = len(data["tasks"])
    total_subs = sum(len(subs) for subs in data["submissions"].values())

    text = (
        f"📊 STATISTIKA\n\n"
        f"👥 O'quvchilar: {total_students}\n"
        f"⏳ Kutilayotgan: {total_pending}\n"
        f"📚 Vazifalar: {total_tasks}\n"
        f"📥 Javoblar: {total_subs}\n"
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
    total_subs = sum(1 for tid, subs in data["submissions"].items() if user_id in subs)

    await message.answer(
        f"📊 Natijangiz:\n\n👤 {s.get('ism')}\n🏫 {s.get('guruh')}\n"
        f"📚 Topshirilgan: {total_subs}\n💰 Ball: {s.get('ball', 0)}"
    )


@dp.message(F.text == "🏆 Ranking")
async def ranking(message: types.Message):
    if is_admin(message.from_user.id):
        return

    data = load_data()
    user_id = str(message.from_user.id)

    if user_id not in data["students"]:
        await message.answer("Avval /start bosing.")
        return

    if not data["students"]:
        await message.answer("🏆 Hozircha o'quvchilar yo'q.")
        return

    sorted_students = sorted(
        data["students"].items(),
        key=lambda x: x[1].get("ball", 0),
        reverse=True
    )

    text = "🏆 RANKING (Top 10)\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for i, (uid, info) in enumerate(sorted_students[:10], 1):
        ism = info.get("ism", "Nomalum")
        guruh = info.get("guruh", "—")
        ball = info.get("ball", 0)
        prefix = medals[i - 1] if i <= 3 else f"{i}️⃣"
        text += f"{prefix} {ism} ({guruh}) — 💰 {ball}\n"

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

    await message.answer(text)


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
        f"👤 Profilingiz:\n\nIsm: {s.get('ism')}\nGuruh: {s.get('guruh')}\n"
        f"Ro'yxatdan o'tgan: {s.get('registered')}\n💰 Ball: {s.get('ball', 0)}"
    )


# ==================== AI SUHBAT ====================
@dp.message(F.text & ~F.text.startswith('/'))
async def ai_suhbat(message: types.Message):
    if is_admin(message.from_user.id):
        return

    tugmalar = [
        "📝 Vazifani topshirish", "📋 Tugallanmagan vazifalar",
        "📊 Natijam", "🏆 Ranking", "👤 Profilim",
        "📚 Vazifa berish", "📥 Kelgan javoblar", "👥 O'quvchilar", "📊 Statistika",
        "🗑 Vazifani o'chirish", "🗑 O'quvchini o'chirish",
        "🔙 Ortga", "✅ Yuborish", "❌ Bekor qilish",
    ]

    if message.text in tugmalar:
        return

    user_id = str(message.from_user.id)
    data = load_data()

    if user_id not in data["students"]:
        return

    if not message.text or len(message.text) < 3:
        return

    await message.answer("🤔 O'ylayapman...")

    try:
        prompt = f"""Sen ingliz tili o'qituvchisisan. O'quvchi senga savol berdi.

SAVOL: {message.text}

Quyidagi TO'LIQ yordamni ber:

1. 📝 TO'LIQ JAVOB
2. 💡 IDEALAR — 4-5 ta fikr (ingliz tilida)
3. 📚 YANGI SO'ZLAR — 5-7 ta (tarjimasi bilan)
4. 🔗 COLLOCATIONS — to'g'ri birikmalar
5. 📝 GRAMMAR — qoidalar
6. ❓ QO'SHIMCHA SAVOLLAR — 2-3 ta
7. 🎯 SAMPLE ANSWER — IELTS 8+ namuna
8. ✅ TUSHUNARLI

MUHIM: Har bo'lim oldiga emoji. Markdown belgilar ishlatma.
O'zbek tilida yoz, misollar ingliz tilida."""

        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": prompt}],
        )
        ai_javob = response.choices[0].message.content

        if len(ai_javob) > 4000:
            for i in range(0, len(ai_javob), 4000):
                await message.answer(ai_javob[i:i+4000])
        else:
            await message.answer(f"🤖 AI JAVOBI:\n\n{ai_javob}")

    except Exception as e:
        logger.error(f"AI suhbat xatosi: {e}")
        await message.answer(f"⚠️ Xatolik: {e}")


# ==================== TEST ====================
@dp.message(Command("test"))
async def test_groq(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": "Salom, sen ishlaysanmi? Qisqa javob ber."}],
        )
        await message.answer(f"✅ Groq ishlayapti:\n\n{response.choices[0].message.content}")
    except Exception as e:
        await message.answer(f"❌ Groq xatosi:\n\n{e}")


# ==================== DEADLINE WARNING (YANGI) ====================
async def deadline_warning():
    """Har daqiqada deadline larni tekshiradi va ogohlantiradi"""
    while True:
        try:
            now = datetime.now()
            data = load_data()

            if "warnings" not in data:
                data["warnings"] = {}

            for tid, task in data["tasks"].items():
                deadline_str = task.get("deadline", "")
                try:
                    deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
                except:
                    continue

                time_left = deadline - now
                hours_left = time_left.total_seconds() / 3600

                warning_times = [
                    (24, "⏰ 24 soat qoldi!"),
                    (12, "⚠️ 12 soat qoldi!"),
                    (6, "🔔 6 soat qoldi!"),
                    (2, "🔴 2 soat qoldi!"),
                    (1, "🚨 1 soat qoldi!"),
                ]

                for warn_hour, warn_text in warning_times:
                    key = f"{tid}_{warn_hour}"
                    if key not in data["warnings"]:
                        if 0 < hours_left <= warn_hour:
                            data["warnings"][key] = True
                            for uid, info in data["students"].items():
                                submitted = data["submissions"].get(tid, {})
                                if uid not in submitted:
                                    try:
                                        await bot.send_message(
                                            int(uid),
                                            f"🔔 {warn_text}\n\n"
                                            f"👤 {info.get('ism', 'o\'quvchi')},\n"
                                            f"📚 Sizda tugallanmagan topshiriq bor:\n\n"
                                            f"📝 {tid}. {task['nomi']}\n"
                                            f"❓ {task['savol']}\n"
                                            f"⏰ Deadline: {task['deadline']}\n\n"
                                            f"⚠️ Iltimos, vaqtida topshiring!",
                                        )
                                    except Exception as e:
                                        logger.error(f"Ogohlantirish xatosi {uid}: {e}")
                            save_data(data)

            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Deadline warning xatosi: {e}")
            await asyncio.sleep(60)


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
    asyncio.create_task(deadline_warning())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
