import os
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.exceptions import ChatNotFound

# ==============================
# CONFIG - Railway Environment Variables
# ==============================
API_TOKEN = os.getenv("BOT_TOKEN", "DEFAULT_BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "X_Reward_Bot")
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "X_Reward_botChannel")

# Coins Rewards
JOIN_REWARD = 100
REFERRAL_REWARD = 200
LIKE_REWARD = 50
COMMENT_REWARD = 80
REPOST_REWARD = 50
DAILY_REWARD = 50
ADS_REWARD = 100

# Boost Mode Settings
BOOST_ADS_REQUIRED = 3
BOOST_DURATION = 3600  # 1 hour in seconds

# Admin & Verifiers - Railway पर environment variables से set करें
ADMINS = list(map(int, os.getenv("ADMINS", "123456789").split(',')))
VERIFIERS = list(map(int, os.getenv("VERIFIERS", "987654321").split(',')))

# Mini App URL
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://x-reward-bot-mini.vercel.app")

# ==============================
# BOT SETUP
# ==============================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# ==============================
# DATABASE - Railway पर PostgreSQL का use करें
# ==============================
# SQLite के बजाय PostgreSQL connection (Railway पर)
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL:
    import psycopg2
    from urllib.parse import urlparse
    # PostgreSQL connection
    result = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )
    cursor = conn.cursor()
    
    # PostgreSQL के लिए CREATE TABLE statements
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        coins INTEGER DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        ref_code TEXT,
        boost_until INTEGER DEFAULT 0,
        joined_at INTEGER DEFAULT 0
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS ads (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        watched_at INTEGER
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS verifiers (
        user_id BIGINT PRIMARY KEY,
        added_by BIGINT,
        added_at INTEGER
    )''')
else:
    # Fallback to SQLite (local development)
    conn = sqlite3.connect("bot.db", check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        coins INTEGER DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        ref_code TEXT,
        boost_until INTEGER DEFAULT 0,
        joined_at INTEGER DEFAULT 0
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        watched_at INTEGER
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS verifiers (
        user_id INTEGER PRIMARY KEY,
        added_by INTEGER,
        added_at INTEGER
    )''')

# Initial verifiers डालें
for verifier_id in VERIFIERS:
    try:
        if DATABASE_URL:
            cursor.execute("INSERT INTO verifiers (user_id, added_by, added_at) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING", 
                          (verifier_id, ADMINS[0], int(time.time())))
        else:
            cursor.execute("INSERT OR IGNORE INTO verifiers (user_id, added_by, added_at) VALUES (?, ?, ?)", 
                          (verifier_id, ADMINS[0], int(time.time())))
    except Exception as e:
        logging.error(f"Error adding verifier: {e}")

conn.commit()

# ==============================
# FUNCTIONS
# ==============================
def get_user(user_id):
    if DATABASE_URL:
        cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    else:
        cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def add_user(user_id, ref_code=None):
    if not get_user(user_id):
        if not ref_code:
            ref_code = f"REF{user_id}{int(time.time())}"
        
        if DATABASE_URL:
            cursor.execute("INSERT INTO users (user_id, coins, referrals, ref_code, joined_at) VALUES (%s, 0, 0, %s, %s)", 
                          (user_id, ref_code, int(time.time())))
        else:
            cursor.execute("INSERT INTO users (user_id, coins, referrals, ref_code, joined_at) VALUES (?, 0, 0, ?, ?)", 
                          (user_id, ref_code, int(time.time())))
        conn.commit()

def update_coins(user_id, amount):
    if DATABASE_URL:
        cursor.execute("UPDATE users SET coins = coins + %s WHERE user_id=%s", (amount, user_id))
    else:
        cursor.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def check_boost(user_id):
    if DATABASE_URL:
        cursor.execute("SELECT boost_until FROM users WHERE user_id=%s", (user_id,))
    else:
        cursor.execute("SELECT boost_until FROM users WHERE user_id=?", (user_id,))
    data = cursor.fetchone()
    if data and data[0] > int(time.time()):
        return True
    return False

def activate_boost(user_id):
    until = int(time.time()) + BOOST_DURATION
    if DATABASE_URL:
        cursor.execute("UPDATE users SET boost_until=%s WHERE user_id=%s", (until, user_id))
    else:
        cursor.execute("UPDATE users SET boost_until=? WHERE user_id=?", (until, user_id))
    conn.commit()

def is_admin(user_id):
    return user_id in ADMINS

def is_verifier(user_id):
    if DATABASE_URL:
        cursor.execute("SELECT * FROM verifiers WHERE user_id=%s", (user_id,))
    else:
        cursor.execute("SELECT * FROM verifiers WHERE user_id=?", (user_id,))
    return cursor.fetchone() is not None

def add_verifier(user_id, added_by):
    try:
        if DATABASE_URL:
            cursor.execute("INSERT INTO verifiers (user_id, added_by, added_at) VALUES (%s, %s, %s)", 
                          (user_id, added_by, int(time.time())))
        else:
            cursor.execute("INSERT INTO verifiers (user_id, added_by, added_at) VALUES (?, ?, ?)", 
                          (user_id, added_by, int(time.time())))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error adding verifier: {e}")
        return False

def remove_verifier(user_id):
    if DATABASE_URL:
        cursor.execute("DELETE FROM verifiers WHERE user_id=%s", (user_id,))
    else:
        cursor.execute("DELETE FROM verifiers WHERE user_id=?", (user_id,))
    conn.commit()
    return cursor.rowcount > 0

def list_verifiers():
    cursor.execute("SELECT user_id FROM verifiers")
    return [row[0] for row in cursor.fetchall()]

# ==============================
# KEYBOARDS
# ==============================
def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💰 Coins", callback_data="coins"),
        InlineKeyboardButton("👥 Refer", callback_data="refer"),
        InlineKeyboardButton("📋 Tasks", callback_data="tasks"),
        InlineKeyboardButton("⚡ Boost Mode", callback_data="boost"),
        InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
        InlineKeyboardButton("🆘 Support", callback_data="support")
    )
    kb.row(InlineKeyboardButton("🌐 Mini App", web_app=WebAppInfo(url=MINI_APP_URL)))
    return kb

def join_check_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL}"))
    kb.add(InlineKeyboardButton("🔄 Verify", callback_data="verify_join"))
    return kb

def admin_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👥 Add Verifier", callback_data="add_verifier"),
           InlineKeyboardButton("❌ Remove Verifier", callback_data="remove_verifier"))
    kb.add(InlineKeyboardButton("📋 List Verifiers", callback_data="list_verifiers"))
    return kb

# ==============================
# HANDLERS
# ==============================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    args = message.get_args()
    ref_code = args if args else None
    
    add_user(message.from_user.id, ref_code)
    
    # Referral processing
    if ref_code and ref_code.startswith("REF"):
        try:
            referrer_id = int(ref_code[3:])
            if get_user(referrer_id) and referrer_id != message.from_user.id:
                update_coins(referrer_id, REFERRAL_REWARD)
                if DATABASE_URL:
                    cursor.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id=%s", (referrer_id,))
                else:
                    cursor.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id=?", (referrer_id,))
                conn.commit()
        except ValueError:
            pass

    try:
        member = await bot.get_chat_member(f"@{REQUIRED_CHANNEL}", message.from_user.id)
        if member.status in ["member", "administrator", "creator"]:
            await message.answer("🎉 Welcome to X Reward Bot!", reply_markup=main_menu())
        else:
            await message.answer("🚨 You must join our channel first:", reply_markup=join_check_keyboard())
    except ChatNotFound:
        await message.answer("⚠️ Channel not found. Contact admin.")

@dp.message_handler(commands=["admin"])
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Access denied!")
        return
        
    await message.answer("🛠 Admin Panel", reply_markup=admin_keyboard())

@dp.callback_query_handler(lambda c: c.data == "verify_join")
async def verify_join(callback: types.CallbackQuery):
    try:
        member = await bot.get_chat_member(f"@{REQUIRED_CHANNEL}", callback.from_user.id)
        if member.status in ["member", "administrator", "creator"]:
            update_coins(callback.from_user.id, JOIN_REWARD)
            await callback.message.edit_text("✅ Verified! +100 coins awarded.", reply_markup=main_menu())
        else:
            await callback.answer("❌ You haven't joined yet!", show_alert=True)
    except ChatNotFound:
        await callback.message.answer("⚠️ Channel not found.")

@dp.callback_query_handler(lambda c: c.data == "coins")
async def show_coins(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    await callback.message.edit_text(f"💰 Your Coins: {user[1]}", reply_markup=main_menu())

@dp.callback_query_handler(lambda c: c.data == "refer")
async def refer_system(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    text = f"👥 Share your referral link:\n\nhttps://t.me/{BOT_USERNAME}?start={user[3]}\n\nYou'll get {REFERRAL_REWARD} coins for each referral!"
    await callback.message.edit_text(text, reply_markup=main_menu())

@dp.callback_query_handler(lambda c: c.data == "boost")
async def boost_mode(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Insert ad watch record
    if DATABASE_URL:
        cursor.execute("INSERT INTO ads (user_id, watched_at) VALUES (%s, %s)", (user_id, int(time.time())))
    else:
        cursor.execute("INSERT INTO ads (user_id, watched_at) VALUES (?, ?)", (user_id, int(time.time())))
    conn.commit()
    
    # Count ads in last hour
    if DATABASE_URL:
        cursor.execute("SELECT COUNT(*) FROM ads WHERE user_id=%s AND watched_at > %s", 
                      (user_id, int(time.time()) - 3600))
    else:
        cursor.execute("SELECT COUNT(*) FROM ads WHERE user_id=? AND watched_at > ?", 
                      (user_id, int(time.time()) - 3600))
    count = cursor.fetchone()[0]
    
    # Give reward for watching ad
    update_coins(user_id, ADS_REWARD)
    
    if count >= BOOST_ADS_REQUIRED:
        activate_boost(user_id)
        await callback.message.edit_text("🔥 You watched enough ads! Boost Mode activated for 1 hour.", reply_markup=main_menu())
    else:
        await callback.message.edit_text(f"👀 You watched {count}/{BOOST_ADS_REQUIRED} ads.\nWatch more to activate Boost Mode!", reply_markup=main_menu())

@dp.callback_query_handler(lambda c: c.data == "leaderboard")
async def leaderboard(callback: types.CallbackQuery):
    if DATABASE_URL:
        cursor.execute("SELECT user_id, coins FROM users ORDER BY coins DESC LIMIT 10")
    else:
        cursor.execute("SELECT user_id, coins FROM users ORDER BY coins DESC LIMIT 10")
    top = cursor.fetchall()
    text = "🏆 Coins Leaderboard:\n\n"
    for i, row in enumerate(top, start=1):
        try:
            user = await bot.get_chat(row[0])
            username = user.username if user.username else user.first_name
            text += f"{i}. {username} - {row[1]} coins\n"
        except:
            text += f"{i}. User {row[0]} - {row[1]} coins\n"
    await callback.message.edit_text(text, reply_markup=main_menu())

# Verifier management handlers
@dp.callback_query_handler(lambda c: c.data == "add_verifier")
async def add_verifier_cmd(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Only admins can do this!")
        return
        
    await callback.message.edit_text("Send the user ID to add as verifier:")

@dp.callback_query_handler(lambda c: c.data == "remove_verifier")
async def remove_verifier_cmd(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Only admins can do this!")
        return
        
    verifiers = list_verifiers()
    if not verifiers:
        await callback.message.edit_text("No verifiers found!")
        return
        
    text = "Current verifiers:\n"
    for user_id in verifiers:
        text += f"- {user_id}\n"
    text += "\nSend the user ID to remove:"
    
    await callback.message.edit_text(text)

@dp.callback_query_handler(lambda c: c.data == "list_verifiers")
async def list_verifiers_cmd(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id) and not is_verifier(callback.from_user.id):
        await callback.answer("❌ Access denied!")
        return
        
    verifiers = list_verifiers()
    if not verifiers:
        await callback.message.edit_text("No verifiers found!")
        return
        
    text = "📋 Verifiers List:\n\n"
    for user_id in verifiers:
        try:
            user = await bot.get_chat(user_id)
            username = user.username if user.username else user.first_name
            text += f"- {username} (ID: {user_id})\n"
        except:
            text += f"- User ID: {user_id}\n"
            
    await callback.message.edit_text(text)

@dp.message_handler(lambda message: message.reply_to_message and message.reply_to_message.text in ["Send the user ID to add as verifier:", "Send the user ID to remove:"])
async def process_verifier_actions(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Only admins can do this!")
        return
        
    try:
        user_id = int(message.text)
        if message.reply_to_message.text == "Send the user ID to add as verifier:":
            if add_verifier(user_id, message.from_user.id):
                await message.answer(f"✅ User {user_id} added as verifier!")
            else:
                await message.answer("❌ User is already a verifier!")
        else:
            if remove_verifier(user_id):
                await message.answer(f"✅ User {user_id} removed from verifiers!")
            else:
                await message.answer("❌ User not found in verifiers!")
    except ValueError:
        await message.answer("❌ Invalid user ID!")

# ==============================
# START BOT
# ==============================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
