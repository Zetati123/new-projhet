import os
import json
import time
import threading
import requests
from datetime import datetime, timedelta
from flask import Flask, request, redirect, make_response, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ====================================================================
#                          الإعدادات العامة
# ====================================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = [int(id) for id in os.environ.get("ADMIN_IDS", "123456789").split(",")]

# ====================================================================
#                          Flask (السيرفر الوسيط)
# ====================================================================

app_flask = Flask(__name__)

# تخزين الكوكيز والروابط
sessions = {}
cookies_storage = {}

# تحميل الكوكيز المحفوظة من ملف (إذا كان موجوداً)
try:
    with open('cookies.json', 'r') as f:
        cookies_storage.update(json.load(f))
        print("✅ تم تحميل الكوكيز المحفوظة")
except FileNotFoundError:
    print("📝 لا توجد كوكيز محفوظة")

# ==================== دوال مساعدة ====================

def parse_cookies(cookies_text):
    """تحويل النص إلى قاموس كوكيز"""
    cookie_dict = {}
    lines = cookies_text.strip().split('\n')
    for line in lines:
        parts = line.split('\t')
        if len(parts) >= 7:
            key = parts[5]
            value = parts[6]
            if key and value:
                cookie_dict[key] = value
    return cookie_dict

def generate_token():
    """توليد معرف فريد"""
    return f"{int(time.time())}_{os.urandom(4).hex()}"

def save_cookies():
    """حفظ الكوكيز في ملف"""
    try:
        with open('cookies.json', 'w') as f:
            json.dump(cookies_storage, f, indent=4)
        return True
    except:
        return False

def get_server_url():
    """الحصول على رابط السيرفر"""
    return os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:5000")

# ==================== Routes Flask ====================

@app_flask.route('/')
def home():
    return """
    <h1>✅ Netflix Bot Proxy يعمل</h1>
    <p>البوت يعمل بنجاح على Render!</p>
    <p>📊 عدد الجلسات النشطة: {}</p>
    <p>📦 عدد الخدمات المخزنة: {}</p>
    """.format(len(sessions), len(cookies_storage))

@app_flask.route('/health')
def health():
    return "OK", 200

@app_flask.route('/generate', methods=['POST'])
def generate_link():
    """استقبال الكوكيز وتوليد رابط"""
    data = request.get_json()
    if not data or 'cookies' not in data:
        return jsonify({"error": "لم يتم إرسال الكوكيز"}), 400
    
    cookies_text = data['cookies']
    cookie_dict = parse_cookies(cookies_text)
    
    if not cookie_dict:
        return jsonify({"error": "كوكيز غير صالحة"}), 400
    
    # توليد رابط
    token = generate_token()
    sessions[token] = {
        'cookies': cookie_dict,
        'expires': time.time() + 3600  # ساعة واحدة
    }
    
    server_url = get_server_url()
    link = f"{server_url}/redirect?token={token}"
    
    return jsonify({
        "link": link,
        "expires_in": "3600 ثانية (ساعة واحدة)"
    })

@app_flask.route('/redirect')
def redirect_to_netflix():
    """إعادة التوجيه إلى Netflix مع الكوكيز"""
    token = request.args.get('token')
    if not token or token not in sessions:
        return "❌ الرابط غير صالح أو منتهي الصلاحية", 404
    
    session = sessions[token]
    if session['expires'] < time.time():
        del sessions[token]
        return "❌ انتهت صلاحية الرابط", 410
    
    # إنشاء رد مع الكوكيز
    resp = make_response(redirect('https://www.netflix.com'))
    for key, value in session['cookies'].items():
        resp.set_cookie(
            key=key,
            value=value,
            domain='.netflix.com',
            path='/',
            secure=True,
            httponly=True,
            max_age=3600
        )
    
    return resp

@app_flask.route('/stats')
def stats():
    """إحصائيات السيرفر"""
    active_sessions = sum(1 for s in sessions.values() if s['expires'] > time.time())
    return jsonify({
        "active_sessions": active_sessions,
        "total_sessions": len(sessions),
        "services": list(cookies_storage.keys()),
        "uptime": time.time()
    })

# ====================================================================
#                          بوت تيليجرام
# ====================================================================

telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ==================== أوامر البوت ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض أزرار الاختيار"""
    user = update.effective_user
    first_name = user.first_name if user.first_name else "صديق"
    
    keyboard = [
        [InlineKeyboardButton("🍿 Netflix", callback_data='netflix')],
        [InlineKeyboardButton("📺 Disney+", callback_data='disney')],
        [InlineKeyboardButton("🎬 Amazon Prime", callback_data='prime')],
        [InlineKeyboardButton("📱 ChatGPT", callback_data='chatgpt')],
        [InlineKeyboardButton("❓ مساعدة", callback_data='help')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 أهلاً بك {first_name}!\n\n"
        "اختر الخدمة التي تريد الحصول على كوكيزها:",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار المستخدم"""
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    user_id = query.from_user.id
    user_name = query.from_user.first_name or "مستخدم"
    
    if choice == 'help':
        await query.edit_message_text(
            "📖 **المساعدة:**\n\n"
            "1. اختر الخدمة التي تريد (مثل Netflix)\n"
            "2. ستحصل على رابط مؤقت صالح لمدة ساعة\n"
            "3. افتح الرابط في المتصفح للدخول إلى حسابك\n\n"
            "⚠️ الروابط تنتهي بعد ساعة واحدة.\n"
            "🔐 لا تشارك الكوكيز مع أي شخص."
        )
        return
    
    if choice not in cookies_storage:
        await query.edit_message_text(
            f"❌ لا توجد كوكيز لـ **{choice}** متاحة حالياً.\n"
            "الرجاء المحاولة لاحقاً."
        )
        return
    
    # توليد رابط مؤقت
    cookies_text = cookies_storage[choice]
    cookie_dict = parse_cookies(cookies_text)
    
    if not cookie_dict:
        await query.edit_message_text(f"❌ كوكيز {choice} غير صالحة.")
        return
    
    # توليد رابط
    token = generate_token()
    sessions[token] = {
        'cookies': cookie_dict,
        'expires': time.time() + 3600,
        'user_id': user_id,
        'service': choice
    }
    
    server_url = get_server_url()
    link = f"{server_url}/redirect?token={token}"
    
    # اختصار الكوكيز للعرض
    cookies_short = cookies_text[:300] + "..." if len(cookies_text) > 300 else cookies_text
    
    # إرسال الكوكيز والرابط للمستخدم
    await query.edit_message_text(
        f"✅ **تم اختيار {choice}!**\n\n"
        f"🔗 **رابط الدخول المؤقت (صالح لمدة ساعة):**\n"
        f"`{link}`\n\n"
        f"📦 **الكوكيز:**\n"
        f"```\n{cookies_short}\n```\n\n"
        f"⚠️ استخدم الرابط خلال ساعة واحدة فقط.\n"
        f"🔐 الكوكيز خاصة بك، لا تشاركها مع أحد.",
        parse_mode="Markdown"
    )
    
    # تسجيل الطلب
    if 'history' not in context.bot_data:
        context.bot_data['history'] = []
    context.bot_data['history'].append({
        'user_id': user_id,
        'user_name': user_name,
        'service': choice,
        'time': datetime.now().isoformat(),
        'token': token
    })

# ==================== أوامر المشرف ====================

async def add_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة كوكيز جديدة (للمشرف فقط)"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ هذا الأمر للمشرفين فقط.")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ **الاستخدام:**\n"
            "/add_cookie [الخدمة] [الكوكيز]\n\n"
            "📌 **مثال:**\n"
            "/add_cookie netflix .netflix.com TRUE / FALSE ...\n\n"
            "📌 **الخدمات المدعومة:**\n"
            "netflix, disney, prime, chatgpt",
            parse_mode="Markdown"
        )
        return
    
    service = args[0].lower()
    cookie_text = " ".join(args[1:])
    
    if len(cookie_text) < 50:
        await update.message.reply_text("⚠️ الكوكيز التي أدخلتها قصيرة جداً. تأكد من الصقها كاملة.")
        return
    
    # حفظ الكوكيز
    cookies_storage[service] = cookie_text
    save_cookies()
    
    await update.message.reply_text(
        f"✅ تم حفظ كوكيز **{service}** بنجاح!\n"
        f"📦 عدد الأحرف: {len(cookie_text)}\n"
        f"🗂️ الخدمات المتاحة الآن: {', '.join(cookies_storage.keys())}"
    )

async def list_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الخدمات المتاحة"""
    if not cookies_storage:
        await update.message.reply_text("❌ لا توجد خدمات متاحة حالياً.")
        return
    
    services_list = "\n".join([f"• {service}" for service in cookies_storage.keys()])
    await update.message.reply_text(
        f"📦 **الخدمات المتاحة:**\n\n{services_list}\n\n"
        f"📊 عدد الخدمات: {len(cookies_storage)}"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حالة البوت"""
    active_links = sum(1 for s in sessions.values() if s['expires'] > time.time())
    total_links = len(sessions)
    services = list(cookies_storage.keys())
    
    history_count = len(context.bot_data.get('history', []))
    
    status_text = f"📊 **حالة البوت:**\n\n"
    status_text += f"✅ البوت يعمل\n"
    status_text += f"🔗 روابط نشطة: {active_links}\n"
    status_text += f"📝 روابط مولدة: {total_links}\n"
    status_text += f"📦 خدمات متاحة: {', '.join(services) if services else 'لا شيء'}\n"
    status_text += f"👥 عدد الطلبات: {history_count}\n"
    status_text += f"🕐 الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف خدمة (للمشرف فقط)"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ هذا الأمر للمشرفين فقط.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ الاستخدام: /delete_service [الخدمة]\n"
            "مثال: /delete_service netflix"
        )
        return
    
    service = args[0].lower()
    if service not in cookies_storage:
        await update.message.reply_text(f"❌ الخدمة **{service}** غير موجودة.")
        return
    
    del cookies_storage[service]
    save_cookies()
    
    await update.message.reply_text(
        f"✅ تم حذف خدمة **{service}** بنجاح.\n"
        f"📦 الخدمات المتبقية: {', '.join(cookies_storage.keys()) if cookies_storage else 'لا شيء'}"
    )

# ====================================================================
#                     تشغيل السيرفر والبوت معاً
# ====================================================================

def run_flask():
    """تشغيل Flask في خيط منفصل"""
    port = int(os.environ.get("PORT", 5000))
    app_flask.run(host='0.0.0.0', port=port)

def run_telegram():
    """تشغيل بوت تيليجرام"""
    print("🤖 تشغيل بوت تيليجرام...")
    telegram_app.run_polling()

def setup_telegram():
    """إعداد أوامر البوت"""
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("add_cookie", add_cookie))
    telegram_app.add_handler(CommandHandler("services", list_services))
    telegram_app.add_handler(CommandHandler("status", status_command))
    telegram_app.add_handler(CommandHandler("delete_service", delete_service))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))

# ====================================================================
#                             MAIN
# ====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 تشغيل Netflix Bot Proxy")
    print("=" * 60)
    
    # إعداد البوت
    setup_telegram()
    
    # تشغيل Flask في خيط منفصل
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("🌐 سيرفر Flask يعمل...")
    
    # تشغيل البوت في الخيط الرئيسي
    run_telegram()
