import asyncio
import aiosqlite
import os
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from keep_alive import keep_alive

# ==========================================
# 1. BOT SETTINGS
# ==========================================
TOKEN = "8668588568:AAG3sXobv5NiAdFu9aHuc9nSoX-O7EEs_4E"
SUPER_ADMINS = [8668588568, 6915992397] 
DB_NAME = "piar_v15.db" 
REQUIRED_CHANNEL = "@sc_task" 

bot = Bot(token=TOKEN)
dp = Dispatcher()
ADMINS_STR = ",".join(map(str, SUPER_ADMINS))

# ==========================================
# 2. DATABASE ARCHITECTURE
# ==========================================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0, 
            is_banned INTEGER DEFAULT 0, clicks INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0)''')
            
        await db.execute('''CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER, 
            category TEXT, target TEXT, conditions TEXT DEFAULT 'None', reward REAL, total_slots INTEGER, completed_slots INTEGER DEFAULT 0)''')
            
        await db.execute('''CREATE TABLE IF NOT EXISTS completed_tasks (
            user_id INTEGER, task_id INTEGER, status TEXT, PRIMARY KEY(user_id, task_id))''')

        await db.execute('''CREATE TABLE IF NOT EXISTS submissions (
            sub_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, 
            worker_id INTEGER, file_id TEXT, status TEXT DEFAULT 'pending')''')

        await db.execute('''CREATE TABLE IF NOT EXISTS notifications (
            notif_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
            message TEXT, is_read INTEGER DEFAULT 0)''')

        await db.execute('''CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY, monetag_link TEXT DEFAULT 'https://monetag.com', 
            monetag_reward REAL DEFAULT 5, ad_freq INTEGER DEFAULT 5,
            adsense_link TEXT DEFAULT 'https://google.com', adsense_reward REAL DEFAULT 10,
            welcome_bonus REAL DEFAULT 50.0, ref_bonus REAL DEFAULT 20.0, min_sc REAL DEFAULT 15.0, maint_mode INTEGER DEFAULT 0)''')

        await db.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
        await db.commit()

# ==========================================
# 3. STATES & MENUS
# ==========================================
class PromoteState(StatesGroup):
    category = State(); target = State(); conditions = State(); reward = State(); slots = State()
class SubmitState(StatesGroup): waiting_for_photo = State()
class AdminState(StatesGroup): waiting_for_input = State()
class SupportState(StatesGroup): typing_msg = State()
class AdminReplyState(StatesGroup): typing_reply = State(); target_user = State()
class AppealState(StatesGroup): typing_reason = State(); task_id = State(); worker_id = State()
class DepositState(StatesGroup): waiting_for_receipt = State()

async def get_main_menu(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,)) as cur:
            unread = (await cur.fetchone())[0]
            
    notif_btn = f"🔔 Notifications (+{unread})" if unread > 0 else "🔔 Notifications"
    
    kb = [[KeyboardButton(text="💸 Earn"), KeyboardButton(text="📢 Promote")],[KeyboardButton(text="👤 Profile"), KeyboardButton(text="🤝 Partners")],[KeyboardButton(text=notif_btn), KeyboardButton(text="📺 View Ads (Bonus)")],
        [KeyboardButton(text="💬 Support")]
    ]
          
    if user_id in SUPER_ADMINS: 
        kb.append([KeyboardButton(text="👑 Admin Panel")])
        
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_categories_kb():
    kb =[[InlineKeyboardButton(text="📱 Telegram", callback_data="catmenu_Telegram"), InlineKeyboardButton(text="🐦 X (Twitter)", callback_data="catmenu_X")],[InlineKeyboardButton(text="📸 Instagram", callback_data="catmenu_Instagram"), InlineKeyboardButton(text="▶️ YouTube", callback_data="catmenu_YouTube")],[InlineKeyboardButton(text="📘 Facebook", callback_data="catmenu_Facebook"), InlineKeyboardButton(text="💬 WhatsApp", callback_data="catmenu_WhatsApp")],[InlineKeyboardButton(text="🎵 TikTok", callback_data="catmenu_TikTok"), InlineKeyboardButton(text="🌐 Website/Other", callback_data="catmenu_Website")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def check_membership(user_id):
    if user_id in SUPER_ADMINS: 
        return True 
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: 
        return False 

# ==========================================
# 4. MASTER MIDDLEWARE (Monetag & Bans)
# ==========================================
class MasterMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.Update, data: dict):
        user_id = event.message.from_user.id if event.message else event.callback_query.from_user.id
        username = event.message.from_user.username if event.message else event.callback_query.from_user.username
        
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cur:
                u = await cur.fetchone()
                if u and u[0] == 1: 
                    return 
                    
            async with db.execute("SELECT maint_mode, ad_freq, monetag_link, monetag_reward FROM settings WHERE id = 1") as cur:
                settings = await cur.fetchone()
                
            if settings[0] == 1 and user_id not in SUPER_ADMINS:
                if event.message: 
                    await event.message.answer("🚧 <b>MAINTENANCE MODE</b>\nBot paused by Admin.", parse_mode="HTML")
                else: 
                    await event.callback_query.answer("🚧 Bot is under maintenance!", show_alert=True)
                return 

            if event.message and event.message.text and not event.message.text.startswith("/"):
                await db.execute("UPDATE users SET clicks = clicks + 1, username = ? WHERE user_id = ?", (username, user_id))
                async with db.execute("SELECT clicks FROM users WHERE user_id = ?", (user_id,)) as cur: 
                    clicks = (await cur.fetchone())[0]
                    
                if clicks % settings[1] == 0:
                    await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (settings[3], user_id))
                    await db.commit()
                    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Claim Bonus to Continue", url=settings[2])]])
                    await event.message.answer(f"🎉 <b>AUTOMATIC BONUS!</b>\n\nYou earned {settings[3]} SC from our sponsor! Click below to continue.", reply_markup=kb, parse_mode="HTML")
                    return 
            await db.commit()
        return await handler(event, data)

dp.update.outer_middleware(MasterMiddleware())

# ==========================================
# 5. START SYSTEM
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    referrer_id = None
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit(): 
        referrer_id = int(args[1])
    
    if not await check_membership(user_id):
        kb = [[InlineKeyboardButton(text="📢 Join Official Channel", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],[InlineKeyboardButton(text="✅ Verify Join", callback_data="check_join")]]
        return await message.answer("🛑 <b>VERIFICATION REQUIRED</b>\n\nYou must join our official channel to use this bot!", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur: 
            exists = await cur.fetchone()
            
        if not exists:
            async with db.execute("SELECT welcome_bonus, ref_bonus FROM settings WHERE id = 1") as cur: 
                bonuses = await cur.fetchone()
                
            await db.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)", (user_id, username, bonuses[0]))
            
            if referrer_id and referrer_id != user_id:
                await db.execute("UPDATE users SET balance = balance + ?, referrals = referrals + 1 WHERE user_id = ?", (bonuses[1], referrer_id))
                await db.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (referrer_id, f"🎉 REFERRAL BONUS: You earned {bonuses[1]} SC because someone joined using your link!"))
            await db.commit()
            
    await message.answer("👋 Welcome to <b>SOCIAL TASK</b>!", reply_markup=await get_main_menu(user_id), parse_mode="HTML")

@dp.callback_query(F.data == "check_join")
async def verify_join(call: types.CallbackQuery):
    if await check_membership(call.from_user.id):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT welcome_bonus FROM settings WHERE id = 1") as cur: 
                bonus = (await cur.fetchone())[0]
            await db.execute("INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, ?)", (call.from_user.id, call.from_user.username, bonus))
            await db.commit()
        await call.message.delete()
        await call.message.answer("✅ <b>Verified!</b>", reply_markup=await get_main_menu(call.from_user.id), parse_mode="HTML")
    else: 
        await call.answer("❌ You haven't joined the channel yet!", show_alert=True)

# ==========================================
# 6. ANONYMOUS SUPPORT & APPEALS SYSTEM
# ==========================================
@dp.message(F.text == "💬 Support")
async def support_menu(message: types.Message, state: FSMContext):
    await state.set_state(SupportState.typing_msg)
    await message.answer("💬 <b>Live Support</b>\n\nPlease type your message/question below. An admin will respond anonymously:", parse_mode="HTML")

@dp.message(SupportState.typing_msg)
async def support_msg(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("↩️ Reply", callback_data=f"sup_rep_{user_id}")]])
    for admin in SUPER_ADMINS:
        try: 
            await bot.send_message(admin, f"📩 <b>NEW SUPPORT TICKET</b>\nFrom ID: <code>{user_id}</code>\n\n{message.text}", reply_markup=kb, parse_mode="HTML")
        except: 
            pass
    await state.clear()
    await message.answer("✅ Message sent to Admin securely.")

@dp.callback_query(F.data.startswith("sup_rep_"))
async def support_reply_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in SUPER_ADMINS: 
        return
    user_id = call.data.split("_")[2]
    await state.set_state(AdminReplyState.typing_reply)
    await state.update_data(target_user=user_id)
    await call.message.answer(f"⌨️ Type your anonymous reply to User {user_id}:")

@dp.message(AdminReplyState.typing_reply)
async def support_reply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target = data['target_user']
    try:
        await bot.send_message(target, f"👨‍💻 <b>ADMIN SUPPORT:</b>\n\n{message.text}", parse_mode="HTML")
        await message.answer("✅ Reply sent to user anonymously.")
    except: 
        await message.answer("❌ Failed. User blocked the bot.")
    await state.clear()

@dp.callback_query(F.data.startswith("appeal_"))
async def start_appeal(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    await state.set_state(AppealState.typing_reason)
    await state.update_data(task_id=parts[1], worker_id=parts[2])
    await call.message.answer("⚖️ <b>File an Appeal</b>\nPlease type why you think your task was unfairly rejected. Admin will review your screenshot manually:", parse_mode="HTML")

@dp.message(AppealState.typing_reason)
async def send_appeal(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id, worker_id, reason = data['task_id'], data['worker_id'], message.text
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT file_id FROM submissions WHERE task_id = ? AND worker_id = ?", (task_id, worker_id)) as cur: 
            sub = await cur.fetchone()
    
    if sub:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("✅ Force Approve", callback_data=f"adm_app_appeal_{task_id}_{worker_id}"), InlineKeyboardButton("❌ Reject Appeal", callback_data=f"adm_rej_appeal_{task_id}_{worker_id}")]])
        for admin in SUPER_ADMINS:
            try: 
                await bot.send_photo(admin, photo=sub[0], caption=f"🚨 <b>NEW APPEAL</b>\nTask ID: {task_id}\nWorker: {worker_id}\n\n💬 <b>Worker's Defense:</b> {reason}", reply_markup=kb, parse_mode="HTML")
            except: 
                pass
            
    await state.clear()
    await message.answer("✅ Appeal sent to Admin. You will be notified of the Supreme Court decision!")

@dp.callback_query(F.data.startswith("adm_app_appeal_") | F.data.startswith("adm_rej_appeal_"))
async def resolve_appeal(call: types.CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS: 
        return
    action = "approve" if "app_appeal" in call.data else "reject"
    parts = call.data.split("_")
    task_id, worker_id = parts[3], parts[4]

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT reward, category FROM tasks WHERE task_id = ?", (task_id,)) as cur: 
            task = await cur.fetchone()
        async with db.execute("SELECT status FROM submissions WHERE task_id = ? AND worker_id = ?", (task_id, worker_id)) as cur: 
            sub = await cur.fetchone()
        
        if action == "approve":
            if sub and sub[0] != 'approved':
                await db.execute("UPDATE submissions SET status = 'approved' WHERE task_id = ? AND worker_id = ?", (task_id, worker_id))
                await db.execute("UPDATE tasks SET completed_slots = completed_slots + 1 WHERE task_id = ?", (task_id,))
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (task[0], worker_id))
                await db.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (worker_id, f"⚖️ APPEAL WON: Admin forced approval for '{task[1]}'. You earned {task[0]} SC!"))
                await call.message.edit_caption(caption="✅ Appeal Force-Approved.")
            else: 
                await call.message.edit_caption(caption="⚠️ Already approved previously.")
        else:
            await db.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (worker_id, f"⚖️ APPEAL LOST: Admin reviewed your screenshot for '{task[1]}' and upheld the rejection."))
            await call.message.edit_caption(caption="❌ Appeal Denied.")
        await db.commit()

# ==========================================
# 7. 👑 GOD MODE ADMIN PANEL
# ==========================================
@dp.message(F.text == "👑 Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id not in SUPER_ADMINS: 
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT maint_mode FROM settings WHERE id = 1") as cur: 
            maint = (await cur.fetchone())[0]
            
    maint_text = "🟢 Turn Maint. ON" if maint == 0 else "🔴 Turn Maint. OFF"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📊 Platform Statistics", callback_data="adm_stats")],[InlineKeyboardButton(text="💸 Edit Economy Rates", callback_data="adm_menu_eco"), InlineKeyboardButton(text="📺 Edit Ad Settings", callback_data="adm_menu_ads")],[InlineKeyboardButton(text="👤 User Manager (Gift/Ban)", callback_data="adm_menu_users"), InlineKeyboardButton(text="📢 Global Broadcast", callback_data="adm_action_broadcast")],[InlineKeyboardButton(text=maint_text, callback_data="adm_maint")]
    ])
    await message.answer("👑 <b>GOD MODE DASHBOARD</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "adm_stats")
async def admin_stats(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*), SUM(balance) FROM users") as cur: 
            users_data = await cur.fetchone()
        async with db.execute("SELECT COUNT(*), SUM(completed_slots) FROM tasks") as cur: 
            tasks_data = await cur.fetchone()
            
    msg = (f"📊 <b>PLATFORM STATISTICS</b>\n\n👥 <b>Total Users:</b> {users_data[0]}\n💰 <b>Total SC:</b> {users_data[1] or 0}\n\n📋 <b>Tasks Created:</b> {tasks_data[0]}\n✅ <b>Tasks Completed:</b> {tasks_data[1] or 0}")
    await call.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("⬅️ Back", callback_data="adm_back")]]), parse_mode="HTML")

@dp.callback_query(F.data.startswith("adm_menu_"))
async def admin_submenus(call: types.CallbackQuery):
    menu = call.data.split("_")[2]
    if menu == "eco":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Welcome Bonus", callback_data="adm_action_set_welcome"), InlineKeyboardButton(text="🤝 Referral Bonus", callback_data="adm_action_set_ref")],[InlineKeyboardButton(text="📈 Minimum Task SC", callback_data="adm_action_set_min")],[InlineKeyboardButton("⬅️ Back", callback_data="adm_back")]
        ])
        await call.message.edit_text("💸 <b>Economy Settings:</b>", reply_markup=kb, parse_mode="HTML")
    elif menu == "ads":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📺 AdSense Link", callback_data="adm_action_set_adsense_link"), InlineKeyboardButton(text="💰 AdSense Reward", callback_data="adm_action_set_adsense_rew")],[InlineKeyboardButton(text="🖱 Monetag Link", callback_data="adm_action_set_monetag_link"), InlineKeyboardButton(text="💰 Monetag Reward", callback_data="adm_action_set_monetag_rew")],[InlineKeyboardButton(text="⏱ Monetag Frequency", callback_data="adm_action_set_monetag_freq")],
            [InlineKeyboardButton("⬅️ Back", callback_data="adm_back")]
        ])
        await call.message.edit_text("📺 <b>Ad Settings:</b>", reply_markup=kb, parse_mode="HTML")
    elif menu == "users":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Gift SC", callback_data="adm_action_gift"), InlineKeyboardButton(text="🔨 Ban/Unban", callback_data="adm_action_ban")],[InlineKeyboardButton("⬅️ Back", callback_data="adm_back")]
        ])
        await call.message.edit_text("👤 <b>User Management:</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "adm_back")
async def admin_back(call: types.CallbackQuery):
    await call.message.delete()
    await admin_panel(call.message)

@dp.callback_query(F.data.startswith("adm_action_"))
async def admin_actions(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split("_", 2)[2]
    await state.set_state(AdminState.waiting_for_input)
    await state.update_data(action=action)
    
    prompts = {
        "set_welcome": "💰 Enter new Welcome Bonus:", 
        "set_ref": "🤝 Enter new Referral Bonus:", 
        "set_min": "📈 Enter new Minimum Task SC:", 
        "set_adsense_link": "📺 Enter new AdSense URL:", 
        "set_adsense_rew": "💰 Enter SC reward for AdSense:", 
        "set_monetag_link": "🖱 Enter new Monetag URL:", 
        "set_monetag_rew": "💰 Enter SC reward for Monetag:", 
        "set_monetag_freq": "⏱ Enter clicks needed before Monetag pops up:", 
        "gift": "🎁 Reply with: `ID Amount` OR `@username Amount`", 
        "ban": "🔨 Reply with `ID` or `@username` to toggle Ban:", 
        "broadcast": "📢 Type message to broadcast to ALL users:"
    }
    await call.message.answer(prompts[action], parse_mode="Markdown")

@dp.message(AdminState.waiting_for_input)
async def admin_process_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    action = data['action']
    text = message.text
    
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            if action == "set_welcome": 
                await db.execute("UPDATE settings SET welcome_bonus = ? WHERE id = 1", (float(text),))
            elif action == "set_ref": 
                await db.execute("UPDATE settings SET ref_bonus = ? WHERE id = 1", (float(text),))
            elif action == "set_min": 
                await db.execute("UPDATE settings SET min_sc = ? WHERE id = 1", (float(text),))
            elif action == "set_adsense_link": 
                await db.execute("UPDATE settings SET adsense_link = ? WHERE id = 1", (text,))
            elif action == "set_adsense_rew": 
                await db.execute("UPDATE settings SET adsense_reward = ? WHERE id = 1", (float(text),))
            elif action == "set_monetag_link": 
                await db.execute("UPDATE settings SET monetag_link = ? WHERE id = 1", (text,))
            elif action == "set_monetag_rew": 
                await db.execute("UPDATE settings SET monetag_reward = ? WHERE id = 1", (float(text),))
            elif action == "set_monetag_freq": 
                await db.execute("UPDATE settings SET ad_freq = ? WHERE id = 1", (int(text),))
            elif action == "gift":
                target, amount = text.split()
                target = target.replace("@", "")
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ? OR username = ?", (float(amount), target, target))
                await db.execute("INSERT INTO notifications (user_id, message) SELECT user_id, ? FROM users WHERE user_id = ? OR username = ?", (f"🎁 ADMIN GIFT: {amount} SC added to your wallet!", target, target))
            elif action == "ban":
                target = text.replace("@", "")
                async with db.execute("SELECT is_banned FROM users WHERE user_id = ? OR username = ?", (target, target)) as cur: 
                    current = (await cur.fetchone())[0]
                await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ? OR username = ?", (1 if current == 0 else 0, target, target))
            elif action == "broadcast": 
                await db.execute("INSERT INTO notifications (user_id, message) SELECT user_id, ? FROM users", (f"📢 BROADCAST:\n{text}",))
                
            await db.commit()
            await message.answer("✅ <b>Update Successful!</b>", parse_mode="HTML")
        except Exception as e: 
            await message.answer(f"❌ Error or invalid format. Try again.")
    await state.clear()

# ==========================================
# 8. EARN & REVIEW PROOFS
# ==========================================
@dp.message(F.text == "💸 Earn")
async def earn_menu(message: types.Message):
    await message.answer("💸 <b>Earn SC Coins</b>\nChoose a category:", reply_markup=get_categories_kb(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("catmenu_"))
async def fetch_task_list(call: types.CallbackQuery):
    category = call.data.split("_")[1]
    user_id = call.from_user.id
    
    async with aiosqlite.connect(DB_NAME) as db:
        query = f'''SELECT task_id, conditions, reward, creator_id FROM tasks 
                   WHERE category = ? AND creator_id != ? AND completed_slots < total_slots 
                   AND task_id NOT IN (SELECT task_id FROM completed_tasks WHERE user_id = ?) 
                   AND task_id NOT IN (SELECT task_id FROM submissions WHERE worker_id = ?) 
                   ORDER BY CASE WHEN creator_id IN ({ADMINS_STR}) THEN 1 ELSE 0 END DESC, reward DESC LIMIT 5'''
        async with db.execute(query, (category, user_id, user_id, user_id)) as cur: 
            tasks = await cur.fetchall()
            
    if not tasks: 
        return await call.message.edit_text(f"📭 No {category} tasks available right now.")

    kb =[]
    for t in tasks:
        task_id, cond, reward, creator_id = t
        cond_text = "Auto-Verify" if cond.lower() == "none" else cond[:15] + "..."
        star = "⭐ " if creator_id in SUPER_ADMINS else "" 
        kb.append([InlineKeyboardButton(text=f"{star}💰 {reward} SC | {cond_text}", callback_data=f"view_{task_id}_{category}")])
    
    await call.message.edit_text(f"🏆 <b>Top {category} Tasks</b>\nSelect a task:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@dp.callback_query(F.data.startswith("view_"))
async def view_task_btn(call: types.CallbackQuery):
    parts = call.data.split("_")
    task_id, category = int(parts[1]), parts[2]
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT target, conditions, reward FROM tasks WHERE task_id = ?", (task_id,)) as cur: 
            task = await cur.fetchone()
            
    target, conditions, reward = task
    link = target if target.startswith("http") else f"https://t.me/{target.replace('@', '')}"
    
    kb = [[InlineKeyboardButton(text="🔗 Go to Task", url=link)]]
    if category == "Telegram" and conditions.strip().lower() == "none":
        msg = f"📢 <b>Subscribe ({reward} SC)</b>\n\n1️⃣ Click 'Go to Task'\n2️⃣ Join\n3️⃣ Click '✅ Check'"
        kb.append([InlineKeyboardButton(text="✅ Check", callback_data=f"verify_{task_id}_{category}")])
    else:
        msg = f"📸 <b>{category} Task ({reward} SC)</b>\n\n⚠️ <b>Conditions:</b> {conditions}\n\n1️⃣ Complete task\n2️⃣ Click '📸 Send Screenshot'"
        kb.append([InlineKeyboardButton(text="📸 Send Screenshot", callback_data=f"submit_{task_id}_{category}")])

    kb.append([InlineKeyboardButton(text="⏭ Skip Task", callback_data=f"skip_{task_id}_{category}")])
    await call.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@dp.callback_query(F.data.startswith("skip_"))
async def skip_task(call: types.CallbackQuery):
    parts = call.data.split("_")
    task_id, category = int(parts[1]), parts[2]
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO completed_tasks (user_id, task_id, status) VALUES (?, ?, 'skipped')", (call.from_user.id, task_id))
        await db.commit()
    call.data = f"catmenu_{category}"
    await fetch_task_list(call)

# Auto Verify
@dp.callback_query(F.data.startswith("verify_"))
async def verify_task(call: types.CallbackQuery):
    parts = call.data.split("_")
    task_id, category = int(parts[1]), parts[2]
    user_id = call.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT target, reward FROM tasks WHERE task_id = ?", (task_id,)) as cur: 
            task = await cur.fetchone()
            
    try:
        member = await bot.get_chat_member(task[0], user_id)
        if member.status in['member', 'administrator', 'creator']:
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("INSERT INTO completed_tasks (user_id, task_id, status) VALUES (?, ?, 'completed')", (user_id, task_id))
                await db.execute("UPDATE tasks SET completed_slots = completed_slots + 1 WHERE task_id = ?", (task_id,))
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (task[1], user_id))
                await db.commit()
            await call.answer(f"✅ Success! You earned {task[1]} SC.", show_alert=True)
            await skip_task(call)
        else: 
            await call.answer("❌ You did not join!", show_alert=True)
    except Exception as e: 
        await call.answer("❌ Broken task. Admin removed bot.", show_alert=True)

# Screenshot Verify
@dp.callback_query(F.data.startswith("submit_"))
async def ask_for_screenshot(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    await state.set_state(SubmitState.waiting_for_photo)
    await state.update_data(task_id=parts[1], category=parts[2])
    await call.message.answer("📸 Upload your screenshot proof as a Photo:")
    await call.answer()

@dp.message(SubmitState.waiting_for_photo, F.photo)
async def handle_screenshot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id, category, worker_id = data['task_id'], data['category'], message.from_user.id
    file_id = message.photo[-1].file_id 
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO submissions (task_id, worker_id, file_id, status) VALUES (?, ?, ?, 'pending')", (task_id, worker_id, file_id))
        async with db.execute("SELECT creator_id, reward FROM tasks WHERE task_id = ?", (task_id,)) as cur: 
            creator = await cur.fetchone()
        await db.commit()

    await state.clear()
    await message.answer("✅ <b>Proof Submitted!</b>", parse_mode="HTML")

    if creator:
        creator_id, reward = creator
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve", callback_data=f"proof_app_{task_id}_{worker_id}"), InlineKeyboardButton(text="❌ Reject", callback_data=f"proof_rej_{task_id}_{worker_id}")]])
        try: 
            await bot.send_photo(creator_id, photo=file_id, caption=f"🔔 <b>New Proof ({category})</b>\n💰 <b>Reward:</b> {reward} SC\nReview:", reply_markup=kb, parse_mode="HTML")
        except: 
            pass
            
    mock_call = types.CallbackQuery(id="0", from_user=message.from_user, chat_instance="0", message=message, data=f"skip_{task_id}_{category}")
    await skip_task(mock_call)

@dp.callback_query(F.data.startswith("proof_"))
async def review_proof(call: types.CallbackQuery):
    parts = call.data.split("_")
    action, task_id, worker_id = parts[1], parts[2], parts[3]
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT reward, category FROM tasks WHERE task_id = ?", (task_id,)) as cur: 
            task = await cur.fetchone()
            
        if action == "app":
            await db.execute("UPDATE submissions SET status = 'approved' WHERE task_id = ? AND worker_id = ?", (task_id, worker_id))
            await db.execute("UPDATE tasks SET completed_slots = completed_slots + 1 WHERE task_id = ?", (task_id,))
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (task[0], worker_id))
            await db.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (worker_id, f"✅ APPROVED: You earned {task[0]} SC for '{task[1]}' task!"))
            await call.message.edit_caption(caption="✅ Proof Approved. Worker paid.")
        else:
            await db.execute("UPDATE submissions SET status = 'rejected' WHERE task_id = ? AND worker_id = ?", (task_id, worker_id))
            await db.execute("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (worker_id, f"❌ REJECTED: Your proof for '{task[1]}' task was rejected."))
            await call.message.edit_caption(caption="❌ Proof Rejected.")
            
            appeal_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚖️ Appeal Rejection", callback_data=f"appeal_{task_id}_{worker_id}")]])
            try: 
                await bot.send_message(worker_id, f"❌ Your task proof for '{task[1]}' was rejected.\n\nIf you believe this is an error, you can file an appeal to the Admin.", reply_markup=appeal_kb)
            except: 
                pass
                
        await db.commit()

# ==========================================
# 9. SMART PROMOTE ENGINE
# ==========================================
@dp.message(F.text == "📢 Promote")
async def promote_menu(message: types.Message):
    await message.answer("📢 <b>Create Campaign</b>\nChoose where to promote:", reply_markup=get_categories_kb(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("catmenu_"))
async def promote_start(call: types.CallbackQuery, state: FSMContext):
    if "Create Campaign" in call.message.text:
        category = call.data.split("_")[1]
        await state.update_data(category=category)
        await state.set_state(PromoteState.target)
        if category == "Telegram":
            await call.message.edit_text("⚠️ Add this bot as an Admin to your Channel/Group first!\n\nSend the @username:", parse_mode="HTML")
        else:
            await call.message.edit_text(f"🌐 Send the Link/URL for your {category} task:")

@dp.message(PromoteState.target)
async def promote_target(message: types.Message, state: FSMContext):
    target = message.text
    data = await state.get_data()
    
    if data['category'] == "Telegram" and not target.startswith("@"):
        return await message.answer("❌ Telegram targets must start with @")
        
    await state.update_data(target=target)
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT min_sc FROM settings WHERE id = 1") as cur: 
            base_min = (await cur.fetchone())[0]
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,)) as cur: 
            bal = (await cur.fetchone())[0]

    if data['category'] == "Telegram":
        if bal < base_min:
            await state.clear()
            return await message.answer(f"❌ <b>Low Balance!</b>\nMin cost is {base_min} SC.", parse_mode="HTML")
        await state.update_data(conditions="None", min_sc=base_min, bal=bal)
        await state.set_state(PromoteState.reward)
        await message.answer(f"💰 <b>Set Reward Price</b>\nMinimum price: <b>{base_min} SC</b>\nEnter price per person:", parse_mode="HTML")
    else:
        await state.set_state(PromoteState.conditions)
        await message.answer("📝 Any special conditions? (e.g. Upload screenshot)\n<i>If no conditions, type <b>None</b></i>", parse_mode="HTML")

@dp.message(PromoteState.conditions)
async def promote_conditions(message: types.Message, state: FSMContext):
    cond = message.text
    await state.update_data(conditions=cond)
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT min_sc FROM settings WHERE id = 1") as cur: 
            base_min = (await cur.fetchone())[0]
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,)) as cur: 
            bal = (await cur.fetchone())[0]
            
    min_sc = base_min if cond.strip().lower() == "none" else 50.0
    if bal < min_sc:
        await state.clear()
        return await message.answer(f"❌ <b>Low Balance!</b>\nMin cost is {min_sc} SC.", parse_mode="HTML")
        
    await state.update_data(min_sc=min_sc, bal=bal)
    await state.set_state(PromoteState.reward)
    await message.answer(f"💰 <b>Set Reward Price</b>\nMinimum price: <b>{min_sc} SC</b>\nEnter price per person:", parse_mode="HTML")

@dp.message(PromoteState.reward)
async def promote_reward(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        rew = float(message.text)
        if rew < data['min_sc']: 
            return await message.answer(f"❌ <b>Error:</b> Minimum is <b>{data['min_sc']} SC</b>.", parse_mode="HTML")
            
        max_slots = int(data['bal'] // rew)
        if max_slots < 1: 
            return await message.answer("❌ Insufficient Coins!")
            
        await state.update_data(reward=rew, max_slots=max_slots)
        await state.set_state(PromoteState.slots)
        await message.answer(f"✅ You can afford max <b>{max_slots} people</b>.\nHow many do you want?", parse_mode="HTML")
    except: 
        await message.answer("❌ Invalid number.")

@dp.message(PromoteState.slots)
async def promote_slots(message: types.Message, state: FSMContext):
    try:
        slots = int(message.text)
        data = await state.get_data()
        if slots < 1 or slots > data['max_slots']: 
            return await message.answer("❌ Invalid number.")
        
        cost = data['reward'] * slots
        user_id = message.from_user.id
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (cost, user_id))
            await db.execute("INSERT INTO tasks (creator_id, category, target, conditions, reward, total_slots) VALUES (?, ?, ?, ?, ?, ?)",
                             (user_id, data['category'], data['target'], data['conditions'], data['reward'], slots))
            await db.commit()
            
        await state.clear()
        await message.answer("✅ <b>Campaign Active!</b>", parse_mode="HTML")
        
        try:
            bot_info = await bot.get_me()
            channel_msg = f"🚀 <b>NEW {data['category'].upper()} TASK</b> 🚀\n💰 <b>Reward:</b> {data['reward']} SC\n👥 <b>Slots:</b> {slots}\n👉 Go to our bot to complete this task and earn SC!"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🤖 Open Bot", url=f"https://t.me/{bot_info.username}")]])
            await bot.send_message(REQUIRED_CHANNEL, channel_msg, reply_markup=kb, parse_mode="HTML")
        except Exception as e: 
            print(f"Failed to post to channel: {e}")
    except: 
        await message.answer("❌ Invalid number.")

# ==========================================
# 10. PROFILE, NOTIFICATIONS, PARTNERS & ADS
# ==========================================
@dp.message(F.text == "👤 Profile")
async def btn_profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT balance, referrals FROM users WHERE user_id = ?", (message.from_user.id,)) as cur: 
            user = await cur.fetchone()
            
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Buy SC Coins", callback_data="buy_coins")]])
    await message.answer(f"👤 <b>Your Profile</b>\n\n🆔 <b>ID:</b> {message.from_user.id}\n💰 <b>Balance:</b> {user[0]} SC\n👥 <b>Referrals:</b> {user[1]}", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "buy_coins")
async def buy_coins(call: types.CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT rate_usdt, rate_ngn FROM settings WHERE id = 1") as cur: 
            rates = await cur.fetchone()
            
    msg = f"🛒 <b>Buy SC Coins</b>\n\n💵 1 USDT = {rates[0]} SC\n🇳🇬 1 NGN = {rates[1]} SC\n\n📸 <b>To Deposit:</b> Transfer funds, then upload your receipt photo here!"
    await state.set_state(DepositState.waiting_for_receipt)
    await call.message.answer(msg, parse_mode="HTML")

@dp.message(DepositState.waiting_for_receipt, F.photo)
async def process_receipt(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    user_id = message.from_user.id
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve 1000 SC", callback_data=f"dep_app_{user_id}_1000")],[InlineKeyboardButton(text="❌ Reject", callback_data=f"dep_rej_{user_id}")]])
    for admin in SUPER_ADMINS:
        try: 
            await bot.send_photo(admin, photo=file_id, caption=f"🚨 <b>NEW DEPOSIT RECEIPT</b>\nFrom: {user_id}", reply_markup=kb, parse_mode="HTML")
        except: 
            pass
            
    await state.clear()
    await message.answer("✅ Receipt sent to Admins!")

@dp.callback_query(F.data.startswith("dep_"))
async def admin_deposit_handler(call: types.CallbackQuery):
    if call.from_user.id not in SUPER_ADMINS: 
        return
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
        await call.message.edit_caption(caption="❌ Deposit Rejected.")

@dp.message(F.text.contains("🔔 Notifications"))
async def view_notifications(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT notif_id, message FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,)) as cur: 
            notifs = await cur.fetchall()
            
        if not notifs: 
            return await message.answer("📭 You have no new notifications.", reply_markup=await get_main_menu(user_id))
            
        msg = "🔔 <b>NEW NOTIFICATIONS:</b>\n\n"
        for n in notifs:
            msg += f"🔸 {n[1]}\n\n"
            await db.execute("UPDATE notifications SET is_read = 1 WHERE notif_id = ?", (n[0],))
        await db.commit()
        
    await message.answer(msg, reply_markup=await get_main_menu(user_id), parse_mode="HTML")

@dp.message(F.text == "📺 View Ads (Bonus)")
async def view_adsense(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT adsense_link, adsense_reward FROM settings WHERE id = 1") as cur: 
            settings = await cur.fetchone()
            
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (settings[1], message.from_user.id))
        await db.commit()
        
    await message.answer(f"📺 Click below to view our sponsor and earn {settings[1]} SC instantly!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 View AdSense", url=settings[0])]]))

@dp.message(F.text == "🤝 Partners")
async def btn_referral(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT ref_bonus FROM settings WHERE id = 1") as cur: 
            ref_bonus = (await cur.fetchone())[0]
            
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={message.from_user.id}"
    await message.answer(f"🤝 <b>Partners Program</b>\n\nShare this link! When someone joins, you earn <b>{ref_bonus} SC</b>.\n\n🔗 <b>Your Link:</b> {ref_link}", parse_mode="HTML")

# ==========================================
# 11. RUN THE BOT
# ==========================================
async def main():
    await init_db()
    keep_alive()  
    print("✅ V15.1 ULTIMATE EDITION ONLINE: Strict Syntax Fixed & Appeals Active!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
