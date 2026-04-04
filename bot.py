import asyncio
import aiosqlite
import os
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from deep_translator import GoogleTranslator
import google.generativeai as genai
from keep_alive import keep_alive

# ==========================================
# 1. BOT SETTINGS & CONSTANTS
# ==========================================
TOKEN = "8668588568:AAG3sXobv5NiAdFu9aHuc9nSoX-O7EEs_4E"
SUPER_ADMINS =[8668588568, 6915992397] 
DB_NAME = "social_task.db"
REQUIRED_CHANNEL = "@sc_task" 

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==========================================
# 2. DATABASE ARCHITECTURE
# ==========================================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, lang TEXT DEFAULT 'en',
            balance REAL DEFAULT 50.0, tasks_done INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0,
            phone TEXT, region TEXT DEFAULT 'Global', clicks INTEGER DEFAULT 0)''')
            
        await db.execute('''CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER, 
            category TEXT, target_region TEXT DEFAULT 'Global', link TEXT, conditions TEXT DEFAULT 'None',
            reward REAL, total_slots INTEGER, completed_slots INTEGER DEFAULT 0, status TEXT DEFAULT 'active')''')
            
        await db.execute('''CREATE TABLE IF NOT EXISTS submissions (
            sub_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, 
            worker_id INTEGER, file_id TEXT, status TEXT DEFAULT 'pending')''')

        await db.execute('''CREATE TABLE IF NOT EXISTS notifications (
            notif_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, message TEXT, is_read INTEGER DEFAULT 0)''')

        await db.execute('''CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY, min_sc_std REAL DEFAULT 15.0, min_sc_cond REAL DEFAULT 50.0,
            rate_ngn REAL DEFAULT 1.5, ai_mode INTEGER DEFAULT 0, gemini_key TEXT,
            maint_mode INTEGER DEFAULT 0, instructions TEXT DEFAULT 'Welcome! Do tasks to earn SC.',
            adsense_link TEXT DEFAULT 'https://google.com', adsense_reward REAL DEFAULT 10,
            monetag_link TEXT DEFAULT 'https://monetag.com', monetag_reward REAL DEFAULT 5, ad_freq INTEGER DEFAULT 5)''')

        # Insert defaults safely
        await db.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
        await db.commit()

# ==========================================
# 3. STATES
# ==========================================
class TaskCreate(StatesGroup):
    category = State(); action = State(); region = State(); link = State(); conditions = State(); reward = State(); slots = State()
class SupportState(StatesGroup): typing_msg = State()
class DepositState(StatesGroup): waiting_for_receipt = State()
class AdminState(StatesGroup):
    broadcast = State(); user_lookup = State(); gift_amount = State(); set_ai_key = State(); edit_ad = State()

# ==========================================
# 4. HELPER FUNCTIONS (AI, TRANSLATE, MENUS)
# ==========================================
async def translate_text(text, target_lang):
    if target_lang == 'en' or not target_lang: return text
    try: return await asyncio.to_thread(GoogleTranslator(source='auto', target=target_lang).translate, text)
    except: return text

async def ai_reply(message_text, db):
    async with db.execute("SELECT gemini_key FROM settings WHERE id = 1") as cur:
        key = (await cur.fetchone())[0]
    if not key: return "🤖 AI is currently sleeping. An admin will reply soon!"
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-pro')
        response = await asyncio.to_thread(model.generate_content, f"You are customer support for 'SOCIAL TASK', a microtask bot. User asks: {message_text}")
        return response.text
    except Exception as e:
        return "🤖 AI System busy. Forwarding to humans!"

async def get_main_menu(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,)) as cur:
            unread = (await cur.fetchone())[0]
    notif_btn = f"🔔 Notifications (+{unread})" if unread > 0 else "🔔 Notifications"
    kb = [[KeyboardButton(text="🚀 Browse Tasks"), KeyboardButton(text="➕ Create Task")],[KeyboardButton(text=notif_btn), KeyboardButton(text="💰 Wallet")],[KeyboardButton(text="📺 View Ads"), KeyboardButton(text="💬 Support")]]
    if user_id in SUPER_ADMINS: kb.append([KeyboardButton(text="👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ==========================================
# 5. START & AUTO-REGION DETECT
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear() 
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    lang = message.from_user.language_code[:2] if message.from_user.language_code else "en"
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username, lang) VALUES (?, ?, ?)", (user_id, username, lang))
        await db.execute("UPDATE users SET username = ?, lang = ? WHERE user_id = ?", (username, lang, user_id))
        await db.commit()
        
    welcome = await translate_text("👋 Welcome to SOCIAL TASK!\nEarn SC by completing tasks.", lang)
    await message.answer(welcome, reply_markup=await get_main_menu(user_id))

@dp.message(F.contact)
async def get_contact(message: types.Message):
    phone = message.contact.phone_number
    if phone.startswith("+234") or phone.startswith("234"): region = "Africa"
    elif phone.startswith("+44") or phone.startswith("+49"): region = "Europe"
    elif phone.startswith("+1"): region = "Americas"
    elif phone.startswith("+91") or phone.startswith("+86"): region = "Asia"
    else: region = "Global"
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET phone = ?, region = ? WHERE user_id = ?", (phone, region, message.from_user.id))
        await db.commit()
    await message.answer(f"✅ Region detected: <b>{region}</b>\nPayment methods unlocked!", reply_markup=await get_main_menu(message.from_user.id), parse_mode="HTML")

# ==========================================
# 6. ADSENSE & WALLET DEPOSITS
# ==========================================
@dp.message(F.text == "📺 View Ads")
async def view_adsense(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT adsense_link, adsense_reward FROM settings WHERE id = 1") as cur:
            link, reward = await cur.fetchone()
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, message.from_user.id))
        await db.commit()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 View Ad / Article", url=link)]])
    await message.answer(f"✅ <b>{reward} SC Added!</b>\nPlease support us by visiting the sponsor below:", reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "💰 Wallet")
async def btn_wallet(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT balance, region FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
            user = await cur.fetchone()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Deposit SC via Receipt", callback_data="buy_sc")]])
    await message.answer(f"💳 <b>Wallet</b>\n💰 <b>Balance:</b> {user[0]} SC\n🌍 <b>Region:</b> {user[1]}", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "buy_sc")
async def buy_sc_menu(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(DepositState.waiting_for_receipt)
    msg = (
        "💳 <b>BUY SC COINS (MANUAL DEPOSIT)</b>\n\n"
        "🇳🇬 <b>Naira (NGN):</b> Send to Bank X (1000 NGN = 1500 SC)\n"
        "💵 <b>USDT (TRC20):</b> Send to Wallet Y (1 USDT = 1000 SC)\n\n"
        "📸 <b>STEP 2:</b> After transferring, upload the screenshot of your receipt here."
    )
    await call.message.answer(msg, parse_mode="HTML")

@dp.message(DepositState.waiting_for_receipt, F.photo)
async def process_receipt(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    user_id = message.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve 1000 SC", callback_data=f"dep_app_{user_id}_1000")],[InlineKeyboardButton(text="❌ Reject", callback_data=f"dep_rej_{user_id}")]])
    for admin in SUPER_ADMINS:
        try: await bot.send_photo(admin, photo=file_id, caption=f"🚨 <b>NEW DEPOSIT RECEIPT</b>\nFrom: {user_id}", reply_markup=kb, parse_mode="HTML")
        except: pass
    await state.clear()
    await message.answer("✅ Receipt sent to Admins. Your SC will be credited soon!")

@dp.callback_query(F.data.startswith("dep_"))
async def admin_deposit_handler(call: types.CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS: return
    parts = call.data.split("_")
    action, user_id = parts[1], parts[2]
    
    if action == "app":
        amount = float(parts[3])
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            await db.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (user_id, f"✅ DEPOSIT APPROVED: {amount} SC added!"))
            await db.commit()
        await call.message.edit_caption(caption="✅ Deposit Approved.")
    else:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (user_id, f"❌ DEPOSIT REJECTED: Your receipt was invalid."))
            await db.commit()
        await call.message.edit_caption(caption="❌ Deposit Rejected.")

# ==========================================
# 8. CREATE & BROWSE TASKS (SORT & REGION)
# ==========================================
@dp.message(F.text == "➕ Create Task")
async def create_task(message: types.Message, state: FSMContext):
    await state.set_state(TaskCreate.category)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 Website", callback_data="cat_Website"), InlineKeyboardButton(text="📱 Telegram", callback_data="cat_Telegram")]])
    await message.answer("Select Platform:", reply_markup=kb)

@dp.callback_query(TaskCreate.category)
async def task_cat(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(cat=call.data.split("_")[1])
    await state.set_state(TaskCreate.region)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌍 Global", callback_data="reg_Global"), InlineKeyboardButton(text="🌍 Africa", callback_data="reg_Africa")],[InlineKeyboardButton(text="🌏 Asia", callback_data="reg_Asia"), InlineKeyboardButton(text="🌎 Americas", callback_data="reg_Americas")]])
    await call.message.edit_text("🎯 Target Region:", reply_markup=kb)

@dp.callback_query(TaskCreate.region)
async def task_reg(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(reg=call.data.split("_")[1])
    await state.set_state(TaskCreate.link)
    await call.message.edit_text("🔗 Send the Clickable Link/URL:")

@dp.message(TaskCreate.link)
async def task_link(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    await state.set_state(TaskCreate.reward)
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT min_sc_std FROM settings") as cur:
            m = (await cur.fetchone())[0]
    await message.answer(f"💰 Reward per person? (Minimum {m} SC):")

@dp.message(TaskCreate.reward)
async def task_rew(message: types.Message, state: FSMContext):
    await state.update_data(rew=float(message.text))
    await state.set_state(TaskCreate.slots)
    await message.answer("👥 How many people do you need?")

@dp.message(TaskCreate.slots)
async def task_fin(message: types.Message, state: FSMContext):
    slots = int(message.text)
    data = await state.get_data()
    total = data['rew'] * slots
    user_id = message.from_user.id
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total, user_id))
        await db.execute("INSERT INTO tasks (creator_id, category, target_region, link, reward, total_slots) VALUES (?, ?, ?, ?, ?, ?)", 
                         (user_id, data['cat'], data['reg'], data['link'], data['rew'], slots))
        await db.commit()
    await state.clear()
    await message.answer("✅ Task Created successfully!")

@dp.message(F.text == "🚀 Browse Tasks")
async def browse_tasks(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang, region FROM users WHERE user_id = ?", (user_id,)) as cur:
            u = await cur.fetchone()
            lang = u[0] if u else "en"
            u_reg = u[1] if u else "Global"

        query = f'''SELECT task_id, category, link, reward, conditions FROM tasks 
                   WHERE creator_id != ? AND completed_slots < total_slots AND status = 'active'
                   AND (target_region = 'Global' OR target_region = ?)
                   AND task_id NOT IN (SELECT task_id FROM submissions WHERE worker_id = ?) 
                   ORDER BY (creator_id IN ({",".join(map(str, SUPER_ADMINS))})) DESC, reward DESC LIMIT 1'''
        async with db.execute(query, (user_id, u_reg, user_id)) as cursor:
            task = await cursor.fetchone()

    if not task: return await message.answer(await translate_text("📋 No tasks available.", lang))
    t_id, cat, link, reward, cond = task
    cat_t = await translate_text(cat, lang)
    cond_t = await translate_text(cond, lang)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Open Task Link", url=link)],[InlineKeyboardButton(text="📸 Submit Screenshot", callback_data=f"submit_{t_id}")]])
    await message.answer(f"🎯 <b>TASK AVAILABLE</b>\n📌 <b>Category:</b> {cat_t}\n💰 <b>Reward:</b> {reward} SC\n⚠️ <b>Conditions:</b> {cond_t}", reply_markup=kb, parse_mode="HTML")

# ==========================================
# 9. GOD MODE ADMIN (ADS, BROADCAST, USERS)
# ==========================================
@dp.message(F.text == "👑 Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id not in SUPER_ADMINS: return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Broadcast", callback_data="adm_broad"), InlineKeyboardButton(text="👤 Users", callback_data="adm_users")],[InlineKeyboardButton(text="🤖 AI Settings", callback_data="adm_ai"), InlineKeyboardButton(text="📺 Ad Settings", callback_data="adm_ads")],[InlineKeyboardButton(text="🚧 Toggle Maintenance", callback_data="adm_maint")]
    ])
    await message.answer("👑 <b>ADMIN PANEL</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("adm_"))
async def adm_router(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split("_")[1]
    
    if action == "broad":
        await state.set_state(AdminState.broadcast)
        await call.message.answer("📢 Type the message to broadcast:")
        
    elif action == "users":
        await state.set_state(AdminState.user_lookup)
        await call.message.answer("👤 Enter User ID or @username:")
        
    elif action == "ai":
        await state.set_state(AdminState.set_ai_key)
        await call.message.answer("🤖 Paste Gemini API Key (or type 'ON'/'OFF'):")
        
    elif action == "maint":
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT maint_mode FROM settings") as cur:
                mode = (await cur.fetchone())[0]
            new_mode = 1 if mode == 0 else 0
            await db.execute("UPDATE settings SET maint_mode = ?", (new_mode,))
            await db.commit()
        status = "ON (Paused)" if new_mode == 1 else "OFF (Active)"
        await call.message.edit_text(f"✅ Maintenance Mode is <b>{status}</b>.", parse_mode="HTML")
        
    elif action == "ads":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 Edit AdSense Link", callback_data="editad_alink"), InlineKeyboardButton(text="💰 AdSense Reward", callback_data="editad_arew")],[InlineKeyboardButton(text="🎁 Edit Monetag Link", callback_data="editad_mlink"), InlineKeyboardButton(text="💰 Monetag Reward", callback_data="editad_mrew")],
            [InlineKeyboardButton(text="⏱️ Ad Frequency (Clicks)", callback_data="editad_freq")]
        ])
        await call.message.answer("📺 <b>ADVERTISING DASHBOARD</b>\nChoose a setting to edit:", reply_markup=kb, parse_mode="HTML")

# --- AD DASHBOARD EDITING ---
@dp.callback_query(F.data.startswith("editad_"))
async def edit_ad_setting(call: types.CallbackQuery, state: FSMContext):
    setting = call.data.split("_")[1]
    await state.update_data(setting_to_edit=setting)
    await state.set_state(AdminState.edit_ad)
    await call.message.answer("📝 Send the new value:")

@dp.message(AdminState.edit_ad)
async def save_ad_setting(message: types.Message, state: FSMContext):
    data = await state.get_data()
    setting = data['setting_to_edit']
    val = message.text
    
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            if setting == "alink": await db.execute("UPDATE settings SET adsense_link = ?", (val,))
            elif setting == "arew": await db.execute("UPDATE settings SET adsense_reward = ?", (float(val),))
            elif setting == "mlink": await db.execute("UPDATE settings SET monetag_link = ?", (val,))
            elif setting == "mrew": await db.execute("UPDATE settings SET monetag_reward = ?", (float(val),))
            elif setting == "freq": await db.execute("UPDATE settings SET ad_freq = ?", (int(val),))
            await db.commit()
            await message.answer(f"✅ Ad setting `{setting}` updated to: {val}")
        except:
            await message.answer("❌ Error: Invalid format (Did you send a letter instead of a number?).")
    await state.clear()

# --- OTHER ADMIN ACTIONS ---
@dp.message(AdminState.broadcast)
async def do_broadcast(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO notifications (user_id, message) SELECT user_id, ? FROM users", (f"📢 BROADCAST:\n{message.text}",))
        await db.commit()
    await state.clear()
    await message.answer("✅ Broadcast queued for all users!")

@dp.message(AdminState.user_lookup)
async def user_lookup(message: types.Message, state: FSMContext):
    target = message.text.replace("@", "")
    async with aiosqlite.connect(DB_NAME) as db:
        q = "SELECT user_id, username, balance, region, tasks_done FROM users WHERE user_id = ? OR username = ?"
        async with db.execute(q, (target, target)) as cur:
            u = await cur.fetchone()
    if not u: return await message.answer("❌ User not found.")
    await state.update_data(target_id=u[0])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Gift SC", callback_data="do_gift"), InlineKeyboardButton(text="🔨 Ban User", callback_data=f"do_ban_{u[0]}")]])
    await message.answer(f"👤 <b>USER FOUND</b>\nID: {u[0]}\nUser: @{u[1]}\nBalance: {u[2]} SC\nTasks: {u[4]}", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "do_gift")
async def start_gift(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.gift_amount)
    await call.message.answer("💰 Enter amount to gift:")

@dp.message(AdminState.gift_amount)
async def execute_gift(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(message.text), data['target_id']))
        await db.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (data['target_id'], f"🎁 ADMIN GIFT: {message.text} SC!"))
        await db.commit()
    await state.clear()
    await message.answer("✅ Gift Sent!")

# ==========================================
# 10. RUN THE BOT
# ==========================================
async def main():
    await init_db()
    keep_alive()  
    print("✅ V8 ONLINE: AD DASHBOARD & MAINTENANCE INCLUDED!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
