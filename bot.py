
import os
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

bot = Bot(token=TOKEN)
dp = Dispatcher()

db = sqlite3.connect("funvisuals.db")
db.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    joined_at TEXT
)
""")
db.execute("""
CREATE TABLE IF NOT EXISTS licenses (
    license_key TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    days INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
)
""")
db.commit()

PLANS = {
    "30": (30, "$1.50"),
    "90": (90, "$3.50"),
    "365": (365, "$12.00"),
}


def now():
    return datetime.now(timezone.utc)


def is_admin(user_id):
    return user_id in ADMIN_IDS


def main_menu(user_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Магазин", callback_data="shop")
    kb.button(text="👤 Мой профиль", callback_data="profile")
    kb.button(text="🔑 Мои лицензии", callback_data="licenses")
    kb.button(text="💬 Поддержка", callback_data="support")
    if is_admin(user_id):
        kb.button(text="⚙️ Админ-панель", callback_data="admin")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def shop_menu():
    kb = InlineKeyboardBuilder()
    for code, (days, price) in PLANS.items():
        kb.button(
            text=f"{days} дней — {price}",
            callback_data=f"buy:{code}"
        )
    kb.button(text="⬅️ Назад", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()


def create_license(user_id, days):
    key = "FV-" + secrets.token_hex(4).upper()
    created = now()
    expires = created + timedelta(days=days)

    db.execute(
        "INSERT INTO licenses VALUES (?, ?, ?, ?, ?)",
        (
            key,
            user_id,
            days,
            expires.isoformat(),
            created.isoformat()
        )
    )
    db.commit()
    return key, expires


@dp.message(CommandStart())
async def start(message: Message):
    user = message.from_user
    db.execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
        (user.id, user.username or "", now().isoformat())
    )
    db.execute(
        "UPDATE users SET username = ? WHERE user_id = ?",
        (user.username or "", user.id)
    )
    db.commit()

    await message.answer(
        "⚡ <b>FUN VISUALS</b>\n"
        "Premium Minecraft Client\n\n"
        "Добро пожаловать в официальный магазин!\n"
        "Выбери нужный раздел:",
        reply_markup=main_menu(user.id),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.message.edit_text(
        "⚡ <b>FUN VISUALS</b>\n\nВыбери нужный раздел:",
        reply_markup=main_menu(call.from_user.id),
        parse_mode="HTML"
    )
    await call.answer()


@dp.callback_query(F.data == "shop")
async def shop(call: CallbackQuery):
    await call.message.edit_text(
        "🛒 <b>Магазин FUN VISUALS</b>\n\n"
        "Выбери срок подписки:\n"
        "Оплата пока работает в тестовом режиме.",
        reply_markup=shop_menu(),
        parse_mode="HTML"
    )
    await call.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery):
    code = call.data.split(":")[1]
    if code not in PLANS:
        await call.answer("Неизвестный тариф", show_alert=True)
        return

    days, price = PLANS[code]
    key, expires = create_license(call.from_user.id, days)

    await call.message.edit_text(
        "🧪 <b>Тестовая покупка успешна!</b>\n\n"
        f"Тариф: {days} дней\n"
        f"Цена в магазине: {price}\n"
        f"Лицензионный ключ:\n<code>{key}</code>\n\n"
        f"Действует до: {expires.strftime('%d.%m.%Y %H:%M UTC')}\n\n"
        "Это тестовая лицензия. Деньги не списывались.",
        reply_markup=main_menu(call.from_user.id),
        parse_mode="HTML"
    )
    await call.answer("Тестовая лицензия создана!")


@dp.callback_query(F.data == "profile")
async def profile(call: CallbackQuery):
    user = call.from_user
    count = db.execute(
        "SELECT COUNT(*) FROM licenses WHERE user_id = ?",
        (user.id,)
    ).fetchone()[0]

    await call.message.edit_text(
        "👤 <b>Твой профиль</b>\n\n"
        f"Telegram ID: <code>{user.id}</code>\n"
        f"Username: @{user.username or 'не указан'}\n"
        f"Лицензий получено: {count}",
        reply_markup=main_menu(user.id),
        parse_mode="HTML"
    )
    await call.answer()


@dp.callback_query(F.data == "licenses")
async def licenses(call: CallbackQuery):
    rows = db.execute(
        "SELECT license_key, days, expires_at FROM licenses "
        "WHERE user_id = ? ORDER BY created_at DESC",
        (call.from_user.id,)
    ).fetchall()

    if not rows:
        result = "🔑 <b>Мои лицензии</b>\n\nУ тебя пока нет лицензий."
    else:
        result = "🔑 <b>Мои лицензии</b>\n\n"
        for key, days, expires in rows:
            expiry = datetime.fromisoformat(expires)
            status = "Активна" if expiry > now() else "Истекла"
            result += (
                f"Ключ: <code>{key}</code>\n"
                f"Срок: {days} дней\n"
                f"Статус: {status}\n"
                f"До: {expiry.strftime('%d.%m.%Y %H:%M UTC')}\n\n"
            )

    await call.message.edit_text(
        result,
        reply_markup=main_menu(call.from_user.id),
        parse_mode="HTML"
    )
    await call.answer()


@dp.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await call.message.edit_text(
        "💬 <b>Поддержка FUN VISUALS</b>\n\n"
        "По вопросам покупки и лицензий обратись к администратору.",
        reply_markup=main_menu(call.from_user.id),
        parse_mode="HTML"
    )
    await call.answer()


@dp.callback_query(F.data == "admin")
async def admin(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    licenses_count = db.execute(
        "SELECT COUNT(*) FROM licenses"
    ).fetchone()[0]

    await call.message.edit_text(
        "⚙️ <b>Админ-панель FUN VISUALS</b>\n\n"
        f"Пользователей: {users}\n"
        f"Выдано лицензий: {licenses_count}\n\n"
        "Команды:\n"
        "<code>/issue USER_ID DAYS</code> — выдать лицензию\n"
        "<code>/stats</code> — статистика",
        reply_markup=main_menu(call.from_user.id),
        parse_mode="HTML"
    )
    await call.answer()


@dp.message(Command("stats"))
async def stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    licenses_count = db.execute(
        "SELECT COUNT(*) FROM licenses"
    ).fetchone()[0]

    await message.answer(
        f"Пользователей: {users}\nЛицензий: {licenses_count}"
    )


@dp.message(Command("issue"))
async def issue(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Формат: /issue USER_ID DAYS")
        return

    try:
        user_id = int(parts[1])
        days = int(parts[2])
        if days not in (30, 90, 365):
            raise ValueError
    except ValueError:
        await message.answer("Укажи Telegram ID и срок 30, 90 или 365.")
        return

    key, expires = create_license(user_id, days)
    await message.answer(
        f"Лицензия создана:\n<code>{key}</code>\n"
        f"Действует до: {expires.strftime('%d.%m.%Y %H:%M UTC')}",
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            user_id,
            f"🎉 Тебе выдана лицензия FUN VISUALS:\n"
            f"<code>{key}</code>\n"
            f"Срок: {days} дней",
            parse_mode="HTML"
        )
    except Exception:
        pass


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
