# bot.py
import logging, sqlite3, asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)

logging.basicConfig(level=logging.INFO)

# ── Sozlamalar ────────────────────────────────────────────────────────────────
TG_TOKEN    = "8189164536:AAExAqjk2LC-TxSqM3bsmwzRDTD4WTEB47Q"
TG_ADMIN    = 7721593413
CARD_NUMBER = "9860 0999 3876 5637 89"
DB_PATH     = "/Users/aziz/PycharmProjects/smm_paenl/smm_panel.db"
MIN_DEPOSIT = 5000
QQS_RATE    = 0.015   # 1.5% QQS
TIMER_SEC   = 7 * 60  # 7 daqiqa

bot = Bot(token=TG_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# Aktiv timerlarni saqlash: {tg_user_id: asyncio.Task}
active_timers: dict[int, asyncio.Task] = {}


# ── Holatlar ──────────────────────────────────────────────────────────────────
class TolovState(StatesGroup):
    username = State()
    summa    = State()
    chek     = State()

class AdminState(StatesGroup):
    balance_username = State()
    balance_amount   = State()
    balance_action   = State()
    xabar_matn       = State()
    user_search      = State()


# ── DB yordamchilar ───────────────────────────────────────────────────────────
def db_conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def get_user_by_username(username: str):
    with db_conn() as db:
        return db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

def confirm_deposit(user_id: int, amount: float, tx_ref: str):
    """amount — asosiy summa (QQS siz). QQS ajratiladi, foydalanuvchi asosiy summani oladi."""
    with db_conn() as db:
        db.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, user_id))
        db.execute(
            "INSERT INTO deposits (user_id, amount, method, status, external_id, confirmed_at) "
            "VALUES (?, ?, 'Karta', 'completed', ?, datetime('now'))",
            (user_id, amount, tx_ref)
        )
        db.execute(
            "INSERT INTO transactions (user_id, type, amount, description, ref_id) "
            "VALUES (?, 'credit', ?, 'Karta orqali to''lov tasdiqlandi', ?)",
            (user_id, amount, tx_ref)
        )
        # Referal 1% bonus
        user = db.execute("SELECT referred_by FROM users WHERE id=?", (user_id,)).fetchone()
        if user and user["referred_by"]:
            bonus = round(amount * 0.01, 2)
            db.execute(
                "UPDATE users SET balance=balance+?, ref_earnings=ref_earnings+? WHERE id=?",
                (bonus, bonus, user["referred_by"])
            )
            db.execute(
                "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, 'credit', ?, ?)",
                (user["referred_by"], bonus, "Referal bonus 1%")
            )
        db.commit()

def is_maintenance():
    with db_conn() as db:
        row = db.execute("SELECT value FROM settings WHERE key='maintenance'").fetchone()
        return row and str(row["value"]) == "1"

def set_maintenance(val: bool):
    with db_conn() as db:
        db.execute("UPDATE settings SET value=? WHERE key='maintenance'", ("1" if val else "0",))
        db.commit()

def get_stats():
    with db_conn() as db:
        users     = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        orders    = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        completed = db.execute("SELECT COUNT(*) FROM orders WHERE status='Completed'").fetchone()[0]
        pending   = db.execute("SELECT COUNT(*) FROM orders WHERE status IN ('Pending','Processing')").fetchone()[0]
        daromad   = db.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status='completed'").fetchone()[0]
        bugun     = db.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status='completed' AND date(confirmed_at)=date('now')").fetchone()[0]
        return {"users": users, "orders": orders, "completed": completed,
                "pending": pending, "daromad": daromad, "bugun": bugun}

def get_all_users(page=0, limit=10):
    with db_conn() as db:
        rows  = db.execute(
            "SELECT id, username, balance, total_orders, is_active FROM users "
            "ORDER BY id DESC LIMIT ? OFFSET ?", (limit, page * limit)
        ).fetchall()
        total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return rows, total

def get_user_orders(username: str, limit=5):
    with db_conn() as db:
        u = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not u: return []
        return db.execute(
            "SELECT o.id, s.name, o.quantity, o.price, o.status "
            "FROM orders o JOIN services s ON o.service_id=s.id "
            "WHERE o.user_id=? ORDER BY o.created_at DESC LIMIT ?",
            (u["id"], limit)
        ).fetchall()


# ── QQS hisoblash ─────────────────────────────────────────────────────────────
def hisobla(asosiy: int) -> tuple[int, int, int]:
    """
    Qaytaradi: (asosiy, qqs, jami)
    Foydalanuvchi jami ni to'laydi.
    """
    qqs  = round(asosiy * QQS_RATE)
    jami = asosiy + qqs
    return asosiy, qqs, jami


# ── Timer: 7 daqiqa ichida to'lov bo'lmasa bekor ─────────────────────────────
async def start_payment_timer(tg_user_id: int, admin_msg_id: int, state: FSMContext):
    """7 daqiqa kutadi, so'ng to'lovni bekor qiladi."""
    try:
        await asyncio.sleep(TIMER_SEC)
        # Agar hali chek kutilayotgan holatda bo'lsa
        current_state = await state.get_state()
        if current_state == TolovState.chek.state:
            await state.clear()
            # Foydalanuvchiga xabar
            try:
                await bot.send_message(
                    tg_user_id,
                    "⏰ <b>Vaqt tugadi!</b>\n\n"
                    "7 daqiqa ichida chek yuborilmadi.\n"
                    "To'lov <b>avtomatik bekor qilindi</b>.\n\n"
                    "Qaytadan urinish uchun /start ni bosing.",
                    parse_mode="HTML",
                    reply_markup=main_menu()
                )
            except Exception:
                pass
            # Adminga ham xabar
            try:
                await bot.send_message(
                    TG_ADMIN,
                    f"⏰ To'lov vaqti tugadi — foydalanuvchi ID: <code>{tg_user_id}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    except asyncio.CancelledError:
        pass  # To'lov tasdiqlandi — timer bekor qilindi
    finally:
        active_timers.pop(tg_user_id, None)


def cancel_timer(tg_user_id: int):
    task = active_timers.pop(tg_user_id, None)
    if task and not task.done():
        task.cancel()


# ── Klaviaturalar ─────────────────────────────────────────────────────────────
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 Balans to'ldirish")],
            [KeyboardButton(text="📊 Mening hisobim")],
            [KeyboardButton(text="ℹ️ Yordam")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"),        KeyboardButton(text="👥 Foydalanuvchilar")],
            [KeyboardButton(text="💰 Balans boshqaruv"),  KeyboardButton(text="📦 Buyurtmalar")],
            [KeyboardButton(text="📢 Xabar yuborish"),    KeyboardButton(text="🔧 Texnik ish")],
            [KeyboardButton(text="💳 Balans to'ldirish")]
        ],
        resize_keyboard=True
    )

def back_btn():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Orqaga")]],
        resize_keyboard=True
    )


# ════════════════════════════════════════════════════════════
#  UMUMIY
# ════════════════════════════════════════════════════════════

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    cancel_timer(message.from_user.id)
    if message.from_user.id == TG_ADMIN:
        await message.answer(
            "👋 <b>Admin paneliga xush kelibsiz!</b>\n\nQuyidagi menyudan tanlang:",
            reply_markup=admin_menu(), parse_mode="HTML"
        )
    else:
        if is_maintenance():
            await message.answer(
                "🔧 <b>Texnik ish olib borilmoqda</b>\n\n"
                "Saytimiz vaqtincha texnik xizmat ko'rsatish uchun to'xtatildi.\n"
                "Tez orada qayta ishga tushadi. Sabr qiling! 🙏",
                parse_mode="HTML"
            )
            return
        await message.answer(
            "👋 <b>Assalomu alaykum!</b>\n\n"
            "🌐 <b>SMMPanel.uz</b> — O'zbekistondagi eng arzon SMM panel\n\n"
            "💳 Balans to'ldirish uchun tugmani bosing:",
            reply_markup=main_menu(), parse_mode="HTML"
        )


@dp.message(Command("admin"))
async def admin_command(message: types.Message, state: FSMContext):
    """Faqat admin uchun /admin buyrug'i."""
    if message.from_user.id != TG_ADMIN:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    await state.clear()
    s = get_stats()
    m = "🔴 YOQILGAN" if is_maintenance() else "🟢 O'CHIRILGAN"
    await message.answer(
        f"🛠 <b>Admin Panel</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['users']}</b>\n"
        f"📦 Jami orderlar: <b>{s['orders']}</b>\n"
        f"✅ Bajarilgan: <b>{s['completed']}</b>\n"
        f"⏳ Kutilayotgan: <b>{s['pending']}</b>\n\n"
        f"💰 Jami daromad: <b>{s['daromad']:,.0f} so'm</b>\n"
        f"📅 Bugungi daromad: <b>{s['bugun']:,.0f} so'm</b>\n\n"
        f"🔧 Texnik ish: {m}\n\n"
        f"Quyidagi menyudan tanlang 👇",
        reply_markup=admin_menu(), parse_mode="HTML"
    )


@dp.message(F.text == "🔙 Orqaga")
async def orqaga(message: types.Message, state: FSMContext):
    cancel_timer(message.from_user.id)
    await state.clear()
    if message.from_user.id == TG_ADMIN:
        await message.answer("Admin menyu:", reply_markup=admin_menu())
    else:
        await message.answer("Asosiy menyu:", reply_markup=main_menu())

@dp.message(F.text == "ℹ️ Yordam")
async def yordam(message: types.Message):
    await message.answer(
        "ℹ️ <b>Yordam</b>\n\n"
        "🌐 Sayt: smmpanel.uz\n"
        "💬 Admin bilan bog'laning\n\n"
        "Muammo bo'lsa /start ni bosing.",
        parse_mode="HTML"
    )


# ════════════════════════════════════════════════════════════
#  FOYDALANUVCHI — TO'LOV (QQS + 7 daqiqa timer)
# ════════════════════════════════════════════════════════════

@dp.message(F.text == "💳 Balans to'ldirish")
async def balans_toldirish(message: types.Message, state: FSMContext):
    if is_maintenance() and message.from_user.id != TG_ADMIN:
        await message.answer("🔧 Texnik ish olib borilmoqda. Keyinroq urinib ko'ring.")
        return
    cancel_timer(message.from_user.id)
    await state.clear()
    await message.answer("👤 Saytdagi <b>username</b> ingizni yuboring:", reply_markup=back_btn(), parse_mode="HTML")
    await state.set_state(TolovState.username)

@dp.message(TolovState.username)
async def tolov_username(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        kb = admin_menu() if message.from_user.id == TG_ADMIN else main_menu()
        await message.answer("Menyu:", reply_markup=kb)
        return
    user = get_user_by_username(message.text.strip())
    if not user:
        await message.answer("❌ Bunday username topilmadi! Qaytadan kiriting:")
        return
    await state.update_data(username=message.text.strip(), user_id=user["id"])
    await message.answer(
        f"✅ Topildi: <b>{user['username']}</b>\n"
        f"💰 Joriy balans: <b>{user['balance']:,.0f} so'm</b>\n\n"
        f"Qancha to'ldirmoqchisiz? (minimal {MIN_DEPOSIT:,} so'm)\n\n"
        f"ℹ️ <i>Har bir to'lovga 1.5% QQS qo'shiladi.</i>",
        parse_mode="HTML"
    )
    await state.set_state(TolovState.summa)

@dp.message(TolovState.summa)
async def tolov_summa(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        kb = admin_menu() if message.from_user.id == TG_ADMIN else main_menu()
        await message.answer("Menyu:", reply_markup=kb)
        return
    try:
        asosiy = int(message.text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting! Masalan: 50000")
        return
    if asosiy < MIN_DEPOSIT:
        await message.answer(f"❌ Minimal summa: {MIN_DEPOSIT:,} so'm")
        return

    asosiy, qqs, jami = hisobla(asosiy)
    await state.update_data(summa=asosiy, qqs=qqs, jami=jami)

    sent = await message.answer(
        f"💳 <b>To'lov ma'lumotlari:</b>\n\n"
        f"🏦 Karta: <code>{CARD_NUMBER}</code>\n\n"
        f"┌ Asosiy summa: <b>{asosiy:,} so'm</b>\n"
        f"├ QQS (1.5%):   <b>{qqs:,} so'm</b>\n"
        f"└ <b>Jami to'lash: {jami:,} so'm</b>\n\n"
        f"⏰ <b>7 daqiqa</b> ichida chek rasmini yuboring!\n"
        f"Vaqt tugasa to'lov avtomatik bekor qilinadi.",
        parse_mode="HTML"
    )

    # 7 daqiqa timerini ishga tushirish
    cancel_timer(message.from_user.id)
    task = asyncio.create_task(
        start_payment_timer(message.from_user.id, sent.message_id, state)
    )
    active_timers[message.from_user.id] = task

    await state.set_state(TolovState.chek)

@dp.message(TolovState.chek, F.photo)
async def tolov_chek(message: types.Message, state: FSMContext):
    # Chek keldi — timerni to'xtatamiz
    cancel_timer(message.from_user.id)

    data = await state.get_data()
    asosiy = data['summa']
    qqs    = data['qqs']
    jami   = data['jami']

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Tasdiqlash",
            callback_data=f"confirm_{data['user_id']}_{asosiy}_{message.from_user.id}"
        ),
        InlineKeyboardButton(
            text="❌ Rad etish",
            callback_data=f"reject_{message.from_user.id}"
        )
    ]])
    await bot.send_photo(
        TG_ADMIN,
        photo=message.photo[-1].file_id,
        caption=(
            f"💰 <b>Yangi to'lov so'rovi</b>\n\n"
            f"👤 Username: <b>{data['username']}</b>\n"
            f"📱 Telegram: {message.from_user.mention_html()}\n\n"
            f"┌ Asosiy summa: <b>{asosiy:,} so'm</b>\n"
            f"├ QQS (1.5%):   <b>{qqs:,} so'm</b>\n"
            f"└ Jami to'langan: <b>{jami:,} so'm</b>"
        ),
        reply_markup=kb, parse_mode="HTML"
    )
    await message.answer(
        "✅ Chekingiz adminga yuborildi!\n⏳ Tez orada tasdiqlanadi...",
        reply_markup=main_menu()
    )
    await state.clear()

@dp.message(TolovState.chek)
async def chek_not_photo(message: types.Message):
    await message.answer("❌ Iltimos, <b>chek rasmini</b> yuboring!", parse_mode="HTML")


@dp.callback_query(F.data.startswith("confirm_"))
async def admin_confirm(callback: types.CallbackQuery):
    if callback.from_user.id != TG_ADMIN:
        await callback.answer("❌ Siz admin emassiz!")
        return
    parts   = callback.data.split("_")
    user_id = int(parts[1])
    # asosiy summa tasdiqlanganda balansgа qo'shiladi (QQS davlatga)
    asosiy  = float(parts[2])
    tg_id   = int(parts[3])

    _, qqs, jami = hisobla(int(asosiy))
    confirm_deposit(user_id, asosiy, f"tg_{tg_id}_{asosiy}")

    await callback.message.edit_caption(
        callback.message.caption + "\n\n✅ <b>TASDIQLANDI</b>",
        parse_mode="HTML"
    )
    try:
        await bot.send_message(
            tg_id,
            f"✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
            f"💰 Balansingizga <b>{asosiy:,.0f} so'm</b> qo'shildi!\n"
            f"🧾 QQS ({qqs:,} so'm) davlat xazinasiga o'tkazildi.\n\n"
            f"🌐 Saytga kiring: smmpanel.uz",
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer("✅ Tasdiqlandi!")


@dp.callback_query(F.data.startswith("reject_"))
async def admin_reject(callback: types.CallbackQuery):
    if callback.from_user.id != TG_ADMIN:
        await callback.answer("❌ Siz admin emassiz!")
        return
    tg_id = int(callback.data.split("_")[1])
    await callback.message.edit_caption(
        callback.message.caption + "\n\n❌ <b>RAD ETILDI</b>",
        parse_mode="HTML"
    )
    try:
        await bot.send_message(
            tg_id,
            "❌ <b>To'lovingiz rad etildi.</b>\n\n"
            "Muammo bo'lsa admin bilan bog'laning.\n"
            "Qayta urinish uchun /start ni bosing.",
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer("❌ Rad etildi!")


# ════════════════════════════════════════════════════════════
#  FOYDALANUVCHI — HISOBIM
# ════════════════════════════════════════════════════════════

@dp.message(F.text == "📊 Mening hisobim")
async def mening_hisobim(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👤 Saytdagi <b>username</b> ingizni yuboring:", reply_markup=back_btn(), parse_mode="HTML")
    await state.set_state(AdminState.user_search)

@dp.message(AdminState.user_search)
async def user_search(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        kb = admin_menu() if message.from_user.id == TG_ADMIN else main_menu()
        await message.answer("Menyu:", reply_markup=kb)
        return
    user = get_user_by_username(message.text.strip())
    if not user:
        await message.answer("❌ Foydalanuvchi topilmadi!")
        await state.clear()
        return
    orders = get_user_orders(message.text.strip())
    orders_text = ""
    for o in orders:
        emoji = {"Completed": "✅", "Pending": "⏳", "Processing": "🔄",
                 "Partial": "⚠️", "Cancelled": "❌"}.get(o["status"], "❓")
        orders_text += f"\n  {emoji} #{o['id']} | {o['name'][:20]} | {o['quantity']} | {o['price']:,.0f} so'm"
    status = "✅ Aktiv" if user["is_active"] else "🚫 Bloklangan"
    await message.answer(
        f"👤 <b>{user['username']}</b>\n\n"
        f"💰 Balans: <b>{user['balance']:,.0f} so'm</b>\n"
        f"📦 Jami orderlar: {user['total_orders']}\n"
        f"💸 Jami sarflagan: {user['total_spent']:,.0f} so'm\n"
        f"👥 Referal daromad: {user['ref_earnings']:,.0f} so'm\n"
        f"🔘 Holat: {status}\n\n"
        f"📋 <b>So'nggi orderlar:</b>{orders_text if orders_text else ' Yo''q'}",
        parse_mode="HTML"
    )
    await state.clear()
    kb = admin_menu() if message.from_user.id == TG_ADMIN else main_menu()
    await message.answer("Menyu:", reply_markup=kb)


# ════════════════════════════════════════════════════════════
#  ADMIN
# ════════════════════════════════════════════════════════════

@dp.message(F.text == "📊 Statistika")
async def statistika(message: types.Message):
    if message.from_user.id != TG_ADMIN: return
    s = get_stats()
    m = "🔴 YOQILGAN" if is_maintenance() else "🟢 O'CHIRILGAN"
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['users']}</b>\n"
        f"📦 Jami orderlar: <b>{s['orders']}</b>\n"
        f"✅ Bajarilgan: <b>{s['completed']}</b>\n"
        f"⏳ Kutilayotgan: <b>{s['pending']}</b>\n\n"
        f"💰 Jami daromad: <b>{s['daromad']:,.0f} so'm</b>\n"
        f"📅 Bugungi daromad: <b>{s['bugun']:,.0f} so'm</b>\n\n"
        f"🔧 Texnik ish: {m}",
        parse_mode="HTML"
    )

@dp.message(F.text == "👥 Foydalanuvchilar")
async def foydalanuvchilar(message: types.Message):
    if message.from_user.id != TG_ADMIN: return
    users, total = get_all_users(page=0)
    text = f"👥 <b>Foydalanuvchilar</b> (jami: {total})\n\n"
    for u in users:
        s = "✅" if u["is_active"] else "🚫"
        text += f"{s} <b>{u['username']}</b> — {u['balance']:,.0f} so'm | {u['total_orders']} order\n"
    btns = []
    if total > 10:
        btns.append([InlineKeyboardButton(text="➡️ Keyingi", callback_data="users_page_1")])
    kb = InlineKeyboardMarkup(inline_keyboard=btns) if btns else None
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("users_page_"))
async def users_page(callback: types.CallbackQuery):
    if callback.from_user.id != TG_ADMIN: return
    page = int(callback.data.split("_")[2])
    users, total = get_all_users(page=page)
    if not users:
        await callback.answer("Bu yerda hech kim yo'q!")
        return
    text = f"👥 <b>Foydalanuvchilar</b> (jami: {total}) — {page+1}-sahifa\n\n"
    for u in users:
        s = "✅" if u["is_active"] else "🚫"
        text += f"{s} <b>{u['username']}</b> — {u['balance']:,.0f} so'm | {u['total_orders']} order\n"
    btns = []
    if page > 0:
        btns.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"users_page_{page-1}"))
    if (page + 1) * 10 < total:
        btns.append(InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"users_page_{page+1}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[btns]) if btns else None
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@dp.message(F.text == "💰 Balans boshqaruv")
async def balans_boshqaruv(message: types.Message, state: FSMContext):
    if message.from_user.id != TG_ADMIN: return
    await message.answer("👤 Foydalanuvchi username ini kiriting:", reply_markup=back_btn())
    await state.set_state(AdminState.balance_username)

@dp.message(AdminState.balance_username)
async def admin_bal_username(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        await message.answer("Admin menyu:", reply_markup=admin_menu())
        return
    user = get_user_by_username(message.text.strip())
    if not user:
        await message.answer("❌ Foydalanuvchi topilmadi!")
        return
    await state.update_data(username=user["username"], user_id=user["id"], current_balance=user["balance"])
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Qo'shish", callback_data="bal_add"),
        InlineKeyboardButton(text="➖ Ayirish",  callback_data="bal_sub"),
        InlineKeyboardButton(text="🔄 Nolga",    callback_data="bal_zero"),
    ]])
    await message.answer(
        f"👤 <b>{user['username']}</b>\n"
        f"💰 Joriy balans: <b>{user['balance']:,.0f} so'm</b>\n\n"
        f"Qanday amal bajarmoqchisiz?",
        reply_markup=kb, parse_mode="HTML"
    )
    await state.set_state(AdminState.balance_action)

@dp.callback_query(F.data.startswith("bal_"))
async def balance_action_cb(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != TG_ADMIN: return
    action = callback.data
    await state.update_data(bal_action=action)
    if action == "bal_zero":
        data = await state.get_data()
        with db_conn() as db:
            db.execute("UPDATE users SET balance=0 WHERE id=?", (data["user_id"],))
            db.execute(
                "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, 'debit', ?, ?)",
                (data["user_id"], data["current_balance"], "Admin tomonidan nolga tushirildi")
            )
            db.commit()
        await callback.message.edit_text(
            f"✅ <b>{data['username']}</b> balansi nolga tushirildi!", parse_mode="HTML"
        )
        await state.clear()
        await bot.send_message(TG_ADMIN, "Admin menyu:", reply_markup=admin_menu())
    else:
        t = "qo'shmoqchi" if action == "bal_add" else "ayirmoqchi"
        await callback.message.edit_text(f"💰 Qancha so'm {t}siz? (raqam kiriting)")
        await state.set_state(AdminState.balance_amount)
    await callback.answer()

@dp.message(AdminState.balance_amount)
async def admin_bal_amount(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        await message.answer("Admin menyu:", reply_markup=admin_menu())
        return
    try:
        amount = float(message.text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")
        return
    data   = await state.get_data()
    action = data["bal_action"]
    with db_conn() as db:
        if action == "bal_add":
            db.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, data["user_id"]))
            db.execute(
                "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, 'credit', ?, ?)",
                (data["user_id"], amount, "Admin tomonidan qo'shildi")
            )
            text = f"✅ <b>{data['username']}</b> ga <b>{amount:,.0f} so'm</b> qo'shildi!"
        else:
            db.execute("UPDATE users SET balance=balance-? WHERE id=?", (amount, data["user_id"]))
            db.execute(
                "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, 'debit', ?, ?)",
                (data["user_id"], amount, "Admin tomonidan ayirildi")
            )
            text = f"✅ <b>{data['username']}</b> dan <b>{amount:,.0f} so'm</b> ayirildi!"
        db.commit()
    await message.answer(text, parse_mode="HTML", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "📦 Buyurtmalar")
async def buyurtmalar(message: types.Message):
    if message.from_user.id != TG_ADMIN: return
    with db_conn() as db:
        orders = db.execute(
            "SELECT o.id, u.username, s.name, o.quantity, o.price, o.status "
            "FROM orders o JOIN users u ON o.user_id=u.id "
            "JOIN services s ON o.service_id=s.id "
            "ORDER BY o.created_at DESC LIMIT 10"
        ).fetchall()
    if not orders:
        await message.answer("📦 Hech qanday buyurtma yo'q!")
        return
    text = "📦 <b>So'nggi 10 ta buyurtma:</b>\n\n"
    for o in orders:
        e = {"Completed": "✅", "Pending": "⏳", "Processing": "🔄",
             "Partial": "⚠️", "Cancelled": "❌"}.get(o["status"], "❓")
        text += (
            f"{e} #{o['id']} | <b>{o['username']}</b> | {o['name'][:20]}\n"
            f"   {o['quantity']} ta | {o['price']:,.0f} so'm\n\n"
        )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📢 Xabar yuborish")
async def xabar_yuborish(message: types.Message, state: FSMContext):
    if message.from_user.id != TG_ADMIN: return
    await message.answer("📢 Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:", reply_markup=back_btn())
    await state.set_state(AdminState.xabar_matn)

@dp.message(AdminState.xabar_matn)
async def xabar_matn(message: types.Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        await message.answer("Admin menyu:", reply_markup=admin_menu())
        return
    await state.update_data(broadcast_text=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yuborish", callback_data="send_broadcast"),
        InlineKeyboardButton(text="❌ Bekor",    callback_data="cancel_broadcast")
    ]])
    await message.answer(
        f"📢 <b>Xabar ko'rinishi:</b>\n\n{message.text}\n\nTasdiqlaysizmi?",
        reply_markup=kb, parse_mode="HTML"
    )

@dp.callback_query(F.data == "send_broadcast")
async def send_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != TG_ADMIN: return
    data = await state.get_data()
    matn = data.get("broadcast_text", "")
    await callback.message.edit_text("⏳ Yuborilmoqda...")
    with db_conn() as db:
        total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    await bot.send_message(
        TG_ADMIN,
        f"✅ Xabar yuborildi!\n👥 Jami foydalanuvchilar: {total}\n\n<b>Xabar:</b>\n{matn}",
        parse_mode="HTML", reply_markup=admin_menu()
    )
    await state.clear()
    await callback.answer("✅ Yuborildi!")

@dp.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.answer()
    await bot.send_message(TG_ADMIN, "Admin menyu:", reply_markup=admin_menu())

@dp.message(F.text == "🔧 Texnik ish")
async def texnik_ish(message: types.Message):
    if message.from_user.id != TG_ADMIN: return
    maintenance = is_maintenance()
    status_text = "🔴 YOQILGAN" if maintenance else "🟢 O'CHIRILGAN"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🟢 O'chirish" if maintenance else "🔴 Yoqish",
            callback_data="toggle_maintenance"
        )
    ]])
    await message.answer(
        f"🔧 <b>Texnik ish rejimi</b>\n\nHolat: {status_text}\n\n"
        f"Yoqilganda foydalanuvchilar botdan foydalana olmaydi.",
        reply_markup=kb, parse_mode="HTML"
    )

@dp.callback_query(F.data == "toggle_maintenance")
async def toggle_maintenance(callback: types.CallbackQuery):
    if callback.from_user.id != TG_ADMIN: return
    current = is_maintenance()
    set_maintenance(not current)
    new_status = "🔴 YOQILDI" if not current else "🟢 O'CHIRILDI"
    await callback.message.edit_text(
        f"🔧 Texnik ish rejimi: <b>{new_status}</b>", parse_mode="HTML"
    )
    await callback.answer(f"Texnik ish {new_status}")


# ── Ishga tushirish ───────────────────────────────────────────────────────────
async def main():
    print("🤖 Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())