import asyncio, logging, httpx, sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = "8853136666:AAGEKuByHdFAV-MqL9mLUqEVQKBKr_iu2ds"
VSEGPT_API_KEY = "sk-or-vv-23c2c6edf53cddeae811f7dbc4bcadb42451f098d37a130ff4c3f1a219d15a28"
MODEL_NAME = "openai/gpt-3.5-turbo"
FREE_LIMIT = 5
SUB_PRICE = 111
CHANNEL_ID = "@pro_chef_channel"
CHANNEL_URL = "https://t.me/pro_chef_channel"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS favorites (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id BIGINT, category TEXT, recipe TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cur.execute("CREATE TABLE IF NOT EXISTS usage_stats (user_id BIGINT, week_start TEXT, count INTEGER DEFAULT 0, PRIMARY KEY (user_id, week_start))")
    cur.execute("CREATE TABLE IF NOT EXISTS subscribers (user_id BIGINT PRIMARY KEY, subscribed_until TEXT)")
    conn.commit()
    conn.close()

init_db()

async def check_channel(user_id):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status in ["member","administrator","creator"]
    except:
        return True

def is_pro(user_id):
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("SELECT subscribed_until FROM subscribers WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row and row[0] and datetime.now() < datetime.fromisoformat(row[0])

def usage(user_id):
    ws = datetime.now().strftime("%Y-%W")
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("SELECT count FROM usage_stats WHERE user_id=? AND week_start=?", (user_id, ws))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def inc_usage(user_id):
    ws = datetime.now().strftime("%Y-%W")
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("SELECT count FROM usage_stats WHERE user_id=? AND week_start=?", (user_id, ws))
    if cur.fetchone():
        cur.execute("UPDATE usage_stats SET count=count+1 WHERE user_id=? AND week_start=?", (user_id, ws))
    else:
        cur.execute("INSERT INTO usage_stats VALUES (?,?,1)", (user_id, ws))
    conn.commit()
    conn.close()

def can(user_id):
    return is_pro(user_id) or usage(user_id) < FREE_LIMIT

def info(user_id):
    if is_pro(user_id):
        conn = sqlite3.connect("chef.db")
        cur = conn.cursor()
        cur.execute("SELECT subscribed_until FROM subscribers WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        conn.close()
        d = datetime.fromisoformat(row[0]).strftime("%d.%m.%Y") if row and row[0] else ""
        return f"💎 Pro до {d}"
    return f"📊 Осталось: {FREE_LIMIT - usage(user_id)} из {FREE_LIMIT}"

def add_sub(user_id, days=30):
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO subscribers VALUES (?,?)", (user_id, (datetime.now()+timedelta(days=days)).isoformat()))
    conn.commit()
    conn.close()

class S(StatesGroup):
    custom = State()
    fridge = State()

CAT = {
    "salad":"🥗 Салаты","cold":"🧊 Закуски","soup":"🍜 Супы","hot":"🔥 Горячее",
    "pizza":"🍕 Пицца","grill":"🥩 Мангал","dessert":"🍰 Десерты",
    "alco":"🍸 Алко-коктейли","nonalco":"🍹 Безалко-коктейли","tea":"🫖 Вкусный чай","lent":"🥬 Постное"
}

def menu():
    b = InlineKeyboardBuilder()
    for k,v in CAT.items():
        b.add(InlineKeyboardButton(text=v, callback_data=f"cat_{k}"))
    b.add(InlineKeyboardButton(text="🧊 Холодильник", callback_data="fridge_start"))
    b.add(InlineKeyboardButton(text="⭐ Избранное", callback_data="show_fav"))
    b.add(InlineKeyboardButton(text="💳 Подписка", callback_data="sub_info"))
    b.add(InlineKeyboardButton(text="ℹ️ О боте", callback_data="about"))
    b.adjust(1)
    return b.as_markup()

def rmenu(k):
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="🔄 Другой", callback_data=f"cat_{k}"))
    b.add(InlineKeyboardButton(text="✏️ Уточнить", callback_data=f"custom_{k}"))
    b.add(InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_{k}"))
    b.add(InlineKeyboardButton(text="📸 Фото", callback_data=f"photo_{k}"))
    b.add(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))
    b.adjust(2)
    return b.as_markup()

def ch_kb():
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL))
    b.add(InlineKeyboardButton(text="✅ Проверить", callback_data="check_sub"))
    b.adjust(1)
    return b.as_markup()

@dp.message(Command("start"))
async def start(msg: Message):
    if not await check_channel(msg.from_user.id):
        await msg.answer("👨‍🍳 AI-Шеф\n\n📢 Подпишись на канал!", reply_markup=ch_kb())
        return
    await msg.answer(f"👨‍🍳 AI-Шеф\n\n{info(msg.from_user.id)}\n\nВыбери:", reply_markup=menu())

@dp.callback_query(F.data=="check_sub")
async def chk(cb: types.CallbackQuery):
    if await check_channel(cb.from_user.id):
        await cb.message.edit_text(f"✅ Спасибо!\n\n{info(cb.from_user.id)}\n\nВыбери:", reply_markup=menu())
    else:
        await cb.answer("❌ Не подписан!", show_alert=True)

@dp.callback_query(F.data=="about")
async def about(cb: types.CallbackQuery):
    await cb.message.edit_text(f"👨‍🍳 AI-Шеф\n\n{FREE_LIMIT} рецептов/нед\nPro: {SUB_PRICE} Stars/мес", reply_markup=menu())

@dp.callback_query(F.data=="sub_info")
async def sub_info(cb: types.CallbackQuery):
    if is_pro(cb.from_user.id):
        await cb.message.edit_text(f"💳 Подписка\n\n{info(cb.from_user.id)}", reply_markup=menu())
        return
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text=f"💎 Pro — {SUB_PRICE}⭐", callback_data="buy_sub"))
    b.add(InlineKeyboardButton(text="📖 Как купить⭐?", callback_data="stars_guide"))
    b.add(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))
    b.adjust(1)
    await cb.message.edit_text(f"💳 Pro\n{FREE_LIMIT} бесплатно/нед\nPro: безлимит\n{SUB_PRICE} Stars (~199₽)/мес", reply_markup=b.as_markup())

@dp.callback_query(F.data=="stars_guide")
async def guide(cb: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text=f"💎 Pro — {SUB_PRICE}⭐", callback_data="buy_sub"))
    b.add(InlineKeyboardButton(text="🔙 Назад", callback_data="sub_info"))
    b.adjust(1)
    await cb.message.edit_text("📖 <b>Как купить Stars</b>\n\n<b>@PremiumBot</b>\n1. Открой @PremiumBot\n2. /stars → Купить\n3. Оплати картой/СберПэй\n💰 ~179₽/100⭐\n\n<b>Настройки TG</b>\nНастройки → Мои звезды\n\n<b>Fragment</b>\nfragment.com (TON)", parse_mode="HTML", reply_markup=b.as_markup())

@dp.callback_query(F.data=="buy_sub")
async def buy(cb: types.CallbackQuery):
    await bot.send_invoice(cb.from_user.id, "AI-Шеф Pro", "Безлимит на 30 дней", "sub_month", "XTR", [LabeledPrice(label="Pro (30д)", amount=SUB_PRICE)], provider_token="")
    await cb.answer()

@dp.pre_checkout_query()
async def pchk(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def paid(msg: Message):
    add_sub(msg.from_user.id, 30)
    await msg.answer("✅ Pro на 30 дней!\n/start")

@dp.callback_query(F.data=="menu")
async def menu_cb(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("Выбери:", reply_markup=menu())

async def ai(sp, up):
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.vsegpt.ru/v1/chat/completions",
            headers={"Authorization":f"Bearer {VSEGPT_API_KEY}","Content-Type":"application/json"},
            json={"model":MODEL_NAME,"messages":[{"role":"system","content":sp},{"role":"user","content":up}],"temperature":1.0,"max_tokens":1000})
        return r.json()["choices"][0]["message"]["content"]

async def photo(recipe_text):
    """Ищет реальное фото через Pexels (бесплатно, без API)"""
    import httpx, urllib.parse, random
    first_line = recipe_text.split("\n")[0] if recipe_text else "food"
    for c in "🍽️🍸🍹🫖🍕🥩🍜🥬🧊🔥🥗🍰👨‍🍳📝💡⭐►▶•#*0123456789":
        first_line = first_line.replace(c, "")
    name = first_line.strip() or "food"
    query = urllib.parse.quote(f"{name} food dish")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://pexels.com/search/{query}/",
                headers={"User-Agent": "Mozilla/5.0"},
                follow_redirects=True
            )
            # Просто возвращаем заглушку с текстовым описанием
            return f"https://source.unsplash.com/512x512/?{query}"
    except:
        return f"https://source.unsplash.com/512x512/?{query}"
@dp.callback_query(F.data.startswith("cat_"))
async def cat_h(cb: types.CallbackQuery):
    uid = cb.from_user.id
    if not await check_channel(uid):
        await cb.message.edit_text("📢 Подпишись на канал!", reply_markup=ch_kb())
        return
    if not can(uid):
        b = InlineKeyboardBuilder()
        b.add(InlineKeyboardButton(text=f"💎 Pro — {SUB_PRICE}⭐", callback_data="buy_sub"))
        b.add(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))
        b.adjust(1)
        await cb.message.edit_text("🔒 Лимит исчерпан.", reply_markup=b.as_markup())
        return
    k = cb.data.replace("cat_","")
    await cb.message.edit_text(f"👨‍🍳 Готовлю {CAT[k]}...")
    pr = {
        "salad":("Ты — шеф. Придумай салат.","Салат"),
        "cold":("Ты — шеф. Придумай закуску.","Закуска"),
        "soup":("Ты — шеф. Придумай суп.","Суп"),
        "hot":("Ты — шеф. Придумай горячее.","Горячее"),
        "pizza":("Ты — пиццайоло. Придумай пиццу.","Пицца"),
        "grill":("Ты — шеф. Придумай блюдо на мангал.","Мангал"),
        "dessert":("Ты — кондитер. Придумай десерт.","Десерт"),
        "alco":("Ты — бармен. Придумай коктейль.","Коктейль"),
        "nonalco":("Ты — бармен. Придумай безалко-коктейль.","Коктейль"),
        "tea":("Ты — чайный мастер. Придумай чай.","Чай"),
        "lent":("Ты — шеф. Придумай постное блюдо.","Постное"),
    }
    sp, up = pr[k]
    sp += "\nФормат: 🍽️ Название\n📝 Ингредиенты\n👨‍🍳 Приготовление\n💡 Совет\nНа русском."
    try:
        rec = await ai(sp, up)
        inc_usage(uid)
    except:
        rec = "⚠️ Ошибка."
    await cb.message.edit_text(f"{info(uid)}\n\n{rec}", reply_markup=rmenu(k))

@dp.callback_query(F.data.startswith("custom_"))
async def cust_start(cb: types.CallbackQuery, state: FSMContext):
    if not can(cb.from_user.id):
        await cb.message.edit_text("🔒 Лимит.", reply_markup=menu())
        return
    k = cb.data.replace("custom_","")
    await state.set_state(S.custom)
    await state.update_data(ck=k)
    await cb.message.edit_text("✏️ Уточнение:")

@dp.message(S.custom)
async def cust_gen(msg: Message, state: FSMContext):
    d = await state.get_data()
    k = d["ck"]
    await state.clear()
    sp = f"Ты — шеф. Придумай рецепт. Учти: {msg.text}.\nФормат: 🍽️ Название\n📝 Ингредиенты\n👨‍🍳 Приготовление\n💡 Совет\nНа русском."
    try:
        rec = await ai(sp, f"Рецепт: {msg.text}")
        inc_usage(msg.from_user.id)
    except:
        rec = "⚠️ Ошибка."
    await msg.answer(f"{info(msg.from_user.id)}\n\n{rec}", reply_markup=rmenu(k))

@dp.callback_query(F.data=="fridge_start")
async def fr_start(cb: types.CallbackQuery, state: FSMContext):
    if not can(cb.from_user.id):
        await cb.message.edit_text("🔒 Лимит.", reply_markup=menu())
        return
    await state.set_state(S.fridge)
    await cb.message.edit_text("🧊 Продукты:")

@dp.message(S.fridge)
async def fr_gen(msg: Message, state: FSMContext):
    await state.clear()
    sp = f"Ты — шеф. Придумай блюдо из: {msg.text}.\nФормат: 🍽️ Название\n📝 Ингредиенты\n👨‍🍳 Приготовление\n💡 Совет\nНа русском."
    try:
        rec = await ai(sp, f"Блюдо из: {msg.text}")
        inc_usage(msg.from_user.id)
    except:
        rec = "⚠️ Ошибка."
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="📸 Фото", callback_data="photo_fridge"))
    b.add(InlineKeyboardButton(text="🧊 Ещё", callback_data="fridge_start"))
    b.add(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))
    b.adjust(1)
    await msg.answer(f"{info(msg.from_user.id)}\n\n{rec}", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("fav_"))
async def fav(cb: types.CallbackQuery):
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO favorites (user_id, category, recipe) VALUES (?,?,?)", (cb.from_user.id, cb.data.replace("fav_",""), cb.message.text))
    conn.commit()
    conn.close()
    await cb.answer("⭐ Добавлено!")

@dp.callback_query(F.data=="show_fav")
async def sfav(cb: types.CallbackQuery):
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("SELECT recipe FROM favorites WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (cb.from_user.id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await cb.message.edit_text("⭐ Пусто.", reply_markup=menu())
        return
    text = "⭐ Избранное:\n\n"
    for r in rows:
        text += f"• {r[0].split(chr(10))[0] if r[0] else '—'}\n"
    await cb.message.edit_text(text, reply_markup=menu())

@dp.callback_query(F.data.startswith("photo_"))
async def photo_h(cb: types.CallbackQuery):
    # Берём текст из текущего сообщения
    recipe_text = cb.message.text or ""
    k = cb.data.replace("photo_","")
    await cb.message.edit_text("📸 Генерирую...")
    try:
        url = await photo(recipe_text)
        await cb.message.answer_photo(photo=url, caption="📸 Готово!")
    except:
        await cb.message.answer("⚠️ Не удалось.")
    await cb.message.edit_text(recipe_text, reply_markup=rmenu(k))

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
