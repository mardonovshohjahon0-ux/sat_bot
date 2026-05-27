import asyncio
import sqlite3
import logging
from collections import defaultdict
import time
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import *
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiogram.types.error_event import ErrorEvent

load_dotenv()

import os
ADMIN_ID = 1647176037
import os

TOKEN = os.environ["TOKEN"]


logging.basicConfig(
    level=logging.INFO,
    filename="bot.log",
    format="%(asctime)s - %(levelname)s - %(message)s"
)


bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ---------------- DATABASE ----------------

conn = sqlite3.connect(
    "sat.db",
    check_same_thread=False,
    timeout=30
)
cursor = conn.cursor()
db_lock = asyncio.Lock()

conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")



cursor.execute("""
CREATE TABLE IF NOT EXISTS section_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER,
    question_number INTEGER,
    correct_answer TEXT,
    score INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    time_limit INTEGER,
    mode TEXT,
    file_id TEXT,
    file_type TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS section_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT,
    source TEXT,
    practice TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    section_id INTEGER,
    question_number INTEGER,
    user_answer TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    age TEXT,
    username TEXT,
    language TEXT DEFAULT 'uz'
)
""")


cursor.execute("""
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER,
    photo TEXT,
    type TEXT,
    options TEXT,
    answer TEXT,
    score INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    section_id INTEGER,
    correct INTEGER,
    wrong INTEGER,
    score INTEGER,
    mode TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_results_user
ON results(user_id)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_results_section
ON results(section_id)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_answers_user
ON user_answers(user_id)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bans (
    user_id INTEGER PRIMARY KEY,
    reason TEXT,
    banned_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS help_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    message TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_user_answers_combo
ON user_answers(user_id, section_id)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_section_answers_combo
ON section_answers(section_id)
""")

try:
    cursor.execute("""
    ALTER TABLE sections
    ADD COLUMN category_id INTEGER
    """)
except:
    pass

conn.commit()

# ---------------- DATA ----------------
callback_tracker = defaultdict(list)

async def anti_spam(message: Message):

    user_id = message.from_user.id

    if user_id == ADMIN_ID:
        return False

    now = time.time()

    spam_tracker[user_id] = [
        t for t in spam_tracker[user_id]
        if now - t < 5
    ]

    spam_tracker[user_id].append(now)

    # 5 sekund ichida 6+ message
    if len(spam_tracker[user_id]) >= 6:

        temp_bans[user_id] = (
            datetime.now() + timedelta(minutes=3)
        )

        await message.answer(
            tr(user_id, "spam_block_3m")
        )

        return True

    return False


async def callback_spam_check(callback: CallbackQuery):

    user_id = callback.from_user.id

    if user_id == ADMIN_ID:
        return True

    now = time.time()

    callback_tracker[user_id] = [
        t for t in callback_tracker[user_id]
        if now - t < 3
    ]

    callback_tracker[user_id].append(now)

    # 3 sekund ichida 8+ bosish
    if len(callback_tracker[user_id]) >= 8:

        await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

        return False

    return True


request_tracker = defaultdict(list)
spam_tracker = defaultdict(list)
temp_bans = {}

LIMIT = 7
WINDOW = 5
BAN_MINUTES = 5

async def check_flood(user_id):

    if user_id == ADMIN_ID:
        return False

    # temp ban check
    if user_id in temp_bans:

        if datetime.now() < temp_bans[user_id]:
            return True

        del temp_bans[user_id]

    now = time.time()

    # eski requestlarni tozalash
    request_tracker[user_id] = [
        t for t in request_tracker[user_id]
        if now - t < WINDOW
    ]

    request_tracker[user_id].append(now)

    # limit
    if len(request_tracker[user_id]) >= LIMIT:

        temp_bans[user_id] = (
            datetime.now() + timedelta(minutes=BAN_MINUTES)
        )

        request_tracker[user_id].clear()

        return True

    return False


processing_users = set()

async def is_banned(user_id):

    cursor.execute(
        "SELECT * FROM bans WHERE user_id=?",
        (user_id,)
    )

    return cursor.fetchone()
sessions = {}
temp = {}




# ---------------- MENUS ----------------
LANGS = {
    "uz": {
        "choose_1_2": "1 yoki 2 yuboring",
        "welcome": "Xush kelibsiz!",
        "choose_lang": "Tilni tanlang:",
        "enter_name": "Ismingizni kiriting:",
        "enter_age": "Yoshingizni kiriting:",
        "registered": "✅ Ro‘yxatdan o‘tdingiz!",
        "sections": "📚 Testni boshlash",
        "results": "📊 Natijalar",
        "profile": "⚙️ Profile",
        "help": "🆘 Yordam",
        "saved": "✅ Javob saqlandi",
        "time_up": "⛔ Vaqt tugadi",
        "finish": "✅ Finish",
        "users": "👥 Foydalanuvchilar",
        "leaderboard": "🏆 Leaderboard",
        "add_section": "➕ Bo'lim qo'shish",
        "edit_section": "✏️ Bo'limni o'zgartirish",
        "upload_file": "📥 File yuklash",
        "help_messages": "🆘 Adminga habarlar",
        "spam_ban": "⛔ Juda ko‘p so‘rov yubordingiz",
        "long_msg": "❗ Xabar juda uzun",
        "session_not_found": "❗ Session topilmadi",
        "section_not_found": "❗ Bo'lim topilmadi",
        "choose_section": "📚 Bo'lim tanlang",
        "test_started": "📝 Test boshlandi",
        "choose_mode": "Test turini tanlang",
        "with_time": "⏱ Vaqt bilan",
        "without_time": "♾ Vaqtsiz",
        "welcome_back": "Qaytganingiz bilan!",
        "new_name": "Yangi ism kiriting",
        "section_name": "Bo'lim nomi:",
        "admin_panel": "👑 Admin panel",
        "rename": "✏️ Ismni o'zgartirish",
        "delete_section": "🗑 Bo'limni o'chirish",
        "choose": "Tanlang:",
        "deleted": "O‘chirildi",
        "changed": "O‘zgartirildi",
        "section_added": "Bo'lim qo‘shildi!",
        "time_input": "Vaqt (minut):",
        "numbers_only": "Faqat raqam kiriting",
        "choose_mode_admin": "1: vaqt bilan\n2: Vaqt bilan/Vaqtsiz",
        "file_upload_choose": "Qaysi bo'limga file yuklaysiz?",
        "no_sections": "❗ Bo'lim yo‘q",
        "send_file": "📄 File yuboring",
        "file_received": "✅ File qabul qilindi.\n\nEndi javob yozing:\n1-A-10",
        "answers_saved": "✅ Javoblar va ballar saqlandi",
        "users_list": "Foydalanuvchilar:",
        "leaderboard_choose": "🏆 Leaderboard uchun bo'lim tanlang:",
        "results_not_found": "❗ Natijalar yo‘q",
        "user_not_found": "Foydalanuvchi topilmadi",
        "section_select": "Bo'limni tanlang:",
        "no_results": "❗ Bu bo'lim bo‘yicha natijalar yo‘q",
        "help_no": "❗ Adminga habarlar yo'q",
        "help_messages_title": "🆘 Adminga habarlar:\n\n",
        "language_changed": "✅ Til o‘zgartirildi",
        "name_updated": "✅ Ism yangilandi",
        "age_updated": "✅ Yosh yangilandi",
        "new_age": "Yangi yosh:",
        "no_sections_exist": "❗ Bo'limlar mavjud emas",
        "finish_old_test": "❗ Oldingi testni tugating",
        "choose_test_type": "Test turini tanlang:",
        "profile_info": "👤 Profil:",
        "not_registered": "❗ Siz ro‘yxatdan o‘tmagansiz",
        "message_sent_admin": "✅ Xabaringiz adminga yuborildi",
        "send_help_message": "✍️ Adminga yubormoqchi bo‘lgan xabaringizni yozing",
        "admin_cannot_help": "❗ Admin help yubora olmaydi",
        "answers_saved_user": "✅ Javob saqlandi. O‘zgartirmoqchi bo‘lsangiz qayta yuboring. Tugatmoqchi bo'lsangiz Finish tugmasini bosing",
        "no_user_results": "❗ Sizda hali result yo‘q",
        "user_results": "📊 Sizning natijalaringiz:\n\n",
        "test_started_text": "📝 Test boshlandi!\n\nJavob format:\n1-A\n2-B\n3-C",
        "time_left": "⏳ Qolgan vaqt:",
        "edit_name": "✏️ Ismni o'zgartirish",
        "edit_age": "🎂 Yoshni o'zgartirish",
        "change_language": "🌐 Tilni o'zgartirish",
        "flood_ban": "⛔ Juda ko‘p request yubordingiz.\n5 minut block.",
        "flood_callback": "⛔ Bloklangansiz",
        "session_not_found": "❗ Session topilmadi",
        "no_users": "❗ Foydalanuvchilar yo‘q",
        "sections_not_found": "❗ Sectionlar yo‘q",
        "profile_name": "Ism",
        "profile_age": "Yosh",
        "section_missing": "❗ Bo'lim topilmadi",
        "leaderboard_title": "Leaderboard",
        "correct": "To‘g‘ri",
        "wrong": "Xato",
        "score": "Ball",
        "user_info": "Foydalanuvchi ma'lumoti",
        "attempt": "Urinish",
        "mode": "Rejim",
        "date": "Sana",
        "no_answer": "Javob yo'q",
        "banned": "⛔ Siz botdan ban olgansiz",
        "choose_lang_text": "Tilni tanlang",
        "temporary_block": "⛔ Siz vaqtincha bloklangansiz",
        "spam_block_3m": "⛔ Juda ko‘p so‘rov yubordingiz.\n3 minutga bloklandingiz.",
        "message_too_long": "❗ Xabar juda uzun",
        "section_not_found_simple": "❗ Section topilmadi",
        "sections_empty": "❗ Sectionlar yo‘q",
        "user_label": "Foydalanuvchi",
        "name_label": "Ism",
        "age_label": "Yosh",
        "not_exists": "yo‘q",
        "attempt_label": "Urinish",
        "mode_label": "Rejim",
        "results_title": "📊 Natijalar",
        "no_answer_text": "javob yo‘q",
        "add_source": "➕ Source qo'shish",
        "add_practice": "➕ Practice qo'shish",
        "add_test": "➕ Test qo'shish",
        
        "select_subject": "📚 Subject tanlang:",
        "select_source": "📂 Source tanlang:",
        "select_practice": "📝 Practice tanlang:",
        "select_test": "📄 Test tanlang:",
        
        "enter_source_name": "Source nomini kiriting:",
        "enter_practice_name": "Practice nomini kiriting:",
        
        "source_added": "✅ Source qo'shildi",
        "practice_added": "✅ Practice qo'shildi",
        
        "step_subject": "1️⃣ Subject tanlang:",
        "step_source": "2️⃣ Source tanlang:",
        "step_practice": "3️⃣ Practice tanlang:",
        "step_test": "4️⃣ Test tanlang:",
        
        "english_subject": "English",
        "math_subject": "Math",
        
        "no_practices": "❗ Practicelar topilmadi",
        "no_tests": "❗ Testlar topilmadi",
        "no_sources": "❗ Sourcelar topilmadi",
        "edit_menu": "✏️ Tahrirlash",
        "edit_source": "📚 Source tahrirlash",
        "edit_practice": "📝 Practice tahrirlash",
        "edit_test": "📄 Test tahrirlash",
        "choose_source": "Source tanlang",
        "choose_practice": "Practice tanlang",
        "choose_test": "Test tanlang",
                
    },

    "ru": {
        "choose_1_2": "Отправьте 1 или 2",
        "welcome": "Добро пожаловать!",
        "choose_lang": "Выберите язык:",
        "enter_name": "Введите имя:",
        "enter_age": "Введите возраст:",
        "registered": "✅ Вы зарегистрированы!",
        "sections": "📚 Разделы",
        "results": "📊 Результаты",
        "profile": "⚙️ Профиль",
        "help": "🆘 Помощь",
        "saved": "✅ Ответ сохранён",
        "time_up": "⛔ Время вышло",
        "finish": "✅ Завершить",
        "users": "👥 Пользователи",
        "leaderboard": "🏆 Таблица лидеров",
        "add_section": "➕ Добавить раздел",
        "edit_section": "✏️ Изменить раздел",
        "upload_file": "📥 Загрузить файл",
        "help_messages": "🆘 Сообщения помощи",
        "spam_ban": "⛔ Слишком много запросов",
        "long_msg": "❗ Сообщение слишком длинное",
        "session_not_found": "❗ Сессия не найдена",
        "section_not_found": "❗ Раздел не найден",
        "choose_section": "📚 Выберите раздел",
        "test_started": "📝 Тест начался",
        "choose_mode": "Выберите режим теста",
        "with_time": "⏱ Со временем",
        "without_time": "♾ Без времени",
        "welcome_back": "Добро пожаловать!",
        "new_name": "введите новое имя",
        "section_name": "Название раздела:",
        "admin_panel": "👑 Админ панель",
        "rename": "✏️ Переименовать",
        "delete_section": "🗑 Удалить раздел",
        "choose": "Выберите:",
        "deleted": "Удалено",
        "changed": "Изменено",
        "section_added": "Раздел добавлен!",
        "time_input": "Время (минуты):",
        "numbers_only": "Введите только число",
        "choose_mode_admin": "1: со временем\n2: с/без времени",
        "file_upload_choose": "В какой раздел загрузить файл?",
        "no_sections": "❗ Разделов нет",
        "send_file": "📄 Отправьте файл",
        "file_received": "✅ Файл получен.\n\nТеперь отправьте ответы:\n1-A-10",
        "answers_saved": "✅ Ответы и баллы сохранены",
        "users_list": "Пользователи:",
        "leaderboard_choose": "🏆 Выберите раздел для leaderboard:",
        "results_not_found": "❗ Результатов нет",
        "user_not_found": "Пользователь не найден",
        "section_select": "Выберите раздел:",
        "no_results": "❗ Нет результатов по этому разделу",
        "help_no": "❗ Нет help сообщений",
        "help_messages_title": "🆘 Справочные сообщения:\n\n",
        "language_changed": "✅ Язык изменён",
        "name_updated": "✅ Имя обновлено",
        "age_updated": "✅ Возраст обновлён",
        "new_age": "Введите новый возраст:",
        "no_sections_exist": "❗ Разделы отсутствуют",
        "finish_old_test": "❗ Сначала завершите предыдущий тест",
        "choose_test_type": "Выберите тип теста:",
        "profile_info": "👤 Профиль:",
        "not_registered": "❗ Вы не зарегистрированы",
        "message_sent_admin": "✅ Сообщение отправлено администратору",
        "send_help_message": "✍️ Напишите сообщение администратору",
        "admin_cannot_help": "❗ Администратор не может отправлять help",
        "answers_saved_user": "✅ Ответ сохранён. Если хотите изменить, отправьте заново. Чтобы завершить тест, нажмите кнопку завершить.",
        "no_user_results": "❗ У вас пока нет результатов",
        "user_results": "📊 Ваши результаты:\n\n",
        "test_started_text": "📝 Тест начался!\n\nФормат ответа:\n1-A\n2-B\n3-C",
        "time_left": "⏳ Осталось времени:",
        "edit_name": "✏️ Изменить имя",
        "edit_age": "🎂 Изменить возраст",
        "change_language": "🌐 Изменить язык",
        "flood_ban": "⛔ Слишком много запросов.\nБлок на 5 минут.",
        "flood_callback": "⛔ ты заблокирован",
        "session_not_found": "❗ Сессия не найдена",
        "no_users": "❗ Пользователей нет",
        "sections_not_found": "❗ Разделов нет",
        "profile_name": "Имя",
        "profile_age": "Возраст",
        "section_missing": "❗ Раздел не найден",
        "leaderboard_title": "Таблица лидеров",
        "correct": "Правильно",
        "wrong": "Ошибка",
        "score": "Баллы",
        "user_info": "Информация о пользователе",
        "attempt": "Попытка",
        "mode": "Режим",
        "date": "Дата",
        "no_answer": "Нет ответа",
        "banned": "⛔ Вы заблокированы в боте",
        "choose_lang_text": "Выберите язык",
        "temporary_block": "⛔ Вы временно заблокированы",
        "spam_block_3m": "⛔ Слишком много запросов.\nВы заблокированы на 3 минуты.",
        "message_too_long": "❗ Сообщение слишком длинное",
        "section_not_found_simple": "❗ Раздел не найден",
        "sections_empty": "❗ Разделов нет",
        "user_label": "Пользователь",
        "name_label": "Имя",
        "age_label": "Возраст",
        "not_exists": "нет",
        "attempt_label": "Попытка",
        "mode_label": "Режим",
        "results_title": "📊 Результаты",
        "no_answer_text": "нет ответа",
        "add_source": "➕ Добавить Source",
        "add_practice": "➕ Добавить Practice",
        "add_test": "➕ Добавить Test",
        
        "select_subject": "📚 Выберите предмет:",
        "select_source": "📂 Выберите source:",
        "select_practice": "📝 Выберите practice:",
        "select_test": "📄 Выберите тест:",
        
        "enter_source_name": "Введите название source:",
        "enter_practice_name": "Введите название practice:",
        
        "source_added": "✅ Source добавлен",
        "practice_added": "✅ Practice добавлен",
        
        "step_subject": "1️⃣ Выберите предмет:",
        "step_source": "2️⃣ Выберите source:",
        "step_practice": "3️⃣ Выберите practice:",
        "step_test": "4️⃣ Выберите тест:",

        "english_subject": "English",
        "math_subject": "Math",
        
        "no_practices": "❗ Practices не найдены",
        "no_tests": "❗ Тесты не найдены",
        "no_sources": "❗ Sources не найдены",
        "edit_menu": "✏️ Редактировать",
        "edit_source": "📚 Редактировать источник",
        "edit_practice": "📝 Практика редактирования",
        "edit_test": "📄 Тест редактирования",
        "choose_source": "Выбрать источник",
        "choose_practice": "Выбрать практику",
        "choose_test": "Выбрать тест",
            
    },

    "en": {
        "choose_1_2": "Send 1 or 2",
        "welcome": "Welcome!",
        "choose_lang": "Choose language:",
        "enter_name": "Enter your name:",
        "enter_age": "Enter your age:",
        "registered": "✅ Registered successfully!",
        "sections": "📚 Sections",
        "results": "📊 Results",
        "profile": "⚙️ Profile",
        "help": "🆘 Help",
        "saved": "✅ Answer saved",
        "time_up": "⛔ Time is over",
        "finish": "✅ Finish",
        "users": "👥 Users",
        "leaderboard": "🏆 Leaderboard",
        "add_section": "➕ Add Section",
        "edit_section": "✏️ Edit Section",
        "upload_file": "📥 Upload File",
        "help_messages": "🆘 Help Messages",
        "spam_ban": "⛔ Too many requests",
        "long_msg": "❗ Message is too long",
        "session_not_found": "❗ Session not found",
        "section_not_found": "❗ Section not found",
        "choose_section": "📚 Choose section",
        "test_started": "📝 Test started",
        "choose_mode": "Choose test mode",
        "with_time": "⏱ With Time",
        "without_time": "♾ Without Time",
        "welcome_back": "Welcome back!",
        "new_name": "Enter new name:",
        "section_name": "Section name:",
        "admin_panel": "👑 Admin panel",
        "rename": "✏️ Rename",
        "delete_section": "🗑 Delete Section",
        "choose": "Choose:",
        "deleted": "Deleted",
        "changed": "Changed",
        "section_added": "Section added!",
        "time_input": "Time (minutes):",
        "numbers_only": "Enter numbers only",
        "choose_mode_admin": "1: with time\n2: with/without",
        "file_upload_choose": "Which section do you want to upload file to?",
        "no_sections": "❗ No sections",
        "send_file": "📄 Send file",
        "file_received": "✅ File received.\n\nNow send answers:\n1-A-10",
        "answers_saved": "✅ Answers and scores saved",
        "users_list": "Users:",
        "leaderboard_choose": "🏆 Choose section for leaderboard:",
        "results_not_found": "❗ No results",
        "user_not_found": "User not found",
        "section_select": "Choose section:",
        "no_results": "❗ No results for this section",
        "help_no": "❗ No help messages",
        "help_messages_title": "🆘 Help Messages:\n\n",
        "language_changed": "✅ Language changed",
        "name_updated": "✅ Name updated",
        "age_updated": "✅ Age updated",
        "new_age": "Enter new age:",
        "no_sections_exist": "❗ No sections available",
        "finish_old_test": "❗ Finish previous test first",
        "choose_test_type": "Choose test type:",
        "profile_info": "👤 Profile:",
        "not_registered": "❗ You are not registered",
        "message_sent_admin": "✅ Message sent to admin",
        "send_help_message": "✍️ Write your message to admin",
        "admin_cannot_help": "❗ Admin cannot send help message",
        "answers_saved_user": "✅ Answer saved. If you want to change it, send it again. To finish the test, press the Finish button.",
        "no_user_results": "❗ You have no results yet",
        "user_results": "📊 Your results:\n\n",
        "test_started_text": "📝 Test started!\n\nAnswer format:\n1-A\n2-B\n3-C",
        "time_left": "⏳ Remaining time:",
        "edit_name": "✏️ Edit Name",
        "edit_age": "🎂 Edit Age",
        "change_language": "🌐 Change Language",
        "flood_ban": "⛔ Too many requests.\nBlocked for 5 minutes.",
        "flood_callback": "⛔ You are blocked",
        "session_not_found": "❗ Session not found",
        "no_users": "❗ No users found",
        "sections_not_found": "❗ No sections found",
        "profile_name": "Name",
        "profile_age": "Age",
        "section_missing": "❗ Section not found",
        "leaderboard_title": "Leaderboard",
        "correct": "Correct",
        "wrong": "Wrong",
        "score": "Score",
        "user_info": "User info",
        "attempt": "Attempt",
        "mode": "Mode",
        "date": "Date",
        "no_answer": "No answer",
        "banned": "⛔ You are banned from the bot",
        "choose_lang_text": "Choose language",
        "temporary_block": "⛔ You are temporarily blocked",
        "spam_block_3m": "⛔ Too many requests.\nYou are blocked for 3 minutes.",
        "message_too_long": "❗ Message is too long",
        "section_not_found_simple": "❗ Section not found",
        "sections_empty": "❗ No sections found",
        "user_label": "User",
        "name_label": "Name",
        "age_label": "Age",
        "not_exists": "none",
        "attempt_label": "Attempt",
        "mode_label": "Mode",
        "results_title": "📊 Results",
        "no_answer_text": "no answer",
        "add_source": "➕ Add Source",
        "add_practice": "➕ Add Practice",
        "add_test": "➕ Add Test",
        
        "select_subject": "📚 Choose subject:",
        "select_source": "📂 Choose source:",
        "select_practice": "📝 Choose practice:",
        "select_test": "📄 Choose test:",
        
        "enter_source_name": "Enter source name:",
        "enter_practice_name": "Enter practice name:",
        
        "source_added": "✅ Source added",
        "practice_added": "✅ Practice added",
        
        "step_subject": "1️⃣ Choose subject:",
        "step_source": "2️⃣ Choose source:",
        "step_practice": "3️⃣ Choose practice:",
        "step_test": "4️⃣ Choose test:",

        "english_subject": "English",
        "math_subject": "Math",
        
        "no_practices": "❗ No practices found",
        "no_tests": "❗ No tests found",
        "no_sources": "❗ No sources found",
        "edit_menu": "✏️ Edit",
        "edit_source": "📚 Edit source",
        "edit_practice": "📝 Edit practice",
        "edit_test": "📄 Edit test",
        "choose_source":"Choose Source",
        "choose_practice": "Choose Practice",
        "choose_test": "Choose Test",
    }
}
def get_main_menu(user_id):

    lang = get_lang(user_id)

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=LANGS[lang]["sections"])],
            [KeyboardButton(text=LANGS[lang]["results"])],
            [KeyboardButton(text=LANGS[lang]["profile"])]
        ],
        resize_keyboard=True
    )

def get_admin_menu():

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=tr_admin("add_source"))],
            [KeyboardButton(text=tr_admin("add_practice"))],
            [KeyboardButton(text=tr_admin("add_test"))],
            [KeyboardButton(text=tr_admin("edit_menu"))],
            [KeyboardButton(text=tr_admin("upload_file"))],
            [KeyboardButton(text=tr_admin("users"))],
            [KeyboardButton(text=tr_admin("leaderboard"))],
            [KeyboardButton(text=tr_admin("help_messages"))]
        ],
        resize_keyboard=True
    )
# ---------------- STATES ----------------
class ChooseLanguage(StatesGroup):
    language = State()
    
    
class UploadFile(StatesGroup):
    waiting_file = State()
    waiting_answers = State()
    

class Register(StatesGroup):
    name = State()
    age = State()

class AddSource(StatesGroup):
    subject = State()
    source = State()

class AddPractice(StatesGroup):
    category = State()
    practice = State()

class AddTest(StatesGroup):
    subject = State()
    source = State()
    practice = State()
    title = State()
    time = State()
    mode = State()

class RenameSection(StatesGroup):
    new_name = State()

class HelpState(StatesGroup):
    waiting_message = State()
    
class EditMenu(StatesGroup):
    source = State()
    practice_source = State()
    practice = State()
    test_source = State()
    test_practice = State()
    test = State()
    
class EditItem(StatesGroup):
    rename = State()
    
class AddSection(StatesGroup):
    title = State()
    time = State()
    mode = State()


# ---------------- START ----------------
def is_menu_text(text_key):
    return F.text.in_([
        LANGS[lang][text_key]
        for lang in LANGS
    ])

async def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    async with db_lock:
        cur = conn.cursor()
        cur.execute(query, params)

        result = None

        if fetchone:
            result = cur.fetchone()

        elif fetchall:
            result = cur.fetchall()

        if commit:
            conn.commit()

        cur.close()
        return result
    
    
    
async def timer(user_id, seconds):

    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=seconds)

    while True:

        # session yo‘q bo‘lsa stop
        if user_id not in sessions:
            return

        # real qolgan vaqt
        remaining = int((end_time - datetime.now()).total_seconds())

        # vaqt tugasa
        if remaining <= 0:
            break

        mins = remaining // 60
        secs = remaining % 60

        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=sessions[user_id]["msg_id"],
                text=f"{tr(user_id, 'time_left')} {mins:02d}:{secs:02d}"
            )

        except Exception as e:
            if "message is not modified" not in str(e):
                logging.error(f"Timer edit error: {e}")

        # har 10 sekund update
        await asyncio.sleep(30)

    # session o‘chib ketgan bo‘lsa
    if user_id not in sessions:
        return

    # double finishdan himoya
    if user_id in processing_users:
        return

    processing_users.add(user_id)

    try:

        await bot.send_message(
            user_id,
            tr(user_id, "time_up")
        )

        result = await calculate_result(user_id)

        if not result:
            return

        result_text, correct, wrong, total_score = result

        await bot.send_message(
            user_id,
            f"📊 {tr(user_id, 'results')}:\n\n"
            f"{result_text}\n"
            f"✔ {tr(user_id, 'correct')}: {correct}\n"
            f"❌ {tr(user_id, 'wrong')}: {wrong}\n"
            f"🏆 {tr(user_id, 'score')}: {total_score}"
        )

    finally:
        processing_users.discard(user_id)

def get_lang(user_id):

    cursor.execute(
        "SELECT language FROM users WHERE user_id=?",
        (user_id,)
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    return "uz"


def tr(user_id, key):

    lang = get_lang(user_id)

    return LANGS.get(lang, LANGS["uz"]).get(key, key)

admin_lang = "uz"

def tr_admin(key):
    return LANGS[admin_lang].get(key, key)

@dp.message(ChooseLanguage.language)
async def choose_language(message: Message, state: FSMContext):

    text = message.text
    global admin_lang

    if "O'zbek" in text:
        lang = "uz"

    elif "Русский" in text:
        lang = "ru"
        
    else:
        lang = "en"

    if message.from_user.id == ADMIN_ID:
        admin_lang = lang
        
        await message.answer(
            tr_admin("admin_panel"),
            reply_markup=get_admin_menu()
        )

        await state.clear()
        return

    

    await state.update_data(language=lang)
    
    cursor.execute(
        "SELECT * FROM users WHERE user_id=?",
        (message.from_user.id,)
    )

    existing_user = cursor.fetchone()

    if existing_user:

        cursor.execute(
            "UPDATE users SET language=? WHERE user_id=?",
            (lang, message.from_user.id)
        )

        conn.commit()

        await message.answer(
            tr(message.from_user.id, "language_changed"),
            reply_markup=get_main_menu(message.from_user.id)
        )

        await state.clear()
        return
    
    temp[message.from_user.id] = {
        "language": lang
    }

    await message.answer(
        LANGS[lang]["enter_name"]
    )

    await state.set_state(Register.name)



@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):

    user_id = message.from_user.id

    # ADMIN
    if user_id == ADMIN_ID:

        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🇺🇿 O'zbek")],
                [KeyboardButton(text="🇷🇺 Русский")],
                [KeyboardButton(text="🇺🇸 English")]
            ],
            resize_keyboard=True
        )

        await message.answer(
            "Tilni tanlang / Choose language / Выберите язык",
            reply_markup=kb
        )

        await state.set_state(ChooseLanguage.language)
        return

    # BAN CHECK
    if await is_banned(user_id):
        return await message.answer(
            tr(user_id, "banned")
        )

    # USER BOR-YO‘QLIGINI TEKSHIRAMIZ
    cursor.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user_id,)
    )

    user = cursor.fetchone()

    # AGAR USER BOR BO‘LSA
    if user:

        await message.answer(
            tr(user_id, "welcome_back"),
            reply_markup=get_main_menu(user_id)
        )

        return

    # AGAR YANGI USER BO‘LSA → TIL TANLAYDI
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇺🇿 O'zbek")],
            [KeyboardButton(text="🇷🇺 Русский")],
            [KeyboardButton(text="🇺🇸 English")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Tilni tanlang / Choose language / Выберите язык",
        reply_markup=kb
    )

    await state.set_state(ChooseLanguage.language)

@dp.message(Command("help"))
async def help_command(message: Message, state: FSMContext):

    if message.from_user.id == ADMIN_ID:
        return await message.answer(
            tr(message.from_user.id, "admin_cannot_help")
        )

    await message.answer(
        tr(message.from_user.id, "send_help_message")
    )

    await state.set_state(HelpState.waiting_message)

@dp.message(HelpState.waiting_message)
async def receive_help_message(message: Message, state: FSMContext):

    username = message.from_user.username or "-"

    cursor.execute("""
        INSERT INTO help_messages
        (user_id, username, message, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        message.from_user.id,
        username,
        message.text,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()

    await message.answer(
        tr(message.from_user.id, "message_sent_admin")
    )

    await state.clear()

@dp.message(Register.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(
        tr(message.from_user.id, "enter_age")
    )
    await state.set_state(Register.age)

@dp.message(Register.age)
async def reg_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer(
            tr(message.from_user.id, "numbers_only")
        )
    data = await state.get_data()

    username = message.from_user.username or "-"

    cursor.execute(
        "INSERT INTO users(user_id, name, age, username, language) VALUES (?, ?, ?, ?, ?)",
        (
            message.from_user.id,
            data["name"],
            message.text,
            username,
            data["language"]
        )
    )
    
    conn.commit()

    await message.answer(
        tr(message.from_user.id, "registered"),
        reply_markup=get_main_menu(message.from_user.id)
    )
    await state.clear()

# ---------------- ADD SECTION ----------------



@dp.message(AddSection.title)
async def sec_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer(
        tr_admin("time_input")
    )
    await state.set_state(AddSection.time)

@dp.message(AddSection.time)
async def sec_time(message: Message, state: FSMContext):
    try:
        await state.update_data(time=int(message.text))
    except Exception as e:
        logging.error(e)
        return await message.answer(
            tr_admin("numbers_only")
        )
    await message.answer(
        tr_admin("choose_mode_admin")
    )
    await state.set_state(AddSection.mode)

@dp.message(AddSection.mode)
async def sec_mode(message: Message, state: FSMContext):
    mode = "fixed" if message.text == "1" else "flex"

    data = await state.get_data()

    cursor.execute(
        "INSERT INTO sections (title, time_limit, mode) VALUES (?, ?, ?)",
        (data["title"], data["time"], mode)
    )
    conn.commit()

    await message.answer(
        tr_admin("section_added")
    )
    await state.clear()

# ---------------- EDIT SECTION ----------------


class UploadSelect(StatesGroup):
    subject = State()
    source = State()
    practice = State()
    test = State()

@dp.message(is_menu_text("upload_file"))
async def upload_file_start(message: Message):

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="English",
                    callback_data="uploadsub_english"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Math",
                    callback_data="uploadsub_math"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_source"),
        reply_markup=kb
    )
@dp.callback_query(F.data.startswith("uploadsub_"))
async def upload_choose_source(callback: CallbackQuery):

    subject = callback.data.split("_")[1]

    cursor.execute("""
        SELECT DISTINCT source
        FROM section_categories
        WHERE subject=?
    """, (subject,))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[0],
                callback_data=f"uploadsource_{subject}_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await message.answer(
        tr(message.from_user.id, "choose_source"),
        reply_markup=kb
    )     
    
@dp.callback_query(F.data.startswith("uploadsource_"))
async def upload_choose_practice(callback: CallbackQuery):

    subject = callback.data.split("_")[1]
    source = callback.data.split("_", 2)[2]

    cursor.execute("""
        SELECT id, practice
        FROM section_categories
        WHERE subject=? AND source=? AND practice!=''
    """, (subject, source))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[1],
                callback_data=f"uploadpractice_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_practice"),
        reply_markup=kb
    )
    
@dp.callback_query(F.data.startswith("uploadpractice_"))
async def upload_choose_test(callback: CallbackQuery):

    category_id = int(callback.data.split("_")[1])

    cursor.execute("""
        SELECT id, title
        FROM sections
        WHERE category_id=?
    """ , (category_id,))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[1],
                callback_data=f"uploadtest_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_test"),
        reply_markup=kb
    )
    
@dp.callback_query(F.data.startswith("uploadtest_"))
async def upload_test_selected(
    callback: CallbackQuery,
    state: FSMContext
):

    sec_id = int(callback.data.split("_")[1])

    await state.update_data(sec_id=sec_id)

    await callback.message.answer(
        tr(callback.from_user.id, "send_file_text")
    )

    await state.set_state(UploadFile.waiting_file)




# ---------------- ADD QUESTION ----------------
@dp.message(is_menu_text("edit_menu"))
async def edit_menu(message: Message):

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr(message.from_user.id, "edit_source"),
                    callback_data="edit_source"
                )
            ],
            [
                InlineKeyboardButton(
                    text=tr(message.from_user.id, "edit_practice"),
                    callback_data="edit_practice"
                )
            ],
            [
                InlineKeyboardButton(
                    text=tr(message.from_user.id, "edit_test"),
                    callback_data="edit_test"
                )
            ]
        ]
    )

    await message.answer(
        tr(message.from_user.id, "choose"),
        reply_markup=kb
    )


@dp.callback_query(F.data == "edit_source")
async def edit_source(callback: CallbackQuery):

    cursor.execute("""
        SELECT DISTINCT source
        FROM section_categories
    """)

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[0],
                callback_data=f"sourceedit_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_source"),
        reply_markup=kb
    )
    
@dp.callback_query(F.data.startswith("sourceedit_"))
async def source_actions(callback: CallbackQuery):

    source = callback.data.split("_", 1)[1]

    temp[callback.from_user.id] = {
        "edit_type": "source",
        "source": source
    }

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr_admin("rename"),
                    callback_data="rename_item"
                )
            ],
            [
                InlineKeyboardButton(
                    text=tr_admin("delete_section"),
                    callback_data="delete_item"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        source,
        reply_markup=kb
    )
    
@dp.callback_query(F.data == "edit_practice")
async def edit_practice(callback: CallbackQuery):

    cursor.execute("""
        SELECT DISTINCT source
        FROM section_categories
    """)

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[0],
                callback_data=f"practice_source_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_source"),
        reply_markup=kb
    )
    
@dp.callback_query(F.data.startswith("practice_source_"))
async def practice_list(callback: CallbackQuery):

    source = callback.data.split("_", 2)[2]

    cursor.execute("""
        SELECT id, practice
        FROM section_categories
        WHERE source=? AND practice!=''
    """, (source,))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[1],
                callback_data=f"practiceedit_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_practice"),
        reply_markup=kb
    )
    
@dp.callback_query(F.data.startswith("practiceedit_"))
async def practice_actions(callback: CallbackQuery):

    cat_id = int(callback.data.split("_")[1])

    temp[callback.from_user.id] = {
        "edit_type": "practice",
        "category_id": cat_id
    }

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr_admin("rename"),
                    callback_data="rename_item"
                )
            ],
            [
                InlineKeyboardButton(
                    text=tr_admin("delete_section"),
                    callback_data="delete_item"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose"),
        reply_markup=kb
    )
    
    
@dp.callback_query(F.data == "edit_test")
async def edit_test(callback: CallbackQuery):

    cursor.execute("""
        SELECT DISTINCT source
        FROM section_categories
    """)

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[0],
                callback_data=f"test_source_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_source"),
        reply_markup=kb
    )
    
@dp.callback_query(F.data.startswith("test_source_"))
async def test_practice_list(callback: CallbackQuery):

    source = callback.data.split("_", 2)[2]

    cursor.execute("""
        SELECT id, practice
        FROM section_categories
        WHERE source=? AND practice!=''
    """, (source,))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[1],
                callback_data=f"test_practice_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_practice"),
        reply_markup=kb
    )
    
@dp.callback_query(F.data.startswith("test_practice_"))
async def test_list(callback: CallbackQuery):

    cat_id = int(callback.data.split("_")[2])

    cursor.execute("""
        SELECT id, title
        FROM sections
        WHERE category_id=?
    """, (cat_id,))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[1],
                callback_data=f"testedit_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_test"),
        reply_markup=kb
    )
    
@dp.callback_query(F.data.startswith("testedit_"))
async def test_actions(callback: CallbackQuery):

    sec_id = int(callback.data.split("_")[1])

    temp[callback.from_user.id] = {
        "edit_type": "test",
        "section_id": sec_id
    }

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr_admin("rename"),
                    callback_data="rename_item"
                )
            ],
            [
                InlineKeyboardButton(
                    text=tr_admin("delete_section"),
                    callback_data="delete_item"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose"),
        reply_markup=kb
    )
    



@dp.callback_query(F.data == "delete_item")
async def delete_item(callback: CallbackQuery):

    data = temp[callback.from_user.id]

    edit_type = data["edit_type"]

    # SOURCE DELETE
    if edit_type == "source":

        source = data["source"]

        cursor.execute("""
            SELECT id
            FROM section_categories
            WHERE source=?
        """, (source,))

        cats = cursor.fetchall()

        for c in cats:

            cat_id = c[0]

            cursor.execute("""
                DELETE FROM section_answers
                WHERE section_id IN (
                    SELECT id FROM sections
                    WHERE category_id=?
                )
            """, (cat_id,))
            
            cursor.execute("""
                DELETE FROM results
                WHERE section_id IN (
                    SELECT id FROM sections
                    WHERE category_id=?
                )
            """, (cat_id,))
            
            cursor.execute("""
                DELETE FROM user_answers
                WHERE section_id IN (
                    SELECT id FROM sections
                    WHERE category_id=?
                )
            """, (cat_id,))
            
            cursor.execute("""
                DELETE FROM sections
                WHERE category_id=?
            """, (cat_id,))

        cursor.execute("""
            DELETE FROM section_categories
            WHERE source=?
        """, (source,))

    # PRACTICE DELETE
    elif edit_type == "practice":

        cat_id = data["category_id"]
        
        cursor.execute("""
            DELETE FROM results
            WHERE section_id IN (
                SELECT id FROM sections
                WHERE category_id=?
            )
        """, (cat_id,))
        
        cursor.execute("""
            DELETE FROM user_answers
            WHERE section_id IN (
                SELECT id FROM sections
                WHERE category_id=?
            )
        """, (cat_id,))

        cursor.execute("""
            DELETE FROM sections
            WHERE category_id=?
        """, (cat_id,))

        cursor.execute("""
            DELETE FROM section_categories
            WHERE id=?
        """, (cat_id,))
    elif edit_type == "test":

        sec_id = data["section_id"]
        
        cursor.execute("""
            DELETE FROM results
            WHERE section_id=?
        """, (sec_id,))

        cursor.execute("""
            DELETE FROM user_answers
            WHERE section_id=?
        """, (sec_id,))

        cursor.execute("""
            DELETE FROM section_answers
            WHERE section_id=?
        """, (sec_id,))

        cursor.execute("""
            DELETE FROM questions
            WHERE section_id=?
        """, (sec_id,))

        cursor.execute("""
            DELETE FROM sections
            WHERE id=?
        """, (sec_id,))
    conn.commit()
    
    

    await callback.message.answer(
        tr_admin("deleted")
    )
    
    temp.pop(callback.from_user.id, None)
    
@dp.callback_query(F.data == "rename_item")
async def rename_item(callback: CallbackQuery, state: FSMContext):

    await callback.message.answer(
        tr(callback.from_user.id, "new_name")
    )

    await state.set_state(EditItem.rename)
    
@dp.message(EditItem.rename)
async def save_rename(message: Message, state: FSMContext):

    data = temp[message.from_user.id]

    edit_type = data["edit_type"]

    # SOURCE
    if edit_type == "source":

        cursor.execute("""
            UPDATE section_categories
            SET source=?
            WHERE source=?
        """, (
            message.text,
            data["source"]
        ))

    # PRACTICE
    elif edit_type == "practice":

        cursor.execute("""
            UPDATE section_categories
            SET practice=?
            WHERE id=?
        """, (
            message.text,
            data["category_id"]
        ))
    elif edit_type == "test":

        cursor.execute("""
            UPDATE sections
            SET title=?
            WHERE id=?
        """, (
            message.text,
            data["section_id"]
        ))
    conn.commit()

    await message.answer(
        tr_admin("changed")
    )

    await state.clear()
    
    temp.pop(message.from_user.id, None)

# ---------------- PROFILE ----------------

class EditProfile(StatesGroup):
    name = State()
    age = State()

@dp.message(is_menu_text("profile"))
async def profile_menu(message: Message):
    cursor.execute("SELECT name, age FROM users WHERE user_id=?", (message.from_user.id,))
    user = cursor.fetchone()

    if not user:
        return await message.answer(
            tr(message.from_user.id, "not_registered")
        )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=tr(message.from_user.id, "edit_name"), callback_data="edit_name")],
            [InlineKeyboardButton(text=tr(message.from_user.id, "edit_age"), callback_data="edit_age")],
            [InlineKeyboardButton(text=tr(message.from_user.id, "change_language"), callback_data="change_lang")]
        ]
    )

    await message.answer(
        f"👤 {tr(message.from_user.id, 'profile_info')}\n"
        f"{tr(message.from_user.id, 'profile_name')}: {user[0]}\n"
        f"{tr(message.from_user.id, 'profile_age')}: {user[1]}",
        reply_markup=kb
    )

@dp.callback_query(F.data == "change_lang")
async def change_lang(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

    await callback.answer()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 Uzbek", callback_data="lang_uz")
            ],
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")
            ],
            [
                InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")
            ]
        ]
    )

    await callback.message.answer(
        tr(callback.from_user.id, "choose_lang"),
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("lang_"))
async def save_lang(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

    await callback.answer()

    lang = callback.data.split("_")[1]

    await db_execute(
        "UPDATE users SET language=? WHERE user_id=?",
        (lang, callback.from_user.id),
        commit=True
    )

    await callback.message.answer(
        tr(callback.from_user.id, "language_changed"),
        reply_markup=get_main_menu(callback.from_user.id)
    )

@dp.callback_query(F.data == "edit_name")
async def edit_name_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )
    await callback.answer()
    await callback.message.answer(
        tr(callback.from_user.id, "new_name")
    )
    await state.set_state(EditProfile.name)

@dp.message(EditProfile.name)
async def save_new_name(message: Message, state: FSMContext):
    cursor.execute(
        "UPDATE users SET name=? WHERE user_id=?",
        (message.text, message.from_user.id)
    )
    conn.commit()

    await message.answer(
        tr(message.from_user.id, "name_updated")
    )
    await state.clear()

@dp.callback_query(F.data == "edit_age")
async def edit_age_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

    await callback.answer()
    await callback.message.answer(
        tr(callback.from_user.id, "new_age")
    )
    await state.set_state(EditProfile.age)

@dp.message(EditProfile.age)
async def save_new_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer(
            tr(message.from_user.id, "numbers_only")
        )
    cursor.execute(
        "UPDATE users SET age=? WHERE user_id=?",
        (message.text, message.from_user.id)
    )
    conn.commit()

    await message.answer(
        tr(message.from_user.id, "age_updated")
    )
    await state.clear()

    
@dp.callback_query(F.data.startswith("startsec_"))
async def start_test(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

    
    user_id = callback.from_user.id
    if callback.from_user.id != ADMIN_ID:
        if not await callback_spam_check(callback):
            return
    await callback.answer()
    if user_id in sessions:
        return await callback.message.answer(
            tr(user_id, "finish_old_test")
        )

    user_id = callback.from_user.id
    try:
        sec_id = int(callback.data.split("_")[1])
    except:
        return

    # 🔥 mode va time olish
    cursor.execute("SELECT mode, time_limit FROM sections WHERE id=?", (sec_id,))
    row = cursor.fetchone()

    if not row:
        return await callback.message.answer(tr(user_id, "section_not_found"))

    mode = row[0]
    time_limit = row[1] or 1

    # 🔥 AGAR FIXED bo‘lsa → avtomatik boshlanadi
    if mode == "fixed":
        await start_real_test(callback, user_id, sec_id, time_limit)
        return

    # 🔥 AGAR FLEX bo‘lsa → user tanlaydi
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr(user_id, "with_time"),
                    callback_data=f"mode_time_{sec_id}"
                ),

                InlineKeyboardButton(
                    text=tr(user_id, "without_time"),
                    callback_data=f"mode_notime_{sec_id}"
                )
            ]
        ]
    )

    await callback.message.answer(
        tr(user_id, "choose_test_type"),
        reply_markup=kb
    )




@dp.callback_query(F.data.startswith("mode_time_"))
async def start_with_time(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

    await callback.answer()
    sec_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    if callback.from_user.id != ADMIN_ID:
        if not await callback_spam_check(callback):
            return
    cursor.execute("SELECT time_limit FROM sections WHERE id=?", (sec_id,))
    time_limit = cursor.fetchone()[0] or 1

    await start_real_test(callback, user_id, sec_id, time_limit)


@dp.callback_query(F.data.startswith("mode_notime_"))
async def start_without_time(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

    await callback.answer()
    sec_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    if callback.from_user.id != ADMIN_ID:
        if not await callback_spam_check(callback):
            return
    await start_real_test(callback, user_id, sec_id, None)
    
async def start_real_test(callback, user_id, sec_id, time_limit):

    conn.commit()
    # FILE yuborish
    cursor.execute("SELECT file_id FROM sections WHERE id=?", (sec_id,))
    file = cursor.fetchone()

    if file and file[0]:
        await bot.send_document(user_id, file[0])

    # Qo‘llanma + Finish
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=tr(user_id, "finish"),
                callback_data="finish"
            )]
        ]
    )

    await callback.message.answer(
        tr(user_id, "test_started_text"),
        reply_markup=kb
    )
    
    cursor.execute("""
        DELETE FROM user_answers
        WHERE user_id=? AND section_id=?
    """, (user_id, sec_id))

    conn.commit()
    # 🔥 TIMER FAQAT BOR BO‘LSA
    if time_limit:
        timer_msg = await callback.message.answer(
            f"{tr(user_id, 'time_left')} {time_limit:02d}:00"
        )

        task = asyncio.create_task(
            timer(user_id, time_limit * 60)
        )
        
        
        
        sessions[user_id] = {
            "started_at": datetime.now(),
            "sec_id": sec_id,
            "msg_id": timer_msg.message_id,
            "task": task
        }

        
    else:
        # without time
        sessions[user_id] = {
            "sec_id": sec_id
        }

@dp.message(is_menu_text("results"))
async def my_results(message: Message):
    cursor.execute("""
        SELECT
            s.title,
            sc.source,
            sc.practice,
            r.correct,
            r.wrong,
            r.score,
            r.created_at
        FROM results r
        JOIN sections s ON s.id = r.section_id
        LEFT JOIN section_categories sc
        ON sc.id = s.category_id
        WHERE r.user_id=?
        ORDER BY r.id DESC
    """, (message.from_user.id,))

    results = cursor.fetchall()

    if not results:
        return await message.answer(
            tr(message.from_user.id, "no_user_results")
        )

    text = tr(message.from_user.id, "user_results")

    for r in results:
        text += (
            f"📚 {r[0]}\n"
            f"📂 {r[1]}\n"
            f"📝 {r[2]}\n"
            f"✔ {r[3]} | ❌ {r[4]} | 🏆 {r[5]}\n"
            f"📅 {r[6]}\n\n"
        )

    await message.answer(text)
    

# ---------------- RUN ----------------
@dp.callback_query(F.data.startswith("uploadfile_"))
async def set_file_section(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

    await callback.answer()
    if callback.from_user.id != ADMIN_ID:
        return
    sec_id = int(callback.data.split("_")[1])

    # ❌ eski
    # temp["edit_sec"] = sec_id

    # ✅ yangi
    await state.update_data(sec_id=sec_id)

    await callback.message.answer(
        tr_admin("send_file")
    )
    await state.set_state(UploadFile.waiting_file)
    
    
    
@dp.message(UploadFile.waiting_file, F.document)
async def receive_file(message: Message, state: FSMContext):
    data = await state.get_data()
    sec_id = data.get("sec_id")

    file_id = message.document.file_id

    cursor.execute(
        "UPDATE sections SET file_id=? WHERE id=?",
        (file_id, sec_id)
    )
    conn.commit()

    await message.answer(
        tr_admin("file_received")
    )

    await state.set_state(UploadFile.waiting_answers)
    
@dp.message(UploadFile.waiting_answers)
async def receive_answers(message: Message, state: FSMContext):

    data = await state.get_data()
    sec_id = data.get("sec_id")

    if not sec_id:
        return await message.answer(
            tr(message.from_user.id, "section_missing")
        )

    cursor.execute("""
        DELETE FROM section_answers
        WHERE section_id=?
    """, (sec_id,))

    lines = message.text.split("\n")

    saved = 0

    for line in lines:

        line = line.strip()

        if not line:
            continue

        line = re.sub(r"\s+", "", line)

        try:
            match = re.match(
                r"^(\d+)-\((.+)\)-(\d+)$",
                line
            )

            if not match:
                continue

            q_num = int(match.group(1))

            answers_raw = match.group(2)

            score = int(match.group(3))

            answers = []

            for a in answers_raw.split(","):

                a = a.strip().lower()

                if a:
                    answers.append(a)

            correct_answer = "|".join(answers)

            cursor.execute("""
                INSERT INTO section_answers
                (
                    section_id,
                    question_number,
                    correct_answer,
                    score
                )
                VALUES (?, ?, ?, ?)
            """, (
                sec_id,
                q_num,
                correct_answer,
                score
            ))

            saved += 1

        except Exception as e:
            logging.error(e)

    conn.commit()

    await message.answer(
        f"{tr_admin('answers_saved')} ({saved})"
    )

    await state.clear()
    

    
@dp.message(is_menu_text("users"))
async def users_list(message: Message):

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    if not users:
        return await message.answer(
            tr(message.from_user.id, "no_users")
        )

    buttons = []
    for u in users:
        name = u[1]
        uid = u[0]
        buttons.append([
            InlineKeyboardButton(text=name, callback_data=f"user_{uid}")
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        tr_admin("users_list"),
        reply_markup=kb
    )
    
    

@dp.message(is_menu_text("leaderboard"))
async def leaderboard_sections(message: Message):

    cursor.execute("SELECT id, title FROM sections")
    sections = cursor.fetchall()

    if not sections:
        return await message.answer(
            tr(message.from_user.id, "sections_not_found")
        )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=s[1],
                    callback_data=f"leader_{s[0]}"
                )
            ]
            for s in sections
        ]
    )
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        tr_admin("leaderboard_choose"),
        reply_markup=kb
    )

    

@dp.callback_query(F.data.startswith("leader_"))
async def show_leaderboard(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

    await callback.answer()
    if callback.from_user.id != ADMIN_ID:
        if not await callback_spam_check(callback):
            return
    if callback.from_user.id != ADMIN_ID:
        return

    sec_id = int(callback.data.split("_")[1])
    
    cursor.execute("SELECT title FROM sections WHERE id=?", (sec_id,))
    sec = cursor.fetchone()

    if not sec:
        return await callback.message.answer(tr(user_id, "sections_empty"))

    sec_name = sec[0]

    # 🔥 eng yuqori natijalar
    cursor.execute("""
    SELECT 
        users.name,
        MAX(results.score),
        MAX(results.correct),
        MIN(results.wrong)
    FROM results
    JOIN users ON users.user_id = results.user_id
    WHERE results.section_id=?
    GROUP BY results.user_id
    ORDER BY MAX(results.score) DESC,
         MAX(results.correct) DESC
    """, (sec_id,))

    rows = cursor.fetchall()

    if not rows:
        return await callback.message.answer(
            tr_admin("results_not_found")
        )

    text = f"🏆 {sec_name} {tr(user_id, 'leaderboard_title')}\n\n"

    for i, row in enumerate(rows, start=1):
        name = row[0]
        score = row[1]
        correct = row[2]
        wrong = row[3]

        text += (
            f"{i}. {name}\n"
            f"🏆 {tr(user_id, 'score')}: {score}\n"
            f"✔ {tr(user_id, 'correct')}: {correct}\n"
            f"❌ {tr(user_id, 'wrong')}: {wrong}\n\n"
        )
    await callback.message.answer(text)

    

@dp.callback_query(F.data.startswith("user_"))
async def user_info(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

    await callback.answer()
    if callback.from_user.id != ADMIN_ID:
        if not await callback_spam_check(callback):
            return
    if callback.from_user.id != ADMIN_ID:
        return

    uid = int(callback.data.split("_")[1])

    user = await db_execute(
        "SELECT * FROM users WHERE user_id=?",
        (uid,),
        fetchone=True
    )

    if not user:
        return await callback.message.answer(
            tr_admin("user_not_found")
        )

    name, age, username = user[1], user[2], user[3]

    text = f"""
    👤 <b>{tr(callback.from_user.id, 'user_info')}</b>
    
    {tr(callback.from_user.id, 'profile_name')}: {name}
    {tr(callback.from_user.id, 'profile_age')}: {age}
    Username: @{username if username else '-'}
    """

    # 🔹 barcha sectionlarni olamiz
    cursor.execute("SELECT id, title FROM sections")
    sections = cursor.fetchall()

    if not sections:
        return await callback.message.answer(text + "\n\n❗ Sectionlar yo‘q")

    # 🔹 har bir section uchun button
    buttons = []
    for s in sections:
        buttons.append([
            InlineKeyboardButton(
                text=s[1],
                callback_data=f"userres_{uid}_{s[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.answer(
        text + "\n\n" + tr_admin("section_select"),
        reply_markup=kb
    )
    
    
    
    
@dp.callback_query(F.data.startswith("userres_"))
async def user_section_result(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )

    if callback.from_user.id != ADMIN_ID:
        if not await callback_spam_check(callback):
            return
    if callback.from_user.id != ADMIN_ID:
        return
    parts = callback.data.split("_")

    uid = int(parts[1])
    sec_id = int(parts[2])

    cursor.execute("SELECT title FROM sections WHERE id=?", (sec_id,))
    sec = cursor.fetchone()
    await callback.answer()

    cursor.execute("SELECT name, age, username FROM users WHERE user_id=?", (uid,))
    u = cursor.fetchone()

    if not sec:
        return await callback.message.answer(
            tr(user_id, "section_not_found")
        )

    sec_name = sec[0]

    cursor.execute("""
        SELECT correct, wrong, score, mode, created_at
        FROM results
        WHERE user_id=? AND section_id=?
        ORDER BY id DESC
    """, (uid, sec_id))

    results = cursor.fetchall()

    if not results:
        return await callback.message.answer(
            f"📚 {sec_name}\n\n{tr_admin('no_results')}"
        )

    text = text = (
        f"👤 {tr(user_id, 'user_label')}\n"
        f"{tr(user_id, 'name_label')}: {u[0]}\n"
        f"{tr(user_id, 'age_label')}: {u[1]}\n"
        f"Username: @{u[2] if u[2] else tr(user_id, 'not_exists')}\n\n"
        f"📚 <b>{sec_name}</b>\n\n"
    )

    for i, r in enumerate(results, start=1):
        text += (
            f"📝 {tr(user_id, 'attempt_label')} {i}\n"
            f"✔ {tr(user_id, 'correct')}: {r[0]}\n"
            f"❌ {tr(user_id, 'wrong')}: {r[1]}\n"
            f"🏆 {tr(user_id, 'score')}: {r[2]}\n"
            f"⏱ {tr(user_id, 'mode_label')}: {r[3]}\n"
            f"📅 {r[4]}\n\n"
        )

    await callback.message.answer(text)


@dp.message(is_menu_text("help_messages"))
async def show_help_messages(message: Message):

    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("""
        SELECT user_id, username, message, created_at
        FROM help_messages
        ORDER BY id DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()

    if not rows:
        return await message.answer(
            tr_admin("help_no")
        )
    text = tr_admin("help_messages_title")

    for row in rows:

        text += (
            f"👤 ID: {row[0]}\n"
            f"📛 Username: @{row[1]}\n"
            f"💬 {row[2]}\n"
            f"📅 {row[3]}\n\n"
        )

    await message.answer(text)
    
    


async def calculate_result(user_id):
    session = sessions.get(user_id)

    if not session:
        return None

    sec_id = session["sec_id"]

    corrects = await db_execute("""
        SELECT question_number, correct_answer, score
        FROM section_answers
        WHERE section_id=?
        ORDER BY question_number ASC
    """, (sec_id,), fetchall=True)

    result_text = ""
    correct = 0
    wrong = 0
    total_score = 0

    for q_num, correct_ans, pts in corrects:

        res = await db_execute("""
            SELECT user_answer
            FROM user_answers
            WHERE user_id=? AND section_id=? AND question_number=?
        """, (
            user_id,
            sec_id,
            q_num
        ), fetchone=True)

        # 🔥 BU YERNI HAM TUZATAMIZ (multi answer uchun)
        if not res:
            wrong += 1
            continue

        user_ans = res[0].replace(" ", "").lower()
        correct_list = [
            a.strip().replace(" ", "").lower()
            for a in correct_ans.split("|")
        ]

        if user_ans in correct_list:
            result_text += f"{q_num} ✅\n"
            correct += 1
            total_score += pts
        else:
            result_text += f"{q_num} ❌\n"
            wrong += 1


    await db_execute("""
    INSERT INTO results (user_id, section_id, correct, wrong, score, mode, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        sec_id,
        correct,
        wrong,
        total_score,
        "file_test",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ), commit=True)
    
    await db_execute("""
        DELETE FROM user_answers
        WHERE user_id=? AND section_id=?
    """, (
        user_id,
        sec_id
    ), commit=True)

    conn.commit()
    sessions.pop(user_id, None)

    try:
        return result_text, correct, wrong, total_score
    finally:
        processing_users.discard(user_id)



@dp.callback_query(F.data == "finish")
async def finish_test(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_id = callback.from_user.id

    if await check_flood(user_id):

        return await callback.answer(
            tr(user_id, "flood_callback"),
            show_alert=True
        )


    # 🔥 callback spam check
    if not await callback_spam_check(callback):
        return

    await callback.answer()

    user_id = callback.from_user.id

    # 🔥 double bosishni bloklaydi
    if user_id in processing_users:
        return

    processing_users.add(user_id)

    try:

        session = sessions.get(user_id)

        if not session:
            return await callback.message.answer(
                tr(user_id, "session_not_found")
            )

        sec_id = session["sec_id"]

    # 🔹 barcha to‘g‘ri javoblarni olamiz
        result = await calculate_result(user_id)

        if not result:
            return

        result_text, correct, wrong, total_score = result

        await callback.message.answer(
            f"{tr(user_id, 'results_title')}:\n\n"
            f"{result_text}\n"
            f"✔ {tr(user_id, 'correct')}: {correct}\n"
            f"❌ {tr(user_id, 'wrong')}: {wrong}\n"
            f"🏆 {tr(user_id, 'score')}: {total_score}"
        )

        # 🔹 userga chiqaramiz

        session = sessions.get(user_id)

        if session:
            task = session.get("task")

            if task:
                task.cancel()
                try:
                    await task
                except Exception as e:
                    logging.error(e)

        # 🔹 sessionni yopamiz
        user_id = callback.from_user.id

        if user_id in sessions:
            del sessions[user_id]
    
        await db_execute("""
            DELETE FROM user_answers
            WHERE user_id=? AND section_id=?
        """, (
            user_id,
            sec_id
        ), commit=True)
    finally:

        processing_users.discard(user_id)
@dp.errors()
async def errors_handler(event: ErrorEvent):

    logging.error(event.exception)

    return True


async def main():
    await dp.start_polling(bot)

 
        
@dp.message(is_menu_text("add_source"))
async def add_source_start(message: Message, state: FSMContext):

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="English",
                    callback_data="subject_english"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Math",
                    callback_data="subject_math"
                )
            ]
        ]
    )

    await message.answer(
        "1-Bo'limni tanlang:",
        reply_markup=kb
    )

    await state.set_state(AddSource.subject)

@dp.callback_query(
    AddSource.subject,
    F.data.startswith("subject_")
)
async def source_subject(callback: CallbackQuery, state: FSMContext):

    subject = callback.data.split("_")[1]

    await state.update_data(subject=subject)

    await callback.message.answer(
        tr(callback.from_user.id, "enter_source_name")
    )

    await state.set_state(AddSource.source)


@dp.message(AddSource.source)
async def save_source(message: Message, state: FSMContext):

    data = await state.get_data()

    cursor.execute("""
        INSERT INTO section_categories
        (subject, source, practice)
        VALUES (?, ?, ?)
    """, (
        data["subject"],
        message.text,
        ""
    ))

    conn.commit()

    await message.answer(
        tr(message.from_user.id, "source_added")
    )

    await state.clear()
    
@dp.message(is_menu_text("add_practice"))
async def add_practice_start(message: Message):

    cursor.execute("""
        SELECT id, subject, source
        FROM section_categories
        WHERE practice=''
    """)

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=f"{r[1]} | {r[2]}",
                callback_data=f"practicecat_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_source"),
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("practicecat_"))
async def choose_practice_category(
    callback: CallbackQuery,
    state: FSMContext
):

    cat_id = int(callback.data.split("_")[1])

    await state.update_data(category_id=cat_id)

    await callback.message.answer(
        tr(callback.from_user.id, "enter_practice_name")
    )

    await state.set_state(AddPractice.practice)
    
@dp.message(AddPractice.practice)
async def save_practice(message: Message, state: FSMContext):

    data = await state.get_data()

    cursor.execute("""
        SELECT subject, source
        FROM section_categories
        WHERE id=?
    """, (data["category_id"],))

    row = cursor.fetchone()

    cursor.execute("""
        INSERT INTO section_categories
        (subject, source, practice)
        VALUES (?, ?, ?)
    """, (
        row[0],
        row[1],
        message.text
    ))

    conn.commit()

    await message.answer(
        tr(message.from_user.id, "practice_added")
    )

    await state.clear()
    
@dp.message(is_menu_text("add_test"))
async def add_test_start(message: Message, state: FSMContext):

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="English",
                    callback_data="testsub_english"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Math",
                    callback_data="testsub_math"
                )
            ]
        ]
    )

    await message.answer(
        tr(message.from_user.id, "select_subject"),
        reply_markup=kb
    )

    await state.set_state(AddTest.subject)
    
@dp.callback_query(
    AddTest.subject,
    F.data.startswith("testsub_")
)
async def add_test_source(callback: CallbackQuery, state: FSMContext):

    subject = callback.data.split("_")[1]

    await state.update_data(subject=subject)

    cursor.execute("""
        SELECT DISTINCT source
        FROM section_categories
        WHERE subject=?
    """, (subject,))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[0],
                callback_data=f"testsource_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "select_source"),
        reply_markup=kb
    )

    await state.set_state(AddTest.source)
    
@dp.callback_query(
    AddTest.source,
    F.data.startswith("testsource_")
)
async def add_test_practice(callback: CallbackQuery, state: FSMContext):

    source = callback.data.split("_", 1)[1]

    data = await state.get_data()

    await state.update_data(source=source)

    cursor.execute("""
        SELECT id, practice
        FROM section_categories
        WHERE subject=? AND source=? AND practice!=''
    """, (
        data["subject"],
        source
    ))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[1],
                callback_data=f"testpractice_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "select_practice"),
        reply_markup=kb
    )

    await state.set_state(AddTest.practice)
    
@dp.callback_query(
    AddTest.practice,
    F.data.startswith("testpractice_")
)
async def add_test_title(callback: CallbackQuery, state: FSMContext):

    category_id = int(callback.data.split("_")[1])

    await state.update_data(category_id=category_id)

    await callback.message.answer(
        tr(callback.from_user.id, "section_name")
    )

    await state.set_state(AddTest.title)
    
@dp.message(AddTest.title)
async def add_test_time(message: Message, state: FSMContext):

    await state.update_data(title=message.text)

    await message.answer(
        tr(message.from_user.id, "time_input")
    )

    await state.set_state(AddTest.time)
    
@dp.message(AddTest.time)
async def add_test_mode(message: Message, state: FSMContext):

    if not message.text.isdigit():
        return await message.answer(
            tr(message.from_user.id, "numbers_only")
        )

    await state.update_data(
        time=int(message.text)
    )

    await message.answer(
        tr(message.from_user.id, "choose_mode_admin")
    )

    await state.set_state(AddTest.mode)
    
@dp.message(AddTest.mode)
async def save_test(message: Message, state: FSMContext):

    if message.text not in ["1", "2"]:
        return await message.answer(
            tr(message.from_user.id, "choose_1_2")
        )

    data = await state.get_data()

    cursor.execute("""
        INSERT INTO sections
        (title, time_limit, mode, category_id)
        VALUES (?, ?, ?, ?)
    """, (
        data["title"],
        data["time"],
        mode,
        data["category_id"]
    ))

    conn.commit()

    await message.answer(
        tr(message.from_user.id, "section_added")
    )

    await state.clear()
    
@dp.message(is_menu_text("sections"))
async def choose_subject(message: Message):

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="English",
                    callback_data="usersub_english"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Math",
                    callback_data="usersub_math"
                )
            ]
        ]
    )

    await message.answer(
        tr(message.from_user.id, "step_subject"),
        reply_markup=kb
    )
    
@dp.callback_query(F.data.startswith("usersub_"))
async def user_choose_source(callback: CallbackQuery):

    subject = callback.data.split("_")[1]

    cursor.execute("""
        SELECT DISTINCT source
        FROM section_categories
        WHERE subject=?
    """, (subject,))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[0],
                callback_data=f"usersource_{subject}_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "step_source"),
        reply_markup=kb
    )   
    
@dp.callback_query(F.data.startswith("usersource_"))
async def user_choose_practice(callback: CallbackQuery):

    parts = callback.data.split("_")

    subject = callback.data.split("_")[1]
    source = callback.data.split("_", 2)[2]

    cursor.execute("""
        SELECT id, practice
        FROM section_categories
        WHERE subject=? AND source=? AND practice!=''
    """, (subject, source))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[1],
                callback_data=f"userpractice_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "choose_practice"),
        reply_markup=kb
    )
    
@dp.callback_query(F.data.startswith("userpractice_"))
async def user_choose_test(callback: CallbackQuery):

    category_id = int(callback.data.split("_")[1])

    cursor.execute("""
        SELECT id, title
        FROM sections
        WHERE category_id=?
    """, (category_id,))

    rows = cursor.fetchall()

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text=r[1],
                callback_data=f"startsec_{r[0]}"
            )
        ])

    kb = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await callback.message.edit_text(
        tr(callback.from_user.id, "step_test"),
        reply_markup=kb
    )   
    
@dp.message()
async def collect_answers(message: Message):

    user_id = message.from_user.id
    
    if await check_flood(user_id):

        return await message.answer(
            tr(user_id, "flood_ban")
        )

    # 🔥 TEMP BAN CHECK
    if user_id in temp_bans:

        if datetime.now() < temp_bans[user_id]:

            return await message.answer(
                tr(user_id, "temporary_block")
            )

        else:
            del temp_bans[user_id]

    # 🔥 ANTI SPAM
    if await anti_spam(message):
        return

        
    if user_id != ADMIN_ID:

        now = time.time()
        
        spam_tracker[user_id].append(now)

        # faqat oxirgi 8 sekund ichidagi requestlar qoladi
        spam_tracker[user_id] = [
            t for t in spam_tracker[user_id]
            if now - t < 8
        ]

        # agar 8 sekund ichida 10 martadan ko‘p yozsa
        if len(spam_tracker[user_id]) >= 15:
                
            temp_bans[user_id] = datetime.now() + timedelta(minutes=3)

            return await message.answer(
                tr(user_id, "spam_block_3m")
            )
        
    if not message.text:
        return

    if len(message.text) > 2000:
        return await message.answer(
            tr(user_id, "message_too_long")
        )
    
    if user_id in spam_tracker and len(spam_tracker[user_id]) == 0:
        del spam_tracker[user_id]
    
    
    if user_id not in sessions:
        return

    sec_id = sessions[user_id]["sec_id"]
    
    
    lines = message.text.split("\n")
    
    pattern = r"^\d{1,3}\s*-\s*.+$"
    valid_answers = 0

    for line in lines:

        if not re.match(pattern, line):
            continue

        valid_answers += 1
        if not line.strip():
            continue

        try:
            line = re.sub(r"\s+", "", line)

            parts = line.split("-", 1)

            q = int(parts[0])
            ans = parts[1].strip().lower()
        except Exception as e:
            logging.error(e)
            continue

    # 🔥 bor-yo‘qligini tekshiradi
        exists = await db_execute("""
            SELECT id
            FROM user_answers
            WHERE user_id=? AND section_id=? AND question_number=?
        """, (
            user_id,
            sec_id,
            q
        ), fetchone=True)

        if exists:
            # update
            await db_execute("""
                UPDATE user_answers
                SET user_answer=?
                WHERE user_id=? AND section_id=? AND question_number=?
            """, (
                ans,
                user_id,
                sec_id,
                q
            ), commit=True)
        else:
            # insert
            await db_execute("""
                INSERT INTO user_answers
                (user_id, section_id, question_number, user_answer)
                VALUES (?, ?, ?, ?)
            """, (
                user_id,
                sec_id,
                q,
                ans
            ), commit=True)

    conn.commit()
    

    if valid_answers > 0:
        await message.answer(
            tr(message.from_user.id, "answers_saved_user")
        )
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        conn.close() 