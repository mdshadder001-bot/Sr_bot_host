import telebot
import zipfile
import tempfile
import shutil
import os
import sys
import subprocess
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import logging
import threading
import re
import atexit
import requests
import html as html_lib
import hashlib
from flask import Flask
from threading import Thread

# ╔═══════════════════════════════════════════════════════════════╗
# ║   ✏️  শুধু এই ৫ লাইনে তোমার তথ্য বসাও                        ║
# ╚═══════════════════════════════════════════════════════════════╝

TOKEN = "9061914208:AAGlaw3PolR0e9j4nIoXhZVzSxzaRaJl1Hg"
OWNER_ID = 8746661403
ADMIN_ID = 8746661403
YOUR_USERNAME = "@BDT_NX_DEVELOPER"
UPDATE_CHANNEL = "https://t.me/NX_REAL_KNOWLEGE"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⛔ এর নিচে কিছু পরিবর্তন করবে না
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_missing = []
if not TOKEN: _missing.append("TOKEN")
if OWNER_ID == 0: _missing.append("OWNER_ID")
if not YOUR_USERNAME: _missing.append("YOUR_USERNAME")
if not UPDATE_CHANNEL: _missing.append("UPDATE_CHANNEL")
if _missing:
    raise ValueError(f"\n\n❌ এই মানগুলো দেওয়া হয়নি: {', '.join(_missing)}\n")
if ADMIN_ID == 0: ADMIN_ID = OWNER_ID

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

FREE_USER_LIMIT = 3
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)
BOT_START_TIME = time.time()

bot_scripts = {}
bot_scripts_lock = threading.RLock()
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False

# ═══════════════════════════════════════════════════════════════
# SPINNER + LIVE LOGS STATE
# ═══════════════════════════════════════════════════════════════
SPINNER_FRAMES = ["◴", "◷", "◶", "◵"]
_spinner_tick = [0]
_spinner_lock = threading.Lock()

_live_logs = {}
_live_logs_lock = threading.Lock()

_active_spinners = {}
_spinner_views_lock = threading.Lock()


def get_spinner():
    with _spinner_lock:
        _spinner_tick[0] = (_spinner_tick[0] + 1) % len(SPINNER_FRAMES)
        return SPINNER_FRAMES[_spinner_tick[0]]


def _clear_view_state(chat_id, message_id):
    key = f"{chat_id}_{message_id}"
    with _spinner_views_lock:
        _active_spinners.pop(key, None)
    with _live_logs_lock:
        s = _live_logs.get(key)
        if s: s['active'] = False
        _live_logs.pop(key, None)


def _fmt_size(b):
    if b < 1024: return f"{b} B"
    if b < 1024 * 1024: return f"{b / 1024:.1f} KB"
    return f"{b / 1024 / 1024:.2f} MB"


# ═══════════════════════════════════════════════════════════════
# 🆕 FILE REF HELPERS (callback data 64-byte limit fix)
# ═══════════════════════════════════════════════════════════════
def _file_ref(owner_id, fname):
    """ফাইলনেমের বদলে ৮-char hash (callback 64-byte limit এর জন্য)।"""
    return hashlib.md5(f"{owner_id}_{fname}".encode()).hexdigest()[:8]


def _resolve_ref(owner_id, ref):
    """Hash ref → (fname, ftype) অথবা (None, None)।"""
    files_snapshot = list(user_files.get(owner_id, []))
    for fn, ft in files_snapshot:
        if _file_ref(owner_id, fn) == ref:
            return fn, ft
    return None, None


class _FakeMessage:
    """Background thread-এ bot.reply_to-এর জন্য fake message।"""
    def __init__(self, chat_id, message_id=0):
        self.chat = type('Chat', (), {'id': chat_id})()
        self.message_id = message_id
        self.from_user = type('User', (), {'id': 0, 'first_name': '', 'username': ''})()


# ───────── Logging ─────────
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# PREMIUM EMOJI
# ═══════════════════════════════════════════════════════════════
PEM = {
    "ok":     '<tg-emoji emoji-id="6111726981760423576">✅</tg-emoji>',
    "no":     '<tg-emoji emoji-id="6311965254817423602">❌</tg-emoji>',
    "warn":   '<tg-emoji emoji-id="6314510813214284503">⚠️</tg-emoji>',
    "admin":  '<tg-emoji emoji-id="5353032893096567467">📊</tg-emoji>',
    "user":   '<tg-emoji emoji-id="5352861489541714456">👤</tg-emoji>',
    "money":  '<tg-emoji emoji-id="6111799373434197692">💸</tg-emoji>',
    "msg":    '<tg-emoji emoji-id="5337302974806922068">💬</tg-emoji>',
    "rocket": '<tg-emoji emoji-id="5352597830089347330">🚀</tg-emoji>',
    "pin":    '<tg-emoji emoji-id="6111410240807245099">📌</tg-emoji>',
    "hi":     '<tg-emoji emoji-id="5353027129250453493">👋</tg-emoji>',
    "file":   '<tg-emoji emoji-id="5352721946054268944">📁</tg-emoji>',
    "key":    '<tg-emoji emoji-id="6233302765582424442">🔑</tg-emoji>',
    "wait":   '<tg-emoji emoji-id="6233136657722251031">⏳</tg-emoji>',
    "bell":   '<tg-emoji emoji-id="6260082445018731350">🔔</tg-emoji>',
    "crown":  '<tg-emoji emoji-id="6183661284467152997">👑</tg-emoji>',
    "gear":   '<tg-emoji emoji-id="6260111633616475361">⚙️</tg-emoji>',
    "check":  '<tg-emoji emoji-id="6188038822509418008">✅</tg-emoji>',
    "add":    '<tg-emoji emoji-id="6188038822509418008">➕</tg-emoji>',
    "rem":    '<tg-emoji emoji-id="6188343249791358585">➖</tg-emoji>',
    "view":   '<tg-emoji emoji-id="6188447235244562676">👀</tg-emoji>',
    "speed":  '<tg-emoji emoji-id="6186175669991379791">⚡</tg-emoji>',
    "join":   '<tg-emoji emoji-id="5352597830089347330">➡️</tg-emoji>',
    "back":   '<tg-emoji emoji-id="6109360506319935223">🔙</tg-emoji>',
}

# ═══════════════════════════════════════════════════════════════
# RAW API HELPERS
# ═══════════════════════════════════════════════════════════════
def rbtn(text, emoji_id=None, style=None):
    b = {"text": text}
    if emoji_id: b["icon_custom_emoji_id"] = emoji_id
    if style:    b["style"] = style
    return b


def ibtn(text, callback_data=None, url=None, emoji_id=None, style=None):
    b = {"text": text}
    if callback_data: b["callback_data"] = callback_data
    if url:           b["url"] = url
    if emoji_id:      b["icon_custom_emoji_id"] = emoji_id
    if style:         b["style"] = style
    return b


def raw_send(chat_id, text, reply_keyboard=None, inline_keyboard=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": text,
               "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_keyboard:
        payload["reply_markup"] = {"keyboard": reply_keyboard, "resize_keyboard": True}
    elif inline_keyboard:
        payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                          json=payload, timeout=30)
        return r.json()
    except Exception as e:
        logger.error(f"raw_send err: {e}")
        return {}


def raw_edit(chat_id, message_id, text, inline_keyboard=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text,
               "parse_mode": parse_mode, "disable_web_page_preview": True}
    if inline_keyboard:
        payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/editMessageText",
                          json=payload, timeout=30)
        return r.json()
    except Exception as e:
        logger.error(f"raw_edit err: {e}")
        return {}


def raw_edit_markup(chat_id, message_id, inline_keyboard):
    payload = {"chat_id": chat_id, "message_id": message_id,
               "reply_markup": {"inline_keyboard": inline_keyboard}}
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/editMessageReplyMarkup",
                          json=payload, timeout=15)
        return r.json()
    except: return {}


# ═══════════════════════════════════════════════════════════════
# SYSTEM STATS
# ═══════════════════════════════════════════════════════════════
def get_uptime_str():
    elapsed = int(time.time() - BOT_START_TIME)
    d = elapsed // 86400
    h = (elapsed % 86400) // 3600
    m = (elapsed % 3600) // 60
    s = elapsed % 60
    if d > 0: return f"{d}d {h}h {m}m"
    if h > 0: return f"{h}h {m}m {s}s"
    if m > 0: return f"{m}m {s}s"
    return f"{s}s"


def get_system_stats():
    try:
        cpu = psutil.cpu_percent(interval=0.3)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return {
            "cpu": cpu,
            "ram_used": ram.used / (1024**3), "ram_total": ram.total / (1024**3),
            "ram_pct": ram.percent,
            "disk_used": disk.used / (1024**3), "disk_total": disk.total / (1024**3),
            "disk_pct": disk.percent,
            "uptime": get_uptime_str(),
        }
    except Exception as e:
        logger.error(f"sys stats: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# KEYBOARD BUILDERS
# ═══════════════════════════════════════════════════════════════
def create_reply_keyboard_main_menu(user_id):
    if user_id in admin_ids:
        return [
            [rbtn("📢 Updates Channel", "5352597830089347330", "primary")],
            [rbtn("📤 Upload File", "5352721946054268944", "primary"),
             rbtn("📂 Check Files", "6188447235244562676", "primary")],
            [rbtn("⚡ Bot Speed", "6186175669991379791", "primary"),
             rbtn("📊 Statistics", "5353032893096567467", "success")],
            [rbtn("💳 Subscriptions", "6111799373434197692", "primary"),
             rbtn("📢 Broadcast", "5337302974806922068", "success")],
            [rbtn("🔒 Lock Bot", "6311965254817423602", "danger"),
             rbtn("🟢 Running All Code", "5352597830089347330", "success")],
            [rbtn("👑 Admin Panel", "6183661284467152997", "primary"),
             rbtn("📞 Contact Owner", "5337302974806922068", "primary")]
        ]
    return [
        [rbtn("📢 Updates Channel", "5352597830089347330", "primary")],
        [rbtn("📤 Upload File", "5352721946054268944", "primary"),
         rbtn("📂 Check Files", "6188447235244562676", "primary")],
        [rbtn("⚡ Bot Speed", "6186175669991379791", "primary"),
         rbtn("📊 Statistics", "5353032893096567467", "success")],
        [rbtn("📞 Contact Owner", "5337302974806922068", "primary")]
    ]


def create_main_menu_inline(user_id):
    b = [
        [ibtn('📢 Updates Channel', url=UPDATE_CHANNEL, emoji_id="5352597830089347330", style="primary")],
        [ibtn('📤 Upload File', callback_data='upload', emoji_id="5352721946054268944", style="primary"),
         ibtn('📂 Check Files', callback_data='check_files', emoji_id="6188447235244562676", style="primary")],
        [ibtn('⚡ Bot Speed', callback_data='speed', emoji_id="6186175669991379791", style="primary"),
         ibtn('📊 Statistics', callback_data='stats', emoji_id="5353032893096567467", style="success")],
    ]
    if user_id in admin_ids:
        b.append([
            ibtn('💳 Subscriptions', callback_data='subscription', emoji_id="6111799373434197692", style="primary"),
            ibtn('📢 Broadcast', callback_data='broadcast', emoji_id="5337302974806922068", style="success"),
        ])
        b.append([
            ibtn('🔓 Unlock Bot' if bot_locked else '🔒 Lock Bot',
                 callback_data='unlock_bot' if bot_locked else 'lock_bot',
                 emoji_id="6311965254817423602", style="danger"),
            ibtn('🟢 Run All', callback_data='run_all_scripts', emoji_id="5352597830089347330", style="success"),
        ])
        b.append([ibtn('👑 Admin Panel', callback_data='admin_panel', emoji_id="6183661284467152997", style="primary")])
    b.append([ibtn('📞 Contact Owner',
                   url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}',
                   emoji_id="5337302974806922068", style="primary")])
    return b


def create_control_buttons(owner_id, file_name, is_running=True):
    ref = _file_ref(owner_id, file_name)   # 🆕 hash ref
    if is_running:
        sp = get_spinner()
        return [
            [ibtn(f"🔴 Stop {sp}", callback_data=f'stop_{owner_id}_{ref}',
                  emoji_id="6311965254817423602", style="danger"),
             ibtn("🔄 Restart", callback_data=f'restart_{owner_id}_{ref}',
                  emoji_id="5352597830089347330", style="primary")],
            [ibtn("🗑️ Delete", callback_data=f'delete_{owner_id}_{ref}',
                  emoji_id="6188343249791358585", style="danger"),
             ibtn("📜 Live Logs", callback_data=f'logs_{owner_id}_{ref}',
                  emoji_id="6188447235244562676", style="primary")],
            [ibtn("🔙 Back", callback_data='check_files',
                  emoji_id="6109360506319935223", style="primary")],
        ]
    return [
        [ibtn("🟢 Start", callback_data=f'start_{owner_id}_{ref}',
              emoji_id="6111726981760423576", style="success"),
         ibtn("🗑️ Delete", callback_data=f'delete_{owner_id}_{ref}',
              emoji_id="6188343249791358585", style="danger")],
        [ibtn("📜 View Logs", callback_data=f'logs_{owner_id}_{ref}',
              emoji_id="6188447235244562676", style="primary")],
        [ibtn("🔙 Back", callback_data='check_files',
              emoji_id="6109360506319935223", style="primary")],
    ]


def create_admin_panel():
    return [
        [ibtn('➕ Add Admin', callback_data='add_admin', emoji_id="6188038822509418008", style="success"),
         ibtn('➖ Remove Admin', callback_data='remove_admin', emoji_id="6188343249791358585", style="danger")],
        [ibtn('📋 List Admins', callback_data='list_admins', emoji_id="5353032893096567467", style="primary"),
         ibtn('🖥️ System Info', callback_data='system_info', emoji_id="6186175669991379791", style="primary")],
        [ibtn('📋 Audit Log', callback_data='audit_view', emoji_id="5352721946054268944", style="primary")],
        [ibtn('🔙 Back', callback_data='back_to_main', emoji_id="6109360506319935223", style="primary")],
    ]


def create_subscription_menu():
    return [
        [ibtn('➕ Add Sub', callback_data='add_subscription', emoji_id="6188038822509418008", style="success"),
         ibtn('➖ Remove Sub', callback_data='remove_subscription', emoji_id="6188343249791358585", style="danger")],
        [ibtn('🔍 Check Sub', callback_data='check_subscription', emoji_id="6188447235244562676", style="primary")],
        [ibtn('🔙 Back', callback_data='back_to_main', emoji_id="6109360506319935223", style="primary")],
    ]


# ═══════════════════════════════════════════════════════════════
# DB SETUP
# ═══════════════════════════════════════════════════════════════
def init_db():
    logger.info(f"DB: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, admin_id INTEGER, action TEXT,
            target TEXT, details TEXT
        )''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit(); conn.close()
        logger.info("DB OK.")
    except Exception as e:
        logger.error(f"DB err: {e}", exc_info=True)


def load_data():
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for uid, exp in c.fetchall():
            try: user_subscriptions[uid] = {'expiry': datetime.fromisoformat(exp)}
            except ValueError: pass
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for uid, fn, ft in c.fetchall():
            user_files.setdefault(uid, []).append((fn, ft))
        c.execute('SELECT user_id FROM active_users')
        active_users.update(x for (x,) in c.fetchall())
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(x for (x,) in c.fetchall())
        conn.close()
        logger.info(f"Loaded: {len(active_users)} users, {len(user_subscriptions)} subs, {len(admin_ids)} admins.")
    except Exception as e:
        logger.error(f"Load err: {e}", exc_info=True)


init_db()
load_data()

# ═══════════════════════════════════════════════════════════════
# FLASK KEEP-ALIVE
# ═══════════════════════════════════════════════════════════════
app = Flask('')


@app.route('/')
def home(): return "Bot is running!"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)


def keep_alive():
    t = Thread(target=run_flask); t.daemon = True; t.start()
    print("Flask started.")


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def get_user_folder(user_id):
    f = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(f, exist_ok=True); return f


def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT


def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))


def is_bot_running(owner_id, file_name):
    sk = f"{owner_id}_{file_name}"
    with bot_scripts_lock:
        info = bot_scripts.get(sk)
        if not info: return False
        proc = info.get('process')
        if not proc:
            if 'log_file' in info and hasattr(info['log_file'], 'close'):
                try: info['log_file'].close()
                except: pass
            bot_scripts.pop(sk, None); return False
        try:
            p = psutil.Process(proc.pid)
            r = p.is_running() and p.status() != psutil.STATUS_ZOMBIE
            if not r:
                if 'log_file' in info and hasattr(info['log_file'], 'close') and not info['log_file'].closed:
                    try: info['log_file'].close()
                    except: pass
                bot_scripts.pop(sk, None)
            return r
        except (psutil.NoSuchProcess, Exception):
            if 'log_file' in info and hasattr(info['log_file'], 'close') and not info['log_file'].closed:
                try: info['log_file'].close()
                except: pass
            bot_scripts.pop(sk, None); return False


def kill_process_tree(process_info):
    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close') and not process_info['log_file'].closed:
            try: process_info['log_file'].close()
            except: pass
        proc = process_info.get('process')
        if proc and hasattr(proc, 'pid') and proc.pid:
            try:
                parent = psutil.Process(proc.pid)
                children = parent.children(recursive=True)
                for ch in children:
                    try: ch.terminate()
                    except:
                        try: ch.kill()
                        except: pass
                gone, alive = psutil.wait_procs(children, timeout=1)
                for p in alive:
                    try: p.kill()
                    except: pass
                try:
                    parent.terminate()
                    try: parent.wait(timeout=1)
                    except psutil.TimeoutExpired: parent.kill()
                except Exception:
                    try: parent.kill()
                    except: pass
            except psutil.NoSuchProcess: pass
    except Exception as e:
        logger.error(f"kill err: {e}")


# ═══════════════════════════════════════════════════════════════
# AUTO INSTALL
# ═══════════════════════════════════════════════════════════════
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot',
    'python_telegram_bot': 'python-telegram-bot', 'aiogram': 'aiogram',
    'pyrogram': 'pyrogram', 'telethon': 'telethon', 'telethon.sync': 'telethon',
    'telepot': 'telepot', 'pytg': 'pytg', 'tgcrypto': 'tgcrypto',
    'bs4': 'beautifulsoup4', 'requests': 'requests', 'pillow': 'Pillow',
    'cv2': 'opencv-python', 'yaml': 'PyYAML', 'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil', 'pandas': 'pandas', 'numpy': 'numpy',
    'flask': 'Flask', 'django': 'Django', 'sqlalchemy': 'SQLAlchemy',
    'psutil': 'psutil',
    'asyncio': None, 'json': None, 'datetime': None, 'os': None, 'sys': None,
    're': None, 'time': None, 'math': None, 'random': None, 'logging': None,
    'threading': None, 'subprocess': None, 'zipfile': None, 'tempfile': None,
    'shutil': None, 'sqlite3': None, 'atexit': None,
}


def attempt_install_pip(mod, msg, silent=False):
    pkg = TELEGRAM_MODULES.get(mod.lower(), mod)
    if pkg is None: return False
    try:
        if not silent:
            bot.reply_to(msg, f"🐍 Installing <code>{pkg}</code>...", parse_mode='HTML')
        r = subprocess.run([sys.executable, '-m', 'pip', 'install', pkg],
                           capture_output=True, text=True, check=False,
                           encoding='utf-8', errors='ignore')
        if r.returncode == 0:
            if not silent:
                bot.reply_to(msg, f"{PEM['ok']} <code>{pkg}</code> installed.", parse_mode='HTML')
            return True
        return False
    except: return False


def attempt_install_npm(mod, folder, msg, silent=False):
    try:
        if not silent:
            bot.reply_to(msg, f"🟠 Installing npm <code>{mod}</code>...", parse_mode='HTML')
        r = subprocess.run(['npm', 'install', mod], capture_output=True, text=True,
                           check=False, cwd=folder, encoding='utf-8', errors='ignore')
        if r.returncode == 0:
            if not silent:
                bot.reply_to(msg, f"{PEM['ok']} npm <code>{mod}</code> installed.", parse_mode='HTML')
            return True
        return False
    except: return False


# ═══════════════════════════════════════════════════════════════
# RUN SCRIPTS
# ═══════════════════════════════════════════════════════════════
def run_script(path, owner, folder, fn, msg, attempt=1, silent=False):
    if attempt > 2:
        if not silent: bot.reply_to(msg, f"{PEM['no']} Failed to run <code>{fn}</code>.", parse_mode='HTML')
        return
    sk = f"{owner}_{fn}"
    try:
        if not os.path.exists(path):
            if not silent: bot.reply_to(msg, f"{PEM['no']} <code>{fn}</code> not found!", parse_mode='HTML')
            remove_user_file_db(owner, fn); return
        if attempt == 1:
            check_proc = None
            try:
                check_proc = subprocess.Popen([sys.executable, path], cwd=folder,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              text=True, encoding='utf-8', errors='ignore')
                _, stderr = check_proc.communicate(timeout=5)
                if check_proc.returncode != 0 and stderr:
                    m = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if m:
                        mod = m.group(1).strip().strip("'\"")
                        if attempt_install_pip(mod, msg, silent=silent):
                            if not silent: bot.reply_to(msg, f"{PEM['wait']} Retrying...", parse_mode='HTML')
                            time.sleep(2)
                            threading.Thread(target=run_script, args=(
                                path, owner, folder, fn, msg, attempt + 1, silent)).start()
                            return
                        return
                    if not silent:
                        bot.reply_to(msg, f"{PEM['no']} Error:\n<pre>{html_lib.escape(stderr[:500])}</pre>", parse_mode='HTML')
                    return
            except subprocess.TimeoutExpired:
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
            except FileNotFoundError:
                if not silent: bot.reply_to(msg, f"{PEM['no']} Python not found.", parse_mode='HTML')
                return
            finally:
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()

        lp = os.path.join(folder, f"{os.path.splitext(fn)[0]}.log")
        lf = None
        try: lf = open(lp, 'w', encoding='utf-8', errors='ignore')
        except Exception: return
        try:
            si = None; cf = 0
            if os.name == 'nt':
                si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
            proc = subprocess.Popen([sys.executable, path], cwd=folder,
                                    stdout=lf, stderr=lf, stdin=subprocess.PIPE,
                                    startupinfo=si, creationflags=cf,
                                    encoding='utf-8', errors='ignore')
            with bot_scripts_lock:
                bot_scripts[sk] = {
                    'process': proc, 'log_file': lf, 'file_name': fn,
                    'chat_id': msg.chat.id, 'script_owner_id': owner,
                    'start_time': datetime.now(), 'user_folder': folder,
                    'type': 'py', 'script_key': sk
                }
            if not silent:
                raw_send(msg.chat.id,
                         f"{PEM['ok']} <b>Script Started!</b>\n\n"
                         f"{PEM['file']} File: <code>{fn}</code>\n"
                         f"{PEM['gear']} PID: <code>{proc.pid}</code>",
                         parse_mode='HTML')
        except Exception as e:
            if lf and not lf.closed: lf.close()
            if not silent: bot.reply_to(msg, f"{PEM['no']} Start error: {e}", parse_mode='HTML')
            with bot_scripts_lock: bot_scripts.pop(sk, None)
    except Exception as e:
        logger.error(f"run_script err {sk}: {e}", exc_info=True)
        with bot_scripts_lock:
            if sk in bot_scripts:
                kill_process_tree(bot_scripts[sk]); bot_scripts.pop(sk, None)


def run_js_script(path, owner, folder, fn, msg, attempt=1, silent=False):
    if attempt > 2:
        if not silent: bot.reply_to(msg, f"{PEM['no']} Failed to run <code>{fn}</code>.", parse_mode='HTML')
        return
    sk = f"{owner}_{fn}"
    try:
        if not os.path.exists(path):
            if not silent: bot.reply_to(msg, f"{PEM['no']} <code>{fn}</code> not found!", parse_mode='HTML')
            remove_user_file_db(owner, fn); return
        if attempt == 1:
            check_proc = None
            try:
                check_proc = subprocess.Popen(['node', path], cwd=folder,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              text=True, encoding='utf-8', errors='ignore')
                _, stderr = check_proc.communicate(timeout=5)
                if check_proc.returncode != 0 and stderr:
                    m = re.search(r"Cannot find module '(.+?)'", stderr)
                    if m:
                        mod = m.group(1).strip().strip("'\"")
                        if not mod.startswith('.') and not mod.startswith('/'):
                            if attempt_install_npm(mod, folder, msg, silent=silent):
                                if not silent: bot.reply_to(msg, f"{PEM['wait']} Retrying...", parse_mode='HTML')
                                time.sleep(2)
                                threading.Thread(target=run_js_script, args=(
                                    path, owner, folder, fn, msg, attempt + 1, silent)).start()
                                return
                    if not silent:
                        bot.reply_to(msg, f"{PEM['no']} Error:\n<pre>{html_lib.escape(stderr[:500])}</pre>", parse_mode='HTML')
                    return
            except subprocess.TimeoutExpired:
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
            except FileNotFoundError:
                if not silent: bot.reply_to(msg, f"{PEM['no']} Node.js not found.", parse_mode='HTML')
                return
            finally:
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()

        lp = os.path.join(folder, f"{os.path.splitext(fn)[0]}.log")
        lf = None
        try: lf = open(lp, 'w', encoding='utf-8', errors='ignore')
        except Exception: return
        try:
            si = None; cf = 0
            if os.name == 'nt':
                si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
            proc = subprocess.Popen(['node', path], cwd=folder,
                                    stdout=lf, stderr=lf, stdin=subprocess.PIPE,
                                    startupinfo=si, creationflags=cf,
                                    encoding='utf-8', errors='ignore')
            with bot_scripts_lock:
                bot_scripts[sk] = {
                    'process': proc, 'log_file': lf, 'file_name': fn,
                    'chat_id': msg.chat.id, 'script_owner_id': owner,
                    'start_time': datetime.now(), 'user_folder': folder,
                    'type': 'js', 'script_key': sk
                }
            if not silent:
                raw_send(msg.chat.id,
                         f"{PEM['ok']} <b>JS Script Started!</b>\n\n"
                         f"{PEM['file']} File: <code>{fn}</code>\n"
                         f"{PEM['gear']} PID: <code>{proc.pid}</code>",
                         parse_mode='HTML')
        except Exception as e:
            if lf and not lf.closed: lf.close()
            if not silent: bot.reply_to(msg, f"{PEM['no']} Start error: {e}", parse_mode='HTML')
            with bot_scripts_lock: bot_scripts.pop(sk, None)
    except Exception as e:
        logger.error(f"run_js_script err {sk}: {e}", exc_info=True)
        with bot_scripts_lock:
            if sk in bot_scripts:
                kill_process_tree(bot_scripts[sk]); bot_scripts.pop(sk, None)


# ═══════════════════════════════════════════════════════════════
# DB OPS + AUDIT (✨ auto-trim)
# ═══════════════════════════════════════════════════════════════
DB_LOCK = threading.Lock()


def log_audit(admin_id, action, target="", details=""):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute(
                'INSERT INTO audit_log (timestamp, admin_id, action, target, details) VALUES (?, ?, ?, ?, ?)',
                (datetime.now().isoformat(), admin_id, action, str(target)[:100], str(details)[:500])
            )
            # ✨ Keep only last 500
            conn.execute('DELETE FROM audit_log WHERE id NOT IN '
                         '(SELECT id FROM audit_log ORDER BY id DESC LIMIT 500)')
            conn.commit()
        except Exception as e: logger.error(f"audit: {e}")
        finally: conn.close()


def get_audit_logs(limit=20):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            cur = conn.execute(
                'SELECT timestamp, admin_id, action, target, details FROM audit_log ORDER BY id DESC LIMIT ?',
                (limit,))
            return cur.fetchall()
        except: return []
        finally: conn.close()


def clear_audit_logs():
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute('DELETE FROM audit_log'); conn.commit(); return True
        except: return False
        finally: conn.close()


def save_user_file(uid, fn, ft='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files VALUES (?, ?, ?)', (uid, fn, ft)); conn.commit()
            user_files.setdefault(uid, [])
            user_files[uid] = [(n, t) for n, t in user_files[uid] if n != fn]
            user_files[uid].append((fn, ft))
        except Exception as e: logger.error(f"save_file: {e}")
        finally: conn.close()


def remove_user_file_db(uid, fn):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (uid, fn)); conn.commit()
            if uid in user_files:
                user_files[uid] = [f for f in user_files[uid] if f[0] != fn]
                if not user_files[uid]: del user_files[uid]
        except Exception as e: logger.error(f"rm_file: {e}")
        finally: conn.close()


def add_active_user(uid):
    active_users.add(uid)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute('INSERT OR IGNORE INTO active_users VALUES (?)', (uid,)); conn.commit()
        except: pass
        finally: conn.close()


def save_subscription(uid, exp):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute('INSERT OR REPLACE INTO subscriptions VALUES (?, ?)', (uid, exp.isoformat()))
            conn.commit(); user_subscriptions[uid] = {'expiry': exp}
        except: pass
        finally: conn.close()


def remove_subscription_db(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute('DELETE FROM subscriptions WHERE user_id = ?', (uid,)); conn.commit()
            if uid in user_subscriptions: del user_subscriptions[uid]
        except: pass
        finally: conn.close()


def add_admin_db(aid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute('INSERT OR IGNORE INTO admins VALUES (?)', (aid,)); conn.commit()
            admin_ids.add(aid)
        except: pass
        finally: conn.close()


def remove_admin_db(aid):
    if aid == OWNER_ID: return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute('DELETE FROM admins WHERE user_id = ?', (aid,)); conn.commit()
            admin_ids.discard(aid); return True
        except: return False
        finally: conn.close()


# ═══════════════════════════════════════════════════════════════
# DOWNLOAD WITH PROGRESS BAR
# ═══════════════════════════════════════════════════════════════
def download_with_progress(file_path, chat_id, message_id, total_size, file_name):
    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    chunks = []
    downloaded = 0
    last_pct = -10
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=131072):
                if chunk:
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if total_size and total_size > 0:
                        pct = int(downloaded * 100 / total_size)
                        if pct - last_pct >= 8 or pct >= 100:
                            last_pct = pct
                            filled = min(pct // 5, 20)
                            bar = "█" * filled + "░" * (20 - filled)
                            try:
                                bot.edit_message_text(
                                    f"{PEM['wait']} <b>Downloading File...</b>\n\n"
                                    f"{PEM['file']} <code>{file_name}</code>\n\n"
                                    f"[{bar}] <b>{pct}%</b>\n"
                                    f"<code>{_fmt_size(downloaded)} / {_fmt_size(total_size)}</code>",
                                    chat_id, message_id, parse_mode='HTML')
                            except: pass
        return b"".join(chunks)
    except Exception as e:
        logger.error(f"download err: {e}")
        raise


# ═══════════════════════════════════════════════════════════════
# LIVE LOGS + SPINNER WORKERS
# ═══════════════════════════════════════════════════════════════
def _read_log_tail(log_path, max_lines=20):
    if not os.path.exists(log_path):
        return "(log file not found)"
    try:
        size = os.path.getsize(log_path)
        if size == 0: return "(empty log)"
        with open(log_path, 'rb') as f:
            if size > 8192: f.seek(-8192, os.SEEK_END)
            data = f.read().decode('utf-8', errors='ignore')
        lines = data.split('\n')
        tail = lines[-max_lines:] if len(lines) > max_lines else lines
        return '\n'.join(tail)
    except Exception as e:
        return f"(error: {e})"


def _live_log_controls(owner, fname, paused):
    ref = _file_ref(owner, fname)   # 🆕
    return [
        [ibtn("▶️ Resume" if paused else "⏸️ Pause",
              callback_data=(f'live_resume_{owner}_{ref}' if paused else f'live_pause_{owner}_{ref}'),
              emoji_id="6233136657722251031", style="primary")],
        [ibtn("⏹️ Stop Logs", callback_data=f'live_stop_{owner}_{ref}',
              emoji_id="6311965254817423602", style="danger")],
    ]


def _live_log_worker(session_key):
    """🐛 FIX: paused session ৫ মিনিট পর auto-stop (leak প্রতিরোধ)।"""
    logger.info(f"Live log started: {session_key}")
    idle_count = 0
    while True:
        with _live_logs_lock:
            sess = _live_logs.get(session_key)
        if not sess or not sess['active']: break
        if sess['paused']:
            idle_count += 1
            if idle_count > 100:  # ~5 মিনিট (3s * 100)
                logger.info(f"Auto-stop paused live log: {session_key}")
                with _live_logs_lock:
                    _live_logs.pop(session_key, None)
                break
            time.sleep(3); continue
        idle_count = 0
        try:
            folder = get_user_folder(sess['owner'])
            lp = os.path.join(folder, f"{os.path.splitext(sess['fname'])[0]}.log")
            content = _read_log_tail(lp, 20)
            if len(content) > 3400: content = "..." + content[-3400:]
            is_run = is_bot_running(sess['owner'], sess['fname'])
            now_str = time.strftime('%H:%M:%S')
            header = (f"{PEM['file']} <b>Live Logs: {sess['fname']}</b>\n"
                      f"Status: {'🟢 Running' if is_run else '🔴 Stopped'}  |  "
                      f"{PEM['wait']} Updated: {now_str}\n\n"   # ✨ timestamp
                      f"<pre>{html_lib.escape(content)}</pre>")
            raw_edit(sess['chat_id'], sess['message_id'], header,
                     inline_keyboard=_live_log_controls(sess['owner'], sess['fname'], False),
                     parse_mode='HTML')
        except Exception as e:
            logger.debug(f"live log edit: {e}")
        time.sleep(3)
    logger.info(f"Live log stopped: {session_key}")


def spinner_updater():
    while True:
        try:
            with _spinner_views_lock:
                views = list(_active_spinners.items())
            for key, v in views:
                if not is_bot_running(v['owner'], v['fname']):
                    with _spinner_views_lock:
                        _active_spinners.pop(key, None)
                    continue
                kb = create_control_buttons(v['owner'], v['fname'], True)
                raw_edit_markup(v['chat_id'], v['message_id'], kb)
        except Exception as e:
            logger.debug(f"spinner: {e}")
        time.sleep(3)


threading.Thread(target=spinner_updater, daemon=True).start()


# ═══════════════════════════════════════════════════════════════
# ZIP HANDLER
# ═══════════════════════════════════════════════════════════════
def handle_zip_file(content, zname, message):
    uid = message.from_user.id
    folder = get_user_folder(uid)
    tdir = None
    try:
        tdir = tempfile.mkdtemp(prefix=f"user_{uid}_zip_")
        zp = os.path.join(tdir, zname)
        with open(zp, 'wb') as f: f.write(content)
        with zipfile.ZipFile(zp, 'r') as z:
            for m in z.infolist():
                mp = os.path.abspath(os.path.join(tdir, m.filename))
                if not mp.startswith(os.path.abspath(tdir)):
                    raise zipfile.BadZipFile(f"Unsafe: {m.filename}")
            z.extractall(tdir)
        all_files = []
        for root, dirs, files in os.walk(tdir):
            dirs[:] = [d for d in dirs if not d.startswith('__') and not d.startswith('.')]
            for f in files:
                if f.startswith('.') or f == zname: continue
                full = os.path.join(root, f)
                all_files.append((os.path.relpath(full, tdir), f, full))
        if not all_files:
            bot.reply_to(message, f"{PEM['no']} ZIP empty!", parse_mode='HTML'); return
        req = next((full for r, b, full in all_files if b == 'requirements.txt'), None)
        pkg = next((full for r, b, full in all_files if b == 'package.json'), None)
        if req:
            bot.reply_to(message, f"{PEM['wait']} Installing Python deps...", parse_mode='HTML')
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', req],
                              capture_output=True, text=True, check=True,
                              cwd=os.path.dirname(req), encoding='utf-8', errors='ignore')
                bot.reply_to(message, f"{PEM['ok']} Python deps installed.", parse_mode='HTML')
            except subprocess.CalledProcessError as e:
                bot.reply_to(message, f"{PEM['no']} pip failed:\n<pre>{html_lib.escape((e.stderr or e.stdout)[:2000])}</pre>",
                             parse_mode='HTML'); return
        if pkg:
            bot.reply_to(message, f"{PEM['wait']} Installing Node deps...", parse_mode='HTML')
            try:
                subprocess.run(['npm', 'install'], capture_output=True, text=True, check=True,
                              cwd=os.path.dirname(pkg), encoding='utf-8', errors='ignore')
                bot.reply_to(message, f"{PEM['ok']} Node deps installed.", parse_mode='HTML')
            except FileNotFoundError:
                bot.reply_to(message, f"{PEM['no']} npm not found.", parse_mode='HTML')
            except subprocess.CalledProcessError as e:
                bot.reply_to(message, f"{PEM['no']} npm failed:\n<pre>{html_lib.escape((e.stderr or e.stdout)[:2000])}</pre>",
                             parse_mode='HTML'); return
        py_files = [(r, b, f) for r, b, f in all_files if b.endswith('.py')]
        js_files = [(r, b, f) for r, b, f in all_files if b.endswith('.js')]
        py_files.sort(key=lambda x: (os.path.dirname(x[0]) != '', x[0]))
        js_files.sort(key=lambda x: (os.path.dirname(x[0]) != '', x[0]))
        main_script = None; ft = None
        for pref in ['main.py', 'bot.py', 'app.py']:
            mm = next((f for f in py_files if f[1] == pref), None)
            if mm: main_script = mm; ft = 'py'; break
        if not main_script:
            for pref in ['index.js', 'main.js', 'bot.js', 'app.js']:
                mm = next((f for f in js_files if f[1] == pref), None)
                if mm: main_script = mm; ft = 'js'; break
        if not main_script and py_files: main_script = py_files[0]; ft = 'py'
        if not main_script and js_files: main_script = js_files[0]; ft = 'js'
        if not main_script:
            bot.reply_to(message, f"{PEM['no']} No .py or .js found!", parse_mode='HTML'); return
        main_name = main_script[1]
        for rel, b, full in all_files:
            dst = os.path.join(folder, b)
            if os.path.isdir(dst): shutil.rmtree(dst)
            elif os.path.exists(dst): os.remove(dst)
            try: shutil.move(full, dst)
            except: pass
        save_user_file(uid, main_name, ft)
        main_path = os.path.join(folder, main_name)
        bot.reply_to(message, f"{PEM['ok']} Starting <code>{main_name}</code>...", parse_mode='HTML')
        if ft == 'py':
            threading.Thread(target=run_script, args=(main_path, uid, folder, main_name, message)).start()
        else:
            threading.Thread(target=run_js_script, args=(main_path, uid, folder, main_name, message)).start()
    except zipfile.BadZipFile as e:
        bot.reply_to(message, f"{PEM['no']} Invalid ZIP: {e}", parse_mode='HTML')
    except Exception as e:
        logger.error(f"zip err: {e}", exc_info=True)
        bot.reply_to(message, f"{PEM['no']} {str(e)}", parse_mode='HTML')
    finally:
        if tdir and os.path.exists(tdir):
            try: shutil.rmtree(tdir)
            except: pass


def handle_js_file(path, owner, folder, fn, msg):
    try:
        save_user_file(owner, fn, 'js')
        threading.Thread(target=run_js_script, args=(path, owner, folder, fn, msg)).start()
    except Exception as e:
        bot.reply_to(msg, f"{PEM['no']} {str(e)}", parse_mode='HTML')


def handle_py_file(path, owner, folder, fn, msg):
    try:
        save_user_file(owner, fn, 'py')
        threading.Thread(target=run_script, args=(path, owner, folder, fn, msg)).start()
    except Exception as e:
        bot.reply_to(msg, f"{PEM['no']} {str(e)}", parse_mode='HTML')


# ═══════════════════════════════════════════════════════════════
# LOGIC FUNCTIONS
# ═══════════════════════════════════════════════════════════════
def _logic_send_welcome(message):
    uid = message.from_user.id
    cid = message.chat.id
    name = message.from_user.first_name
    uname = message.from_user.username
    if bot_locked and uid not in admin_ids:
        bot.send_message(cid, f"{PEM['warn']} Bot locked.", parse_mode='HTML'); return
    photo = None
    try:
        p = bot.get_user_profile_photos(uid, limit=1)
        if p.photos: photo = p.photos[0][-1].file_id
    except: pass
    if uid not in active_users:
        add_active_user(uid)
        try:
            bot.send_message(OWNER_ID,
                             f"🎉 New user!\n👤 {name}\n✳️ @{uname or 'N/A'}\n🆔 <code>{uid}</code>",
                             parse_mode='HTML')
        except: pass
    limit = get_user_file_limit(uid); cur = get_user_file_count(uid)
    lim_str = str(limit) if limit != float('inf') else "Unlimited"
    exp_info = ""
    if uid == OWNER_ID: status = f"{PEM['crown']} Owner"
    elif uid in admin_ids: status = f"{PEM['admin']} Admin"
    elif uid in user_subscriptions:
        exp = user_subscriptions[uid].get('expiry')
        if exp and exp > datetime.now():
            status = f"{PEM['check']} Premium"
            days = (exp - datetime.now()).days
            exp_info = f"\n{PEM['wait']} Expires in: {days} days"
        else:
            status = f"{PEM['user']} Free (Expired)"; remove_subscription_db(uid)
    else: status = f"{PEM['user']} Free User"
    txt = (f"{PEM['hi']} <b>Welcome, {name}!</b>\n\n"
           f"{PEM['user']} ID: <code>{uid}</code>\n"
           f"{PEM['key']} Username: @{uname or 'Not set'}\n"
           f"{PEM['pin']} Status: {status}{exp_info}\n"
           f"{PEM['file']} Files: {cur} / {lim_str}\n"
           f"{PEM['gear']} Uptime: {get_uptime_str()}\n\n"
           f"{PEM['rocket']} Upload <code>.py</code>, <code>.js</code>, or <code>.zip</code>\n"
           f"{PEM['msg']} Git: <code>/gitclone URL</code>\n\n"
           f"{PEM['pin']} Use buttons below.")
    try:
        if photo:
            try: bot.send_photo(cid, photo)
            except: pass
        raw_send(cid, txt, reply_keyboard=create_reply_keyboard_main_menu(uid), parse_mode='HTML')
    except Exception as e: logger.error(f"Welcome: {e}")


def _logic_updates_channel(message):
    kb = [[ibtn('📢 Updates Channel', url=UPDATE_CHANNEL, emoji_id="5352597830089347330", style="primary")]]
    raw_send(message.chat.id,
             f"{PEM['msg']} <b>Join our Channel</b>\n\n{PEM['join']} {UPDATE_CHANNEL}",
             inline_keyboard=kb, parse_mode='HTML')


def _logic_upload_file(message):
    uid = message.from_user.id
    if bot_locked and uid not in admin_ids:
        bot.reply_to(message, f"{PEM['warn']} Bot locked.", parse_mode='HTML'); return
    if get_user_file_count(uid) >= get_user_file_limit(uid):
        bot.reply_to(message, f"{PEM['warn']} File limit reached.", parse_mode='HTML'); return
    raw_send(message.chat.id,
             f"{PEM['file']} <b>Upload File</b>\n\n"
             f"Send <code>.py</code>, <code>.js</code>, or <code>.zip</code>\n"
             f"{PEM['warn']} Max: <b>20 MB</b>\n"
             f"{PEM['pin']} Or use <code>/gitclone URL</code>",
             parse_mode='HTML')


def _logic_check_files(message):
    uid = message.from_user.id
    files = user_files.get(uid, [])
    if not files:
        raw_send(message.chat.id, f"{PEM['file']} No files.", parse_mode='HTML'); return
    kb = []
    for fn, ft in sorted(files):
        running = is_bot_running(uid, fn)
        icon = "🟢" if running else "🔴"
        kb.append([ibtn(f"{icon} {fn} ({ft})",
                       callback_data=f'file_{uid}_{_file_ref(uid, fn)}',   # 🆕 ref
                       emoji_id="5352721946054268944",
                       style="success" if running else "danger")])
    kb.append([ibtn("🔙 Back", callback_data='back_to_main', emoji_id="6109360506319935223", style="primary")])
    raw_send(message.chat.id,
             f"{PEM['file']} <b>Your Files</b>\n\n{PEM['pin']} Tap to manage:",
             inline_keyboard=kb, parse_mode='HTML')


def _logic_bot_speed(message):
    uid = message.from_user.id
    cid = message.chat.id
    start = time.time()
    wait = bot.reply_to(message, f"{PEM['wait']} Testing...", parse_mode='HTML')
    try:
        bot.send_chat_action(cid, 'typing')
        rt = round((time.time() - start) * 1000, 2)
        icon = "🟢" if rt < 500 else ("🟡" if rt < 1500 else "🔴")
        status = f"{PEM['ok']} Unlocked" if not bot_locked else f"{PEM['warn']} Locked"
        if uid == OWNER_ID: lvl = f"{PEM['crown']} Owner"
        elif uid in admin_ids: lvl = f"{PEM['admin']} Admin"
        elif uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now():
            lvl = f"{PEM['check']} Premium"
        else: lvl = f"{PEM['user']} Free"
        txt = (f"{PEM['speed']} <b>Speed Test</b>\n\n"
               f"{icon} <code>{rt} ms</code>\n"
               f"🚦 {status}\n"
               f"👤 {lvl}\n"
               f"⏱️ Uptime: {get_uptime_str()}")
        bot.edit_message_text(txt, cid, wait.message_id, parse_mode='HTML')
    except: pass


def _logic_contact_owner(message):
    kb = [[ibtn('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}',
                emoji_id="5337302974806922068", style="primary")]]
    raw_send(message.chat.id,
             f"{PEM['msg']} <b>Contact Owner</b>\n\n{PEM['user']} {YOUR_USERNAME}",
             inline_keyboard=kb, parse_mode='HTML')


def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    raw_send(message.chat.id,
             f"{PEM['money']} <b>Subscription Management</b>",
             inline_keyboard=create_subscription_menu(), parse_mode='HTML')


def _logic_statistics(message):
    uid = message.from_user.id
    total_users = len(active_users)
    total_files = sum(len(f) for f in user_files.values())
    running = 0; user_running = 0
    with bot_scripts_lock: keys = list(bot_scripts.keys())
    for k in keys:
        try:
            s_owner, _ = k.split('_', 1)
            with bot_scripts_lock: info = bot_scripts.get(k)
            if info and is_bot_running(int(s_owner), info['file_name']):
                running += 1
                if int(s_owner) == uid: user_running += 1
        except: continue
    txt = (f"{PEM['admin']} <b>Statistics</b>\n\n"
           f"{PEM['user']} Users: <code>{total_users}</code>\n"
           f"{PEM['file']} Files: <code>{total_files}</code>\n"
           f"🟢 Running: <code>{running}</code>\n")
    if uid in admin_ids:
        txt += f"🔒 Bot: <code>{'Locked' if bot_locked else 'Unlocked'}</code>\n"
    txt += f"🤖 Your Bots: <code>{user_running}</code>\n"
    txt += f"⏱️ Uptime: <code>{get_uptime_str()}</code>"
    bot.reply_to(message, txt, parse_mode='HTML')


def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    m = bot.reply_to(message, f"{PEM['msg']} Send broadcast.\n/cancel to abort.", parse_mode='HTML')
    bot.register_next_step_handler(m, process_broadcast_message)


def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    global bot_locked
    bot_locked = not bot_locked
    log_audit(message.from_user.id, "lock" if bot_locked else "unlock", "", "")
    bot.reply_to(message, f"{PEM['warn']} Bot {'LOCKED 🔒' if bot_locked else 'UNLOCKED 🔓'}.",
                 parse_mode='HTML')


def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    raw_send(message.chat.id,
             f"{PEM['crown']} <b>Admin Panel</b>\n\n{PEM['pin']} Select:",
             inline_keyboard=create_admin_panel(), parse_mode='HTML')


def _logic_run_all_scripts(mo):
    if isinstance(mo, telebot.types.Message):
        aid = mo.from_user.id; ac = mo.chat.id
        rep = lambda t, **k: bot.send_message(ac, t, **k); am = mo
    elif isinstance(mo, telebot.types.CallbackQuery):
        aid = mo.from_user.id; ac = mo.message.chat.id
        bot.answer_callback_query(mo.id)
        rep = lambda t, **k: bot.send_message(ac, t, **k); am = mo.message
    else: return
    if aid not in admin_ids:
        rep(f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    rep(f"{PEM['wait']} Starting all scripts...", parse_mode='HTML')
    started = 0; users = 0; skipped = 0
    snapshot = dict(user_files)
    for target, files in snapshot.items():
        if not files: continue
        users += 1
        folder = get_user_folder(target)
        for fn, ft in files:
            if not is_bot_running(target, fn):
                path = os.path.join(folder, fn)
                if os.path.exists(path):
                    try:
                        if ft == 'py':
                            threading.Thread(target=run_script, args=(path, target, folder, fn, am, 1, True)).start(); started += 1
                        elif ft == 'js':
                            threading.Thread(target=run_js_script, args=(path, target, folder, fn, am, 1, True)).start(); started += 1
                        else: skipped += 1
                        time.sleep(0.3)
                    except: skipped += 1
                else: skipped += 1
    rep(f"{PEM['ok']} <b>Done!</b>\n\n"
        f"▶️ Started: <code>{started}</code>\n"
        f"👥 Users: <code>{users}</code>\n"
        f"⚠️ Skipped: <code>{skipped}</code>", parse_mode='HTML')


def _logic_system_info(message):
    uid = message.from_user.id
    if uid not in admin_ids:
        bot.reply_to(message, f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    stats = get_system_stats()
    if not stats:
        bot.reply_to(message, f"{PEM['no']} Failed.", parse_mode='HTML'); return
    cpu_i = "🟢" if stats['cpu'] < 50 else ("🟡" if stats['cpu'] < 80 else "🔴")
    ram_i = "🟢" if stats['ram_pct'] < 70 else ("🟡" if stats['ram_pct'] < 90 else "🔴")
    disk_i = "🟢" if stats['disk_pct'] < 70 else ("🟡" if stats['disk_pct'] < 90 else "🔴")
    txt = (f"{PEM['speed']} <b>System Info</b>\n\n"
           f"{cpu_i} CPU: <code>{stats['cpu']:.1f}%</code>\n"
           f"{ram_i} RAM: <code>{stats['ram_used']:.2f}/{stats['ram_total']:.2f} GB</code>\n"
           f"{disk_i} Disk: <code>{stats['disk_used']:.2f}/{stats['disk_total']:.2f} GB</code>\n\n"
           f"⏱️ Uptime: <code>{stats['uptime']}</code>\n"
           f"🟢 Scripts: <code>{len(bot_scripts)}</code>")
    bot.reply_to(message, txt, parse_mode='HTML')


# ═══════════════════════════════════════════════════════════════
# AUDIT BUILD
# ═══════════════════════════════════════════════════════════════
def _build_audit_text(limit=20):
    logs = get_audit_logs(limit)
    if not logs: return None, None
    lines = [f"{PEM['admin']} <b>Audit Log (last {len(logs)})</b>\n"]
    icons = {"ban": "🚫", "unban": "✅", "add_admin": "➕", "remove_admin": "➖",
             "delete_file": "🗑️", "broadcast": "📢", "add_sub": "💳",
             "remove_sub": "❌", "lock": "🔒", "unlock": "🔓",
             "git_clone": "📦", "audit_cleared": "🗑️"}
    for ts, admin_id, action, target, details in logs:
        try: t = datetime.fromisoformat(ts).strftime("%m-%d %H:%M")
        except: t = str(ts)[:16]
        ic = icons.get(action, "•")
        line = f"{ic} <code>{t}</code> | <code>{admin_id}</code> | <b>{action}</b>"
        if target: line += f" → <code>{target}</code>"
        lines.append(line)
    txt = "\n".join(lines)
    if len(txt) > 4000: txt = txt[:4000] + "\n..."
    kb = [[
        ibtn("🗑️ Clear", callback_data="audit_clear", emoji_id="6188343249791358585", style="danger"),
        ibtn("🔄 Refresh", callback_data="audit_refresh", emoji_id="6186175669991379791", style="primary"),
        ibtn("🔙 Back", callback_data='admin_panel', emoji_id="6109360506319935223", style="primary")
    ]]
    return txt, kb


# ═══════════════════════════════════════════════════════════════
# GIT CLONE (🆕 background thread)
# ═══════════════════════════════════════════════════════════════
@bot.message_handler(commands=['gitclone'])
def cmd_gitclone(message):
    uid = message.from_user.id
    cid = message.chat.id
    if bot_locked and uid not in admin_ids:
        raw_send(cid, f"{PEM['warn']} Bot locked.", parse_mode='HTML'); return
    if get_user_file_count(uid) >= get_user_file_limit(uid):
        raw_send(cid, f"{PEM['warn']} File limit reached.", parse_mode='HTML'); return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        raw_send(cid,
                 f"{PEM['pin']} <b>Git Clone</b>\n\n"
                 f"<code>/gitclone &lt;repo_url&gt; [branch]</code>\n\n"
                 f"Supported: GitHub, GitLab, Bitbucket (HTTPS)",
                 parse_mode='HTML'); return
    parts = args[1].split()
    url = parts[0].strip()
    branch = parts[1] if len(parts) > 1 else None
    if not re.match(r'^https://(github\.com|gitlab\.com|bitbucket\.org)/[\w\-\.]+/[\w\-\.]+', url):
        raw_send(cid, f"{PEM['no']} Invalid URL. Only GitHub/GitLab/Bitbucket HTTPS.", parse_mode='HTML'); return
    status_msg = bot.reply_to(message, f"{PEM['wait']} Cloning in background...", parse_mode='HTML')
    threading.Thread(
        target=_do_gitclone_bg,
        args=(uid, cid, status_msg.message_id, url, branch),
        daemon=True
    ).start()


def _do_gitclone_bg(uid, cid, msg_id, url, branch):
    """🆕 Git clone in background — polling thread block করে না।"""
    fake_msg = _FakeMessage(cid, msg_id)
    tdir = None
    try:
        tdir = tempfile.mkdtemp(prefix=f"git_{uid}_")
        repo_dir = os.path.join(tdir, 'repo')
        cmd = ['git', 'clone', '--depth', '1']
        if branch: cmd.extend(['--branch', branch])
        cmd.extend([url, repo_dir])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           encoding='utf-8', errors='ignore')
        if r.returncode != 0:
            err = html_lib.escape((r.stderr or r.stdout)[:500])
            bot.edit_message_text(f"{PEM['no']} Clone failed:\n<pre>{err}</pre>",
                                 cid, msg_id, parse_mode='HTML'); return
        total_size = 0
        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d != '.git']
            for f in files: total_size += os.path.getsize(os.path.join(root, f))
        if total_size > 20 * 1024 * 1024:
            bot.edit_message_text(f"{PEM['no']} Repo too large ({_fmt_size(total_size)})",
                                 cid, msg_id, parse_mode='HTML'); return
        py_files = []; js_files = []
        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', '.venv']]
            for f in files:
                if f.endswith('.py'): py_files.append(os.path.join(root, f))
                elif f.endswith('.js'): js_files.append(os.path.join(root, f))
        main_script = None; ft = None
        for pref in ['main.py', 'bot.py', 'app.py']:
            for p in py_files:
                if os.path.basename(p) == pref: main_script = p; ft = 'py'; break
            if main_script: break
        if not main_script:
            for pref in ['index.js', 'main.js', 'bot.js', 'app.js']:
                for p in js_files:
                    if os.path.basename(p) == pref: main_script = p; ft = 'js'; break
                if main_script: break
        if not main_script and py_files: main_script = py_files[0]; ft = 'py'
        if not main_script and js_files: main_script = js_files[0]; ft = 'js'
        if not main_script:
            bot.edit_message_text(f"{PEM['no']} No .py or .js in repo.",
                                 cid, msg_id, parse_mode='HTML'); return
        req = None; pkg = None
        for root, _, files in os.walk(repo_dir):
            if 'requirements.txt' in files: req = os.path.join(root, 'requirements.txt')
            if 'package.json' in files: pkg = os.path.join(root, 'package.json')
        if req:
            bot.edit_message_text(f"{PEM['wait']} Installing Python deps...", cid, msg_id, parse_mode='HTML')
            try: subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', req],
                              capture_output=True, timeout=180, encoding='utf-8', errors='ignore')
            except: pass
        if pkg:
            bot.edit_message_text(f"{PEM['wait']} Installing Node deps...", cid, msg_id, parse_mode='HTML')
            try: subprocess.run(['npm', 'install'], cwd=os.path.dirname(pkg),
                              capture_output=True, timeout=180, encoding='utf-8', errors='ignore')
            except: pass
        user_folder = get_user_folder(uid)
        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', '.venv']]
            for f in files:
                src = os.path.join(root, f); dst = os.path.join(user_folder, f)
                try: shutil.copy2(src, dst)
                except: pass
        main_name = os.path.basename(main_script)
        save_user_file(uid, main_name, ft)
        main_path = os.path.join(user_folder, main_name)
        log_audit(uid, "git_clone", main_name, url)
        bot.edit_message_text(
            f"{PEM['ok']} <b>Cloned!</b>\n\n"
            f"{PEM['file']} Main: <code>{main_name}</code>\n"
            f"{PEM['gear']} Type: <code>{ft.upper()}</code>\n"
            f"📦 Size: <code>{_fmt_size(total_size)}</code>\n\n"
            f"{PEM['rocket']} Starting...",
            cid, msg_id, parse_mode='HTML')
        if ft == 'py':
            threading.Thread(target=run_script, args=(main_path, uid, user_folder, main_name, fake_msg)).start()
        else:
            threading.Thread(target=run_js_script, args=(main_path, uid, user_folder, main_name, fake_msg)).start()
    except subprocess.TimeoutExpired:
        try: bot.edit_message_text(f"{PEM['no']} Clone timeout.", cid, msg_id, parse_mode='HTML')
        except: pass
    except Exception as e:
        logger.error(f"gitclone: {e}", exc_info=True)
        try: bot.edit_message_text(f"{PEM['no']} {html_lib.escape(str(e)[:300])}",
                                  cid, msg_id, parse_mode='HTML')
        except: pass
    finally:
        if tdir and os.path.exists(tdir):
            try: shutil.rmtree(tdir, ignore_errors=True)
            except: pass


# ═══════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════
@bot.message_handler(commands=['start', 'help'])
def cmd_welcome(message): _logic_send_welcome(message)


@bot.message_handler(commands=['status', 'statistics'])
def cmd_status(message): _logic_statistics(message)


@bot.message_handler(commands=['system'])
def cmd_system(message): _logic_system_info(message)


@bot.message_handler(commands=['uptime'])
def cmd_uptime(message):
    bot.reply_to(message, f"⏱️ Uptime: <code>{get_uptime_str()}</code>", parse_mode='HTML')


@bot.message_handler(commands=['audit'])
def cmd_audit(message):
    if message.from_user.id not in admin_ids:
        raw_send(message.chat.id, f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    args = message.text.split()
    limit = 20
    if len(args) > 1:
        try: limit = min(int(args[1]), 100)
        except: pass
    txt, kb = _build_audit_text(limit)
    if not txt:
        raw_send(message.chat.id, f"{PEM['admin']} No audit logs yet.", parse_mode='HTML'); return
    raw_send(message.chat.id, txt, inline_keyboard=kb, parse_mode='HTML')


BUTTON_TEXT_TO_LOGIC = {
    "📢 Updates Channel": _logic_updates_channel,
    "📤 Upload File": _logic_upload_file,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": _logic_bot_speed,
    "📞 Contact Owner": _logic_contact_owner,
    "📊 Statistics": _logic_statistics,
    "💳 Subscriptions": _logic_subscriptions_panel,
    "📢 Broadcast": _logic_broadcast_init,
    "🔒 Lock Bot": _logic_toggle_lock_bot,
    "🟢 Running All Code": _logic_run_all_scripts,
    "👑 Admin Panel": _logic_admin_panel,
}


@bot.message_handler(func=lambda m: m.text in BUTTON_TEXT_TO_LOGIC)
def handle_button(m):
    fn = BUTTON_TEXT_TO_LOGIC.get(m.text)
    if fn: fn(m)


@bot.message_handler(commands=['updateschannel'])
def cmd_updates(m): _logic_updates_channel(m)

@bot.message_handler(commands=['uploadfile'])
def cmd_upload(m): _logic_upload_file(m)

@bot.message_handler(commands=['checkfiles'])
def cmd_files(m): _logic_check_files(m)

@bot.message_handler(commands=['botspeed'])
def cmd_speed(m): _logic_bot_speed(m)

@bot.message_handler(commands=['contactowner'])
def cmd_contact(m): _logic_contact_owner(m)

@bot.message_handler(commands=['subscriptions'])
def cmd_subs(m): _logic_subscriptions_panel(m)

@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(m): _logic_broadcast_init(m)

@bot.message_handler(commands=['lockbot'])
def cmd_lock(m): _logic_toggle_lock_bot(m)

@bot.message_handler(commands=['adminpanel'])
def cmd_admin(m): _logic_admin_panel(m)

@bot.message_handler(commands=['runningallcode'])
def cmd_runall(m): _logic_run_all_scripts(m)


@bot.message_handler(commands=['ping'])
def cmd_ping(message):
    s = time.time()
    msg = bot.reply_to(message, "Pong!")
    bot.edit_message_text(f"Pong! <code>{round((time.time() - s) * 1000, 2)} ms</code>",
                          message.chat.id, msg.message_id, parse_mode='HTML')


# ═══════════════════════════════════════════════════════════════
# DOCUMENT HANDLER
# ═══════════════════════════════════════════════════════════════
@bot.message_handler(content_types=['document'])
def handle_doc(message):
    uid = message.from_user.id
    cid = message.chat.id
    doc = message.document
    if bot_locked and uid not in admin_ids:
        bot.reply_to(message, f"{PEM['warn']} Bot locked.", parse_mode='HTML'); return
    if get_user_file_count(uid) >= get_user_file_limit(uid):
        bot.reply_to(message, f"{PEM['warn']} File limit reached.", parse_mode='HTML'); return
    fname = doc.file_name
    if not fname:
        bot.reply_to(message, f"{PEM['warn']} No file name.", parse_mode='HTML'); return
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, f"{PEM['no']} Only .py, .js, .zip.", parse_mode='HTML'); return
    if doc.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, f"{PEM['no']} Max 20MB.", parse_mode='HTML'); return
    try:
        try:
            bot.forward_message(OWNER_ID, cid, message.message_id)
            bot.send_message(OWNER_ID, f"⬆️ <code>{fname}</code> from <code>{uid}</code>", parse_mode='HTML')
        except: pass
        wait = bot.reply_to(message, f"{PEM['wait']} <b>Preparing...</b>", parse_mode='HTML')
        fi = bot.get_file(doc.file_id)
        content = download_with_progress(fi.file_path, cid, wait.message_id, doc.file_size, fname)
        try:
            bot.edit_message_text(
                f"{PEM['ok']} <b>Downloaded!</b>\n\n"
                f"{PEM['file']} <code>{fname}</code>\n"
                f"[{'█' * 20}] <b>100%</b>\n"
                f"<code>{_fmt_size(len(content))}</code>",
                cid, wait.message_id, parse_mode='HTML')
        except: pass
        folder = get_user_folder(uid)
        if ext == '.zip':
            handle_zip_file(content, fname, message)
        else:
            path = os.path.join(folder, fname)
            with open(path, 'wb') as f: f.write(content)
            if ext == '.js': handle_js_file(path, uid, folder, fname, message)
            elif ext == '.py': handle_py_file(path, uid, folder, fname, message)
    except Exception as e:
        logger.error(f"Upload err: {e}", exc_info=True)
        bot.reply_to(message, f"{PEM['no']} {html_lib.escape(str(e)[:300])}", parse_mode='HTML')


# ═══════════════════════════════════════════════════════════════
# CALLBACK ROUTER
# ═══════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(call):
    uid = call.from_user.id
    data = call.data
    if bot_locked and uid not in admin_ids and data not in ['back_to_main', 'speed', 'stats']:
        bot.answer_callback_query(call.id, "⚠️ Bot locked.", show_alert=True); return
    try:
        if data.startswith('live_pause_'): cb_live_pause(call)
        elif data.startswith('live_resume_'): cb_live_resume(call)
        elif data.startswith('live_stop_'): cb_live_stop(call)
        elif data == 'upload': cb_upload(call)
        elif data == 'check_files': cb_check_files(call)
        elif data.startswith('file_'): cb_file_control(call)
        elif data.startswith('start_'): cb_start(call)
        elif data.startswith('stop_'): cb_stop(call)
        elif data.startswith('restart_'): cb_restart(call)
        elif data.startswith('delete_'): cb_delete(call)
        elif data.startswith('logs_'): cb_logs(call)
        elif data == 'speed': cb_speed(call)
        elif data == 'back_to_main': cb_back(call)
        elif data.startswith('confirm_broadcast_'): cb_confirm_broadcast(call)
        elif data == 'cancel_broadcast': cb_cancel_broadcast(call)
        elif data == 'subscription': admin_cb(call, cb_submenu)
        elif data == 'stats': cb_stats(call)
        elif data == 'lock_bot': admin_cb(call, cb_lock)
        elif data == 'unlock_bot': admin_cb(call, cb_unlock)
        elif data == 'run_all_scripts': admin_cb(call, cb_runall)
        elif data == 'broadcast': admin_cb(call, cb_broadcast)
        elif data == 'admin_panel': admin_cb(call, cb_admin)
        elif data == 'system_info': admin_cb(call, cb_system_info)
        elif data == 'audit_view': admin_cb(call, cb_audit_view)
        elif data == 'audit_clear': admin_cb(call, cb_audit_clear)
        elif data == 'audit_refresh': admin_cb(call, cb_audit_refresh)
        elif data == 'add_admin': owner_cb(call, cb_add_admin)
        elif data == 'remove_admin': owner_cb(call, cb_rem_admin)
        elif data == 'list_admins': admin_cb(call, cb_list_admins)
        elif data == 'add_subscription': admin_cb(call, cb_add_sub)
        elif data == 'remove_subscription': admin_cb(call, cb_rem_sub)
        elif data == 'check_subscription': admin_cb(call, cb_check_sub)
        else: bot.answer_callback_query(call.id, "Unknown.")
    except Exception as e:
        logger.error(f"Callback err: {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, "Error.", show_alert=True)
        except: pass


def admin_cb(call, fn):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    fn(call)


def owner_cb(call, fn):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner only.", show_alert=True); return
    fn(call)


# ═══════════════════════════════════════════════════════════════
# LIVE LOG CALLBACKS (🆕 resolve ref)
# ═══════════════════════════════════════════════════════════════
def cb_logs(call):
    try:
        _, owner_str, ref = call.data.split('_', 2)
        owner = int(owner_str)
        fname, _ = _resolve_ref(owner, ref)
        if not fname:
            bot.answer_callback_query(call.id, "⚠️ File no longer exists.", show_alert=True); return
        if not (call.from_user.id == owner or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ No permission.", show_alert=True); return
        folder = get_user_folder(owner)
        lp = os.path.join(folder, f"{os.path.splitext(fname)[0]}.log")
        if not os.path.exists(lp):
            bot.answer_callback_query(call.id, "⚠️ No logs yet.", show_alert=True); return
        chat_id = call.message.chat.id
        _clear_view_state(chat_id, call.message.message_id)
        session_key = f"{chat_id}_{call.message.message_id}"
        content = _read_log_tail(lp, 20)
        if len(content) > 3400: content = "..." + content[-3400:]
        is_run = is_bot_running(owner, fname)
        now_str = time.strftime('%H:%M:%S')
        header = (f"{PEM['file']} <b>Live Logs: {fname}</b>\n"
                  f"Status: {'🟢 Running' if is_run else '🔴 Stopped'}  |  "
                  f"{PEM['wait']} Updated: {now_str}\n\n"
                  f"<pre>{html_lib.escape(content)}</pre>")
        bot.answer_callback_query(call.id, "🔴 Live started")
        raw_edit(chat_id, call.message.message_id, header,
                 inline_keyboard=_live_log_controls(owner, fname, False), parse_mode='HTML')
        with _live_logs_lock:
            _live_logs[session_key] = {
                'owner': owner, 'fname': fname,
                'chat_id': chat_id, 'message_id': call.message.message_id,
                'paused': False, 'active': True,
            }
        threading.Thread(target=_live_log_worker, args=(session_key,), daemon=True).start()
    except Exception as e: logger.error(f"cb_logs: {e}")


def cb_live_pause(call):
    try:
        _, _, owner_str, ref = call.data.split('_', 3)
        owner = int(owner_str)
        fname, _ = _resolve_ref(owner, ref)
        if not fname:
            bot.answer_callback_query(call.id, "⚠️ File gone.", show_alert=True); return
        session_key = f"{call.message.chat.id}_{call.message.message_id}"
        with _live_logs_lock:
            sess = _live_logs.get(session_key)
            if sess: sess['paused'] = True
        bot.answer_callback_query(call.id, "⏸️ Paused")
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['wait']} <b>Logs Paused</b>\n\n"
                 f"{PEM['file']} <code>{fname}</code>\n"
                 f"{PEM['pin']} Click Resume to continue",
                 inline_keyboard=_live_log_controls(owner, fname, True), parse_mode='HTML')
    except Exception as e: logger.error(f"live_pause: {e}")


def cb_live_resume(call):
    try:
        _, _, owner_str, ref = call.data.split('_', 3)
        session_key = f"{call.message.chat.id}_{call.message.message_id}"
        with _live_logs_lock:
            sess = _live_logs.get(session_key)
            if sess: sess['paused'] = False
        bot.answer_callback_query(call.id, "▶️ Resumed")
    except Exception as e: logger.error(f"live_resume: {e}")


def cb_live_stop(call):
    try:
        _, _, owner_str, ref = call.data.split('_', 3)
        owner = int(owner_str)
        fname, _ = _resolve_ref(owner, ref)
        if not fname:
            bot.answer_callback_query(call.id, "⚠️ File gone.", show_alert=True); return
        session_key = f"{call.message.chat.id}_{call.message.message_id}"
        with _live_logs_lock:
            sess = _live_logs.pop(session_key, None)
            if sess: sess['active'] = False
        bot.answer_callback_query(call.id, "⏹️ Stopped")
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['ok']} <b>Live Logs Stopped</b>\n\n"
                 f"{PEM['file']} <code>{fname}</code>",
                 inline_keyboard=[[
                     ibtn("🔙 Back to File", callback_data=f'file_{owner}_{ref}',
                          emoji_id="6109360506319935223", style="primary")
                 ]], parse_mode='HTML')
    except Exception as e: logger.error(f"live_stop: {e}")


# ═══════════════════════════════════════════════════════════════
# FILE / MENU CALLBACKS (🆕 resolve ref)
# ═══════════════════════════════════════════════════════════════
def cb_upload(call):
    if get_user_file_count(call.from_user.id) >= get_user_file_limit(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Limit reached.", show_alert=True); return
    bot.answer_callback_query(call.id)
    raw_send(call.message.chat.id,
             f"{PEM['file']} Send .py, .js, or .zip\n{PEM['warn']} Max 20MB.",
             parse_mode='HTML')


def cb_check_files(call):
    uid = call.from_user.id
    _clear_view_state(call.message.chat.id, call.message.message_id)
    files = user_files.get(uid, [])
    if not files:
        bot.answer_callback_query(call.id, "⚠️ No files.", show_alert=True)
        kb = [[ibtn("🔙 Back", callback_data='back_to_main', emoji_id="6109360506319935223", style="primary")]]
        try: raw_edit(call.message.chat.id, call.message.message_id,
                      f"{PEM['file']} No files.", inline_keyboard=kb, parse_mode='HTML')
        except: pass
        return
    bot.answer_callback_query(call.id)
    kb = []
    for fn, ft in sorted(files):
        running = is_bot_running(uid, fn)
        icon = "🟢" if running else "🔴"
        kb.append([ibtn(f"{icon} {fn} ({ft})",
                       callback_data=f'file_{uid}_{_file_ref(uid, fn)}',   # 🆕 ref
                       emoji_id="5352721946054268944",
                       style="success" if running else "danger")])
    kb.append([ibtn("🔙 Back", callback_data='back_to_main', emoji_id="6109360506319935223", style="primary")])
    try: raw_edit(call.message.chat.id, call.message.message_id,
                  f"{PEM['file']} <b>Your Files</b>\n\n{PEM['pin']} Tap to manage:",
                  inline_keyboard=kb, parse_mode='HTML')
    except: pass


def cb_file_control(call):
    try:
        _, owner_str, ref = call.data.split('_', 2)
        owner = int(owner_str)
        fname, ftype = _resolve_ref(owner, ref)   # 🆕
        if not fname:
            bot.answer_callback_query(call.id, "⚠️ File no longer exists.", show_alert=True); return
        if not (call.from_user.id == owner or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ No permission.", show_alert=True); return
        bot.answer_callback_query(call.id)
        _clear_view_state(call.message.chat.id, call.message.message_id)
        running = is_bot_running(owner, fname)
        status = f"{PEM['ok']} Running" if running else f"{PEM['no']} Stopped"
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['file']} <b>{fname}</b>\n\n"
                 f"{PEM['gear']} Type: <code>{ftype.upper()}</code>\n"
                 f"{PEM['pin']} Status: {status}",
                 inline_keyboard=create_control_buttons(owner, fname, running),
                 parse_mode='HTML')
        if running:
            sk = f"{call.message.chat.id}_{call.message.message_id}"
            with _spinner_views_lock:
                _active_spinners[sk] = {
                    'owner': owner, 'fname': fname,
                    'chat_id': call.message.chat.id,
                    'message_id': call.message.message_id,
                }
    except Exception as e: logger.error(f"cb_file_control: {e}")


def cb_start(call):
    try:
        _, owner_str, ref = call.data.split('_', 2)
        owner = int(owner_str)
        fname, ftype = _resolve_ref(owner, ref)
        if not fname:
            bot.answer_callback_query(call.id, "⚠️ File no longer exists.", show_alert=True); return
        if not (call.from_user.id == owner or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ No permission.", show_alert=True); return
        _clear_view_state(call.message.chat.id, call.message.message_id)
        folder = get_user_folder(owner); path = os.path.join(folder, fname)
        if not os.path.exists(path):
            bot.answer_callback_query(call.id, "⚠️ Missing file.", show_alert=True)
            remove_user_file_db(owner, fname); return
        if is_bot_running(owner, fname):
            bot.answer_callback_query(call.id, "⚠️ Already running.", show_alert=True); return
        bot.answer_callback_query(call.id, "⏳ Starting...")
        if ftype == 'py':
            threading.Thread(target=run_script, args=(path, owner, folder, fname, call.message)).start()
        elif ftype == 'js':
            threading.Thread(target=run_js_script, args=(path, owner, folder, fname, call.message)).start()
        time.sleep(1.5)
        running = is_bot_running(owner, fname)
        status = f"{PEM['ok']} Running" if running else "🟡 Starting"
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['file']} <b>{fname}</b>\n\n"
                 f"{PEM['gear']} Type: <code>{ftype.upper()}</code>\n"
                 f"{PEM['pin']} Status: {status}",
                 inline_keyboard=create_control_buttons(owner, fname, running),
                 parse_mode='HTML')
        if running:
            vsk = f"{call.message.chat.id}_{call.message.message_id}"
            with _spinner_views_lock:
                _active_spinners[vsk] = {
                    'owner': owner, 'fname': fname,
                    'chat_id': call.message.chat.id, 'message_id': call.message.message_id,
                }
    except Exception as e: logger.error(f"cb_start: {e}")


def cb_stop(call):
    try:
        _, owner_str, ref = call.data.split('_', 2)
        owner = int(owner_str)
        fname, ftype = _resolve_ref(owner, ref)
        if not fname:
            bot.answer_callback_query(call.id, "⚠️ File no longer exists.", show_alert=True); return
        if not (call.from_user.id == owner or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ No permission.", show_alert=True); return
        _clear_view_state(call.message.chat.id, call.message.message_id)
        sk = f"{owner}_{fname}"
        if not is_bot_running(owner, fname):
            bot.answer_callback_query(call.id, "⚠️ Already stopped.", show_alert=True); return
        bot.answer_callback_query(call.id, "⏳ Stopping...")
        with bot_scripts_lock: i = bot_scripts.get(sk)
        if i: kill_process_tree(i)
        with bot_scripts_lock: bot_scripts.pop(sk, None)
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['file']} <b>{fname}</b>\n\n"
                 f"{PEM['gear']} Type: <code>{ftype.upper()}</code>\n"
                 f"{PEM['pin']} Status: {PEM['no']} Stopped",
                 inline_keyboard=create_control_buttons(owner, fname, False),
                 parse_mode='HTML')
    except Exception as e: logger.error(f"cb_stop: {e}")


def cb_restart(call):
    try:
        _, owner_str, ref = call.data.split('_', 2)
        owner = int(owner_str)
        fname, ftype = _resolve_ref(owner, ref)
        if not fname:
            bot.answer_callback_query(call.id, "⚠️ File no longer exists.", show_alert=True); return
        if not (call.from_user.id == owner or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ No permission.", show_alert=True); return
        _clear_view_state(call.message.chat.id, call.message.message_id)
        folder = get_user_folder(owner); path = os.path.join(folder, fname); sk = f"{owner}_{fname}"
        if not os.path.exists(path):
            bot.answer_callback_query(call.id, "⚠️ Missing file.", show_alert=True); return
        bot.answer_callback_query(call.id, "⏳ Restarting...")
        if is_bot_running(owner, fname):
            with bot_scripts_lock: i = bot_scripts.get(sk)
            if i: kill_process_tree(i)
            with bot_scripts_lock: bot_scripts.pop(sk, None)
            time.sleep(1.5)
        if ftype == 'py':
            threading.Thread(target=run_script, args=(path, owner, folder, fname, call.message)).start()
        elif ftype == 'js':
            threading.Thread(target=run_js_script, args=(path, owner, folder, fname, call.message)).start()
        time.sleep(1.5)
        running = is_bot_running(owner, fname)
        status = f"{PEM['ok']} Running" if running else "🟡 Starting"
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['file']} <b>{fname}</b>\n\n"
                 f"{PEM['gear']} Type: <code>{ftype.upper()}</code>\n"
                 f"{PEM['pin']} Status: {status}",
                 inline_keyboard=create_control_buttons(owner, fname, running),
                 parse_mode='HTML')
        if running:
            vsk = f"{call.message.chat.id}_{call.message.message_id}"
            with _spinner_views_lock:
                _active_spinners[vsk] = {
                    'owner': owner, 'fname': fname,
                    'chat_id': call.message.chat.id, 'message_id': call.message.message_id,
                }
    except Exception as e: logger.error(f"cb_restart: {e}")


def cb_delete(call):
    try:
        _, owner_str, ref = call.data.split('_', 2)
        owner = int(owner_str)
        fname, _ = _resolve_ref(owner, ref)
        if not fname:
            bot.answer_callback_query(call.id, "⚠️ File no longer exists.", show_alert=True); return
        if not (call.from_user.id == owner or call.from_user.id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ No permission.", show_alert=True); return
        _clear_view_state(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "🗑️ Deleting...")
        sk = f"{owner}_{fname}"
        if is_bot_running(owner, fname):
            with bot_scripts_lock: i = bot_scripts.get(sk)
            if i: kill_process_tree(i)
            with bot_scripts_lock: bot_scripts.pop(sk, None)
            time.sleep(0.5)
        folder = get_user_folder(owner)
        for p in [os.path.join(folder, fname),
                  os.path.join(folder, f"{os.path.splitext(fname)[0]}.log")]:
            if os.path.exists(p):
                try: os.remove(p)
                except: pass
        remove_user_file_db(owner, fname)
        log_audit(call.from_user.id, "delete_file", fname, f"owner={owner}")
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['ok']} <b>Deleted</b>\n\n{PEM['file']} <code>{fname}</code>",
                 parse_mode='HTML')
    except Exception as e: logger.error(f"cb_delete: {e}")


def cb_speed(call):
    uid = call.from_user.id
    try:
        s = time.time()
        raw_edit(call.message.chat.id, call.message.message_id, f"{PEM['wait']} Testing...", parse_mode='HTML')
        bot.send_chat_action(call.message.chat.id, 'typing')
        rt = round((time.time() - s) * 1000, 2)
        icon = "🟢" if rt < 500 else ("🟡" if rt < 1500 else "🔴")
        status = f"{PEM['ok']} Unlocked" if not bot_locked else f"{PEM['warn']} Locked"
        if uid == OWNER_ID: lvl = f"{PEM['crown']} Owner"
        elif uid in admin_ids: lvl = f"{PEM['admin']} Admin"
        elif uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now():
            lvl = f"{PEM['check']} Premium"
        else: lvl = f"{PEM['user']} Free"
        bot.answer_callback_query(call.id)
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['speed']} <b>Speed Test</b>\n\n"
                 f"{icon} <code>{rt} ms</code>\n"
                 f"🚦 {status}\n"
                 f"👤 {lvl}",
                 inline_keyboard=create_main_menu_inline(uid), parse_mode='HTML')
    except: pass


def cb_back(call):
    uid = call.from_user.id
    _clear_view_state(call.message.chat.id, call.message.message_id)
    limit = get_user_file_limit(uid); cur = get_user_file_count(uid)
    lim_str = str(limit) if limit != float('inf') else "Unlimited"
    if uid == OWNER_ID: status = f"{PEM['crown']} Owner"
    elif uid in admin_ids: status = f"{PEM['admin']} Admin"
    elif uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now():
        status = f"{PEM['check']} Premium"
    else: status = f"{PEM['user']} Free"
    txt = (f"{PEM['hi']} <b>Welcome back, {call.from_user.first_name}!</b>\n\n"
           f"{PEM['user']} ID: <code>{uid}</code>\n"
           f"{PEM['pin']} Status: {status}\n"
           f"{PEM['file']} Files: {cur} / {lim_str}\n"
           f"{PEM['gear']} Uptime: {get_uptime_str()}")
    try:
        bot.answer_callback_query(call.id)
        raw_edit(call.message.chat.id, call.message.message_id, txt,
                 inline_keyboard=create_main_menu_inline(uid), parse_mode='HTML')
    except: pass


def cb_submenu(call):
    bot.answer_callback_query(call.id)
    raw_edit(call.message.chat.id, call.message.message_id,
             f"{PEM['money']} <b>Subscription Management</b>",
             inline_keyboard=create_subscription_menu(), parse_mode='HTML')


def cb_stats(call):
    bot.answer_callback_query(call.id)
    _logic_statistics(call.message)


def cb_lock(call):
    global bot_locked
    bot_locked = True
    log_audit(call.from_user.id, "lock", "", "")
    bot.answer_callback_query(call.id, "🔒 Locked.")
    try:
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['warn']} <b>Bot Locked</b>",
                 inline_keyboard=create_main_menu_inline(call.from_user.id), parse_mode='HTML')
    except: pass


def cb_unlock(call):
    global bot_locked
    bot_locked = False
    log_audit(call.from_user.id, "unlock", "", "")
    bot.answer_callback_query(call.id, "🔓 Unlocked.")
    try:
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['ok']} <b>Bot Unlocked</b>",
                 inline_keyboard=create_main_menu_inline(call.from_user.id), parse_mode='HTML')
    except: pass


def cb_runall(call): _logic_run_all_scripts(call)


def cb_system_info(call):
    uid = call.from_user.id
    if uid not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    bot.answer_callback_query(call.id)
    stats = get_system_stats()
    if not stats:
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['no']} Failed.", inline_keyboard=create_admin_panel(), parse_mode='HTML'); return
    cpu_i = "🟢" if stats['cpu'] < 50 else ("🟡" if stats['cpu'] < 80 else "🔴")
    ram_i = "🟢" if stats['ram_pct'] < 70 else ("🟡" if stats['ram_pct'] < 90 else "🔴")
    disk_i = "🟢" if stats['disk_pct'] < 70 else ("🟡" if stats['disk_pct'] < 90 else "🔴")
    txt = (f"{PEM['speed']} <b>System Info</b>\n\n"
           f"{cpu_i} CPU: <code>{stats['cpu']:.1f}%</code>\n"
           f"{ram_i} RAM: <code>{stats['ram_pct']:.1f}%</code>\n"
           f"{disk_i} Disk: <code>{stats['disk_pct']:.1f}%</code>\n\n"
           f"⏱️ Uptime: <code>{stats['uptime']}</code>\n"
           f"🟢 Scripts: <code>{len(bot_scripts)}</code>")
    raw_edit(call.message.chat.id, call.message.message_id, txt,
             inline_keyboard=create_admin_panel(), parse_mode='HTML')


def cb_audit_view(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    bot.answer_callback_query(call.id)
    txt, kb = _build_audit_text(20)
    if not txt:
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['admin']} No audit logs yet.",
                 inline_keyboard=[[ibtn("🔙 Back", callback_data='admin_panel', emoji_id="6109360506319935223", style="primary")]],
                 parse_mode='HTML'); return
    raw_edit(call.message.chat.id, call.message.message_id, txt, inline_keyboard=kb, parse_mode='HTML')


def cb_audit_clear(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner only.", show_alert=True); return
    clear_audit_logs()
    log_audit(call.from_user.id, "audit_cleared", "", "")
    bot.answer_callback_query(call.id, "🗑️ Cleared")
    raw_edit(call.message.chat.id, call.message.message_id,
             f"{PEM['ok']} Audit log cleared.",
             inline_keyboard=[[ibtn("🔙 Back", callback_data='admin_panel', emoji_id="6109360506319935223", style="primary")]],
             parse_mode='HTML')


def cb_audit_refresh(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    bot.answer_callback_query(call.id, "🔄 Refreshed")
    txt, kb = _build_audit_text(20)
    if not txt:
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['admin']} No audit logs.",
                 inline_keyboard=[[ibtn("🔙 Back", callback_data='admin_panel', emoji_id="6109360506319935223", style="primary")]],
                 parse_mode='HTML'); return
    raw_edit(call.message.chat.id, call.message.message_id, txt, inline_keyboard=kb, parse_mode='HTML')


def cb_broadcast(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, f"{PEM['msg']} Send broadcast.\n/cancel to abort.", parse_mode='HTML')
    bot.register_next_step_handler(m, process_broadcast_message)


def process_broadcast_message(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled."); return
    content = message.text
    if not content and not (message.photo or message.video):
        bot.reply_to(message, f"{PEM['no']} Empty.", parse_mode='HTML'); return
    kb = [[ibtn("✅ Send", callback_data=f"confirm_broadcast_{message.message_id}",
                emoji_id="6111726981760423576", style="success"),
           ibtn("❌ Cancel", callback_data="cancel_broadcast",
                emoji_id="6311965254817423602", style="danger")]]
    preview = html_lib.escape(content[:1000].strip()) if content else "(Media)"
    raw_send(message.chat.id,
             f"{PEM['warn']} <b>Confirm Broadcast</b>\n\n"
             f"<pre>{preview}</pre>\n\n"
             f"To <b>{len(active_users)}</b> users?",
             inline_keyboard=kb, parse_mode='HTML')


def cb_confirm_broadcast(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    try:
        orig = call.message.reply_to_message
        if not orig: raise ValueError("Original not found.")
        txt = pid = vid = None
        if orig.text: txt = orig.text
        elif orig.photo: pid = orig.photo[-1].file_id
        elif orig.video: vid = orig.video.file_id
        else: raise ValueError("No content.")
        log_audit(call.from_user.id, "broadcast", f"{len(active_users)} users", (txt or "")[:100])
        bot.answer_callback_query(call.id, "🚀 Broadcasting...")
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['wait']} Broadcasting to {len(active_users)} users...", parse_mode='HTML')
        threading.Thread(target=exec_broadcast, args=(
            txt, pid, vid, orig.caption if (pid or vid) else None,
            call.message.chat.id)).start()
    except Exception as e:
        raw_edit(call.message.chat.id, call.message.message_id,
                 f"{PEM['no']} {html_lib.escape(str(e))}", parse_mode='HTML')


def cb_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "Cancelled.")
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass


def exec_broadcast(txt, pid, vid, caption, admin_chat):
    sent = failed = blocked = 0
    start = time.time()
    users = list(active_users); total = len(users)
    for i, uid in enumerate(users):
        try:
            if txt: bot.send_message(uid, txt, parse_mode='HTML')
            elif pid: bot.send_photo(uid, pid, caption=caption, parse_mode='HTML' if caption else None)
            elif vid: bot.send_video(uid, vid, caption=caption, parse_mode='HTML' if caption else None)
            sent += 1
        except telebot.apihelper.ApiTelegramException as e:
            err = str(e).lower()
            if any(s in err for s in ["blocked", "deactivated", "not found", "kicked"]): blocked += 1
            elif "flood" in err or "too many" in err:
                time.sleep(6)
                try:
                    if txt: bot.send_message(uid, txt, parse_mode='HTML'); sent += 1
                except: failed += 1
            else: failed += 1
        except: failed += 1
        if (i + 1) % 25 == 0 and i < total - 1: time.sleep(1.5)
        elif i % 5 == 0: time.sleep(0.2)
    result = (f"{PEM['ok']} <b>Broadcast Complete!</b>\n\n"
              f"✅ Sent: <code>{sent}</code>\n"
              f"❌ Failed: <code>{failed}</code>\n"
              f"🚫 Blocked: <code>{blocked}</code>\n"
              f"👥 Targets: <code>{total}</code>\n"
              f"⏱️ {round(time.time() - start, 2)}s")
    try: raw_send(admin_chat, result, parse_mode='HTML')
    except: pass


def cb_admin(call):
    bot.answer_callback_query(call.id)
    raw_edit(call.message.chat.id, call.message.message_id,
             f"{PEM['crown']} <b>Admin Panel</b>",
             inline_keyboard=create_admin_panel(), parse_mode='HTML')


def cb_add_admin(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id,
                         f"{PEM['crown']} Enter User ID.\n/cancel to abort.", parse_mode='HTML')
    bot.register_next_step_handler(m, process_add_admin)


def process_add_admin(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, f"{PEM['no']} Owner only.", parse_mode='HTML'); return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled."); return
    try:
        nid = int(message.text.strip())
        if nid <= 0: raise ValueError()
        if nid == OWNER_ID: bot.reply_to(message, "⚠️ Already Owner."); return
        if nid in admin_ids: bot.reply_to(message, "⚠️ Already Admin."); return
        add_admin_db(nid)
        log_audit(message.from_user.id, "add_admin", nid, "")
        bot.reply_to(message, f"{PEM['ok']} Admin <code>{nid}</code> added.", parse_mode='HTML')
        try: bot.send_message(nid, f"{PEM['crown']} You are now Admin.")
        except: pass
    except ValueError:
        bot.reply_to(message, f"{PEM['no']} Invalid ID.", parse_mode='HTML')


def cb_rem_admin(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id,
                         f"{PEM['crown']} Enter Admin ID.\n/cancel to abort.", parse_mode='HTML')
    bot.register_next_step_handler(m, process_rem_admin)


def process_rem_admin(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, f"{PEM['no']} Owner only.", parse_mode='HTML'); return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled."); return
    try:
        rid = int(message.text.strip())
        if rid <= 0: raise ValueError()
        if rid == OWNER_ID: bot.reply_to(message, "⚠️ Cannot remove Owner."); return
        if rid not in admin_ids: bot.reply_to(message, "⚠️ Not Admin."); return
        if remove_admin_db(rid):
            log_audit(message.from_user.id, "remove_admin", rid, "")
            bot.reply_to(message, f"{PEM['ok']} Admin <code>{rid}</code> removed.", parse_mode='HTML')
            try: bot.send_message(rid, "ℹ️ You are no longer Admin.")
            except: pass
    except ValueError:
        bot.reply_to(message, f"{PEM['no']} Invalid ID.", parse_mode='HTML')


def cb_list_admins(call):
    bot.answer_callback_query(call.id)
    lst = "\n".join(f"• <code>{aid}</code> {'👑' if aid == OWNER_ID else '🛡️'}"
                    for aid in sorted(list(admin_ids)))
    raw_edit(call.message.chat.id, call.message.message_id,
             f"{PEM['crown']} <b>Admins</b>\n\n{lst}",
             inline_keyboard=create_admin_panel(), parse_mode='HTML')


def cb_add_sub(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id,
                         f"{PEM['money']} Enter <code>USER_ID DAYS</code>\n/cancel to abort.",
                         parse_mode='HTML')
    bot.register_next_step_handler(m, process_add_sub)


def process_add_sub(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled."); return
    try:
        parts = message.text.split()
        if len(parts) != 2: raise ValueError("Format: ID DAYS")
        uid = int(parts[0]); days = int(parts[1])
        if uid <= 0 or days <= 0: raise ValueError("Positive only")
        current = user_subscriptions.get(uid, {}).get('expiry')
        start = datetime.now()
        if current and current > start: start = current
        exp = start + timedelta(days=days)
        save_subscription(uid, exp)
        log_audit(message.from_user.id, "add_sub", uid, f"{days} days")
        bot.reply_to(message, f"{PEM['ok']} Sub <code>{uid}</code> for {days}d.\nExpires: {exp:%Y-%m-%d}",
                     parse_mode='HTML')
        try: bot.send_message(uid, f"{PEM['ok']} Sub activated! Expires: {exp:%Y-%m-%d}.")
        except: pass
    except ValueError as e:
        bot.reply_to(message, f"{PEM['no']} Invalid: {e}", parse_mode='HTML')


def cb_rem_sub(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id,
                         f"{PEM['money']} Enter User ID.\n/cancel to abort.", parse_mode='HTML')
    bot.register_next_step_handler(m, process_rem_sub)


def process_rem_sub(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled."); return
    try:
        uid = int(message.text.strip())
        if uid <= 0: raise ValueError()
        if uid not in user_subscriptions:
            bot.reply_to(message, f"{PEM['no']} No sub for <code>{uid}</code>.", parse_mode='HTML'); return
        remove_subscription_db(uid)
        log_audit(message.from_user.id, "remove_sub", uid, "")
        bot.reply_to(message, f"{PEM['ok']} Sub <code>{uid}</code> removed.", parse_mode='HTML')
    except ValueError:
        bot.reply_to(message, f"{PEM['no']} Invalid ID.", parse_mode='HTML')


def cb_check_sub(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id,
                         f"{PEM['money']} Enter User ID to check.\n/cancel to abort.", parse_mode='HTML')
    bot.register_next_step_handler(m, process_check_sub)


def process_check_sub(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, f"{PEM['no']} Admin only.", parse_mode='HTML'); return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled."); return
    try:
        uid = int(message.text.strip())
        if uid <= 0: raise ValueError()
        if uid in user_subscriptions:
            exp = user_subscriptions[uid].get('expiry')
            if exp and exp > datetime.now():
                days = (exp - datetime.now()).days
                bot.reply_to(message, f"{PEM['ok']} <code>{uid}</code> active.\nExpires: {exp:%Y-%m-%d} ({days}d)",
                             parse_mode='HTML')
            elif exp:
                bot.reply_to(message, f"{PEM['warn']} <code>{uid}</code> expired.", parse_mode='HTML')
                remove_subscription_db(uid)
        else:
            bot.reply_to(message, f"ℹ️ <code>{uid}</code> no sub.", parse_mode='HTML')
    except ValueError:
        bot.reply_to(message, f"{PEM['no']} Invalid ID.", parse_mode='HTML')


# ═══════════════════════════════════════════════════════════════
# CLEANUP & MAIN
# ═══════════════════════════════════════════════════════════════
def cleanup():
    logger.warning("Shutdown cleanup...")
    with _live_logs_lock:
        for k in list(_live_logs.keys()):
            _live_logs[k]['active'] = False
        _live_logs.clear()
    with _spinner_views_lock:
        _active_spinners.clear()
    with bot_scripts_lock:
        keys = list(bot_scripts.keys())
    for k in keys:
        with bot_scripts_lock:
            i = bot_scripts.get(k)
        if i: kill_process_tree(i)
    logger.warning("Done.")


atexit.register(cleanup)


if __name__ == '__main__':
    logger.info("=" * 40 + "\n🤖 Bot Starting Up...\n" +
                f"🐍 Python: {sys.version.split()[0]}\n" +
                f"🔑 Owner ID: {OWNER_ID}\n" +
                f"🛡️ Admins: {admin_ids}\n" + "=" * 40)
    keep_alive()
    logger.info("🚀 Starting polling...")
    while True:
        try:
            bot.infinity_polling(logger_level=logging.INFO, timeout=60, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            logger.warning("Timeout. Retry 5s..."); time.sleep(5)
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"Conn err: {ce}. Retry 15s..."); time.sleep(15)
        except Exception as e:
            logger.critical(f"💥 Error: {e}", exc_info=True); time.sleep(30)
        finally:
            time.sleep(1)