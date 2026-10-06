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


# ==================== MENYULAR ====================
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
            [KeyboardButton(text="📥 Kelgan javoblar")],
            [KeyboardButton(text="👥 O'quvchilar")],
            [KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="🗑 Vazifani o'chirish")],
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


def tizim_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇬🇧 IELTS")],
            [KeyboardButton(text="🇪🇺 CEFR")],
            [KeyboardButton(text="🔙 Ortga")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
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
                f"Topshirish uchun /submit buyrug'ini bosing.",
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

    if not data["tasks"]:
        await message.answer("📚 Hozircha vazifalar yo'q.")
        return

    text = "📚 VAZIFALAR\n\n"
    for tid, task in data["tasks"].items():
        submitted = data["submissions"].get(tid, {})
        status = "🟢 Yuborilgan" if user_id in submitted else "🔴 Yuborilmagan"
        text += f"{tid}. {task['nomi']}\n   {status}\n   ⏰ {task['deadline']}\n\n"

    text += "Topshirish uchun /submit buyrug'ini bosing."
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


@dp.message(AudioYuborish.vazifa_id, F.text)
async def audio_vazifa_id(message: types.Message, state: FSMContext):
    if message.text == "🔙 Ortga":
        await message.answer("Bekor qilindi.", reply_markup=oquvchi_menu())
        await state.clear()
        return

    task_id = message.text.strip()
    data = load_data()
    user_id = str(message.from_user.id)

    if task_id not in data["tasks"]:
        await message.answer("Bunday vazifa topilmadi. Qaytadan yozing:")
        return

    # KETMA-KETLIKNI TEKSHIRISH
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

    # TIZIMNI SO'RASH
    await message.answer(
        f"✅ Vazifa: {data['tasks'][task_id]['nomi']}\n\n"
        f"📊 Qaysi tizim bo'yicha baholash kerak?",
        reply_markup=tizim_menu(),
    )


@dp.message(F.text == "🇬🇧 IELTS")
async def tizim_ielts(message: types.Message, state: FSMContext):
    if is_admin(message.from_user.id):
        return

    data_user = await state.get_data()
    task_id = data_user.get("task_id")

    if not task_id:
        await message.answer("Avval /submit bosing.")
        await state.clear()
        return

    await state.update_data(tizim="IELTS")
    await message.answer(
        "✅ IELTS tanlandi.\n\n🎤 Endi audio javobingizni yuboring:",
        reply_markup=ortga_menu(),
    )


@dp.message(F.text == "🇪🇺 CEFR")
async def tizim_cefr(message: types.Message, state: FSMContext):
    if is_admin(message.from_user.id):
        return

    data_user = await state.get_data()
    task_id = data_user.get("task_id")

    if not task_id:
        await message.answer("Avval /submit bosing.")
        await state.clear()
        return

    await state.update_data(tizim="CEFR")
    await message.answer(
        "✅ CEFR tanlandi.\n\n🎤 Endi audio javobingizni yuboring:",
        reply_markup=ortga_menu(),
    )


@dp.message(AudioYuborish.vazifa_id, F.voice)
async def audio_qabul(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data_user = await state.get_data()
    task_id = data_user.get("task_id")
    tizim = data_user.get("tizim", "IELTS")

    if not task_id:
        await message.answer("Vazifa tanlanmagan. /submit bosing.")
        await state.clear()
        return

    data = load_data()
    if task_id not in data["tasks"]:
        await message.answer("Vazifa topilmadi.")
        await state.clear()
        return

    task = data["tasks"][task_id]
    await message.answer(f"⏳ Audio qabul qilindi. AI {tizim} bo'yicha tahlil qilmoqda...")

    try:
        file = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file.file_path)
        audio_data = file_bytes.read()
    except Exception as e:
        logger.error(f"Audio yuklab olish xatosi: {e}")
        await message.answer("❌ Audio yuklab olishda xatolik.")
        await state.clear()
        return

    # TIZIMGA QARAB PROMPT
    if tizim == "IELTS":
        prompt = f"""Sen IELTS Speaking examiner san. O'quvchi speaking topshirig'ini bajardi.

SAVOL: {task['savol']}

Quyidagi audioni IELTS Speaking mezonlari bo'yicha tahlil qil:

1. 📝 TRANSCRIPT — o'quvchi aytgan gaplarni so'zma-so'z yoz

2. 📊 BAHO — 0 dan 100 gacha aniq foizda ber:
   - Fluency & Coherence: X%
   - Lexical Resource: X%
   - Grammatical Range & Accuracy: X%
   - Pronunciation: X%
   - Overall: X%

3. 📝 IZOH — nega shunday baho:
   - ✅ Kuchli tomonlar
   - ⚠️ O'rtacha tomonlar
   - ❌ Zaif tomonlar

4. 🗣 FLUENCY & COHERENCE — pauzalar, filler words, mantiqiy bog'lanish

5. 📚 LEXICAL RESOURCE — so'z boyligi, takrorlanish

6. 📖 GRAMMATICAL RANGE — grammatik xilma-xillik, xatolar

7. 🔊 PRONUNCIATION — talaffuz, stress, intonatsiya

8. ✨ IMPROVED VERSION — yaxshilangan to'liq javob (IELTS 8+ darajada)

9. 🎯 TAVSIYA — 3-5 ta maslahat

MUHIM: Markdown belgilar ishlatma. Faqat emoji va oddiy matn.
O'zbek tilida yoz. Qisqa va aniq."""
    else:  # CEFR
        prompt = f"""Sen CEFR bo'yicha ingliz tili o'qituvchisisan. O'quvchi speaking topshirig'ini bajardi.

SAVOL: {task['savol']}

Quyidagi audioni CEFR mezonlari bo'yicha tahlil qil:

1. 📝 TRANSCRIPT — o'quvchi aytgan gaplarni so'zma-so'z yoz

2. 📊 DARAJA — CEFR bo'yicha daraja ber (A1, A2, B1, B2, C1):
   - Overall: X daraja
   - Fluency: X daraja
   - Vocabulary: X daraja
   - Grammar: X daraja
   - Pronunciation: X daraja

3. 📝 IZOH — nega shunday daraja:
   - ✅ Kuchli tomonlar
   - ⚠️ O'rtacha tomonlar
   - ❌ Zaif tomonlar

4. 🗣 FLUENCY — pauzalar, filler words, ravonlik

5. 📚 VOCABULARY — so'z boyligi, takrorlanish

6. 📖 GRAMMAR — grammatik xilma-xillik, xatolar

7. 🔊 PRONUNCIATION — talaffuz, stress, intonatsiya

8. ✨ IMPROVED VERSION — yaxshilangan to'liq javob (C1 darajada)

9. 🎯 TAVSIYA — 3-5 ta maslahat

MUHIM: Markdown belgilar ishlatma. Faqat emoji va oddiy matn.
O'zbek tilida yoz. Qisqa va aniq."""

    ai_tahlil = "⚠️ AI tahlil qila olmadi."
    try:
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
        "tizim": tizim,
    }
    save_data(data)

    ism = data["students"][user_id].get("ism", "Nomalum")
    guruh = data["students"][user_id].get("guruh", "—")

    header = f"🤖 AI SPEAKING TAHLILI ({tizim})\n\n"
    full_text = header + ai_tahlil

    if len(full_text) > 4000:
        for i in range(0, len(full_text), 4000):
            await message.answer(full_text[i:i+4000])
    else:
        await message.answer(full_text)

    try:
        await bot.send_message(
            ADMIN_ID,
            f"📥 YANGI AUDIO!\n\n👤 {ism} ({guruh})\n📚 Vazifa: {task['nomi']}\n📊 Tizim: {tizim}\n⏰ {now_str()}\n\n"
            f"🤖 AI tahlil qildi.",
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
        "✅ Audio va AI tahlil yuborildi!\n\n📌 O'qituvchi tekshirib, ball beradi.",
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
                tizim = sub.get("tizim", "—")
                text += f"👤 {ism} ({guruh})\n📚 {task_name}\n📊 {tizim}\n⏰ {sub.get('submitted_at')}\n\n"
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
    total_subs = sum(len(subs) for subs in data["submissions"].values())

    text = f"📊 STATISTIKA\n\n👥 O'quvchilar: {total_students}\n📚 Vazifalar: {total_tasks}\n📥 Javoblar: {total_subs}\n"
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
        f"👤 Profilingiz:\n\nIsm: {s.get('ism')}\nGuruh: {s.get('guruh')}\n"
        f"Ro'yxatdan o'tgan: {s.get('registered')}"
    )


# ==================== AI SUHBAT ====================
@dp.message(F.text & ~F.text.startswith('/'))
async def ai_suhbat(message: types.Message):
    if is_admin(message.from_user.id):
        return

    tugmalar = [
        "📚 Vazifalar", "📊 Natijam", "🏆 Ranking", "👤 Profilim",
        "📚 Vazifa berish", "📥 Kelgan javoblar", "👥 O'quvchilar", "📊 Statistika",
        "🗑 Vazifani o'chirish", "🇬🇧 IELTS", "🇪🇺 CEFR",
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
        prompt = f"""Sen ingliz tili o'qituvchisisan. O'quvchi senga savol berdi:

SAVOL: {message.text}

Quyidagilarni bajar:

1. 📝 SAVOLGA JAVOB — qisqa va aniq javob ber
2. 💡 IDEALAR — 3-4 ta fikr taklif qil (ingliz tilida)
3. 📚 YANGI SO'ZLAR — 3-5 ta foydali so'z va ibora (tarjimasi bilan)
4. ❓ QO'SHIMCHA SAVOL — o'quvchiga qo'shimcha savol ber (ingliz tilida)
5. ✅ TUSHUNARLI — barchasi oddiy va tushunarli tilda yozilgan

MUHIM: Markdown belgilar ishlatma. Faqat emoji va oddiy matn.
O'zbek tilida yoz. Qisqa va aniq."""

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
            messages=[{"role": "user", "
