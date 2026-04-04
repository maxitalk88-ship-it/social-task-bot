import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from keep_alive import keep_alive

# ==========================================
# 1. YOUR BOT SETTINGS
# ==========================================
TOKEN = "8668588568:AAG3sXobv5NiAdFu9aHuc9nSoX-O7EEs_4E"
SUPER_ADMINS =[8668588568, 6915992397] 
DB_NAME = "social_task.db"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==========================================
# 2. DATABASE SETUP
# ==========================================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            balance REAL DEFAULT 50.0, 
            tasks_done INTEGER DEFAULT 0, 
            is_banned INTEGER DEFAULT 0)''')
        await db.commit()

# ==========================================
# 3. DYNAMIC MENU LOGIC
# ==========================================
def get_main_menu(user_id):
    kb = [[KeyboardButton(text="🚀 Browse Tasks"), KeyboardButton(text="➕ Create Task")],[KeyboardButton(text="🔔 Notifications"), KeyboardButton(text="💰 Wallet")],[KeyboardButton(text="🤝 Referral"), KeyboardButton(text="⚙️ Settings")]
    ]
    if user_id in SUPER_ADMINS:
        kb.append([KeyboardButton(text="👑 Admin Panel")])
        
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ==========================================
# 4. START COMMAND
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()
    
    welcome_text = (
        "👋 Welcome to <b>SOCIAL TASK</b>!\n\n"
        "Earn SC by completing simple social media tasks, "
        "or use your SC to grow your own channels!"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_menu(user_id), parse_mode="HTML")

# ==========================================
# 5. RUN THE BOT
# ==========================================
async def main():
    await init_db()
    keep_alive()  # This starts the 24/7 alarm clock!
    print("✅ SOCIAL TASK is running on the Cloud!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
