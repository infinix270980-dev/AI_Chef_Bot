cat > chef_bot.py << 'EOF'
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import httpx
import sqlite3
from datetime import datetime

BOT_TOKEN = "ТВОЙ_ТОКЕН_ОТ_BOTFATHER"
VSEGPT_API_KEY = "ТВОЙ_КЛЮЧ_VSEGPT"
MODEL_NAME = "deepseek/deepseek-chat"
FREE_LIMIT = 5

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

def init_db():
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id BIGINT,
            category TEXT,
            recipe TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usage_stats (
            user_id BIGINT,
            week_start TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, week_start)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            user_id BIGINT PRIMARY KEY,
            subscribed_until TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def is_subscribed(user_id: int) -> bool:
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("SELECT subscribed_until FROM subscribers WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return datetime.now() < datetime.fromisoformat(row[0])
    return False

def get_usage(user_id: int) -> int:
    week_start = datetime.now().strftime("%Y-%W")
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("SELECT count FROM usage_stats WHERE user_id = ? AND week_start = ?", (user_id, week_start))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def inc_usage(user_id: int):
    week_start = datetime.now().strftime("%Y-%W")
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("SELECT count FROM usage_stats WHERE user_id = ? AND week_start = ?", (user_id, week_start))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE usage_stats SET count = count + 1 WHERE user_id = ? AND week_start = ?", (user_id, week_start))
    else:
        cur.execute("INSERT INTO usage_stats (user_id, week_start, count) VALUES (?, ?, 1)", (user_id, week_start))
    conn.commit()
    conn.close()

def check_limit(user_id: int) -> bool:
    if is_subscribed(user_id):
        return True
    return get_usage(user_id) < FREE_LIMIT

class RecipeStates(StatesGroup):
    waiting_custom = State()
    waiting_fridge = State()

CATEGORIES = {
    "salad": "🥗 Салаты",
    "cold": "🧊 Холодные закуски",
    "soup": "🍜 Супы",
    "hot": "🔥 Горячие блюда",
    "pizza": "🍕 Пицца",
    "grill": "🥩 Мангал",
    "dessert": "🍰 Десерты",
    "alco": "🍸 Алкогольные коктейли",
    "nonalco": "🍹 Безалкогольные коктейли",
    "tea": "🫖 Вкусный чай",
    "lent": "🥬 Постные блюда",
}

def main_menu():
    builder = InlineKeyboardBuilder()
    for key, label in CATEGORIES.items():
        builder.add(InlineKeyboardButton(text=label, callback_data=f"cat_{key}"))
    builder.add(InlineKeyboardButton(text="🧊 Что в холодильнике?", callback_data="fridge_start"))
    builder.add(InlineKeyboardButton(text="⭐ Избранное", callback_data="show_fav"))
    builder.add(InlineKeyboardButton(text="💳 Подписка", callback_data="subscribe_info"))
    builder.add(InlineKeyboardButton(text="ℹ️ О боте", callback_data="about"))
    builder.adjust(1)
    return builder.as_markup()

def recipe_menu(key):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔄 Другой рецепт", callback_data=f"cat_{key}"))
    builder.add(InlineKeyboardButton(text="✏️ Уточнить", callback_data=f"custom_{key}"))
    builder.add(InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_{key}"))
    builder.add(InlineKeyboardButton(text="📸 Фото блюда", callback_data=f"photo_{key}"))
    builder.add(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))
    builder.adjust(2)
    return builder.as_markup()

def back_to_menu():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🏠 В меню", callback_data="menu"))
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "👨‍🍳 AI-Шеф v2.0!\n\n"
        f"Бесплатно: {FREE_LIMIT} рецептов в неделю.\n"
        "Выбери категорию:",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "about")
async def about(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👨‍🍳 AI-Шеф v2.0\n\n"
        f"• {FREE_LIMIT} бесплатных рецептов в неделю\n"
        "• 11 категорий\n• Уточнения\n• Избранное\n• Фото блюд\n• Рецепт из продуктов",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "subscribe_info")
async def subscribe_info(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💳 Подписка AI-Шеф\n\n"
        f"Бесплатно: {FREE_LIMIT} рецептов в неделю.\n"
        "Pro: безлимит.\n\n"
        "Цена: 199₽/мес (скоро).",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "menu")
async def menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Выбери категорию:", reply_markup=main_menu())

async def ask_ai(system_prompt: str, user_prompt: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.vsegpt.ru/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {VSEGPT_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 1.0,
                "max_tokens": 1000
            }
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"]

def clean_name(text: str) -> str:
    """Вытаскивает название блюда из первой строки"""
    first_line = text.split("\n")[0] if text else "dish"
    chars = "🍽️🍸🍹🫖🍕🥩🍜🥬🧊🔥🥗🍰👨‍🍳📝💡⭐►▶•#*"
    for c in chars:
        first_line = first_line.replace(c, "")
    return first_line.strip() or "dish"

async def generate_photo(recipe_text: str) -> str:
    """Генерирует фото по названию блюда"""
    name = clean_name(recipe_text)
    prompt = f"Professional food photography of {name}, restaurant style, high quality, appetizing"
    url = f"https://image.pollinations.ai/prompt/{prompt}?width=512&height=512&nologo=true"
    return url

@dp.callback_query(F.data.startswith("cat_"))
async def category_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not check_limit(user_id):
        await callback.message.edit_text(
            f"🔒 Лимит исчерпан ({FREE_LIMIT} рецептов в неделю).",
            reply_markup=back_to_menu()
        )
        return
    
    key = callback.data.replace("cat_", "")
    label = CATEGORIES[key]
    
    await callback.message.edit_text(f"👨‍🍳 Готовлю {label.lower()}...")
    
    prompts = {
        "salad": ("Ты — шеф-повар. Придумай оригинальный рецепт салата.", "Придумай рецепт салата."),
        "cold": ("Ты — шеф-повар. Придумай рецепт холодной закуски.", "Придумай рецепт закуски."),
        "soup": ("Ты — шеф-повар. Придумай рецепт супа.", "Придумай рецепт супа."),
        "hot": ("Ты — шеф-повар. Придумай рецепт горячего блюда.", "Придумай рецепт горячего."),
        "pizza": ("Ты — пиццайоло. Придумай рецепт пиццы.", "Придумай рецепт пиццы."),
        "grill": ("Ты — шеф-повар. Придумай рецепт для мангала.", "Придумай рецепт для мангала."),
        "dessert": ("Ты — кондитер. Придумай рецепт десерта.", "Придумай рецепт десерта."),
        "alco": ("Ты — бармен. Придумай рецепт алкогольного коктейля.", "Придумай коктейль."),
        "nonalco": ("Ты — бармен. Придумай безалкогольный коктейль.", "Придумай безалкогольный коктейль."),
        "tea": ("Ты — чайный мастер. Придумай рецепт чая.", "Придумай рецепт чая."),
        "lent": ("Ты — шеф-повар. Придумай постное блюдо.", "Придумай постное блюдо."),
    }
    
    system_prompt, user_prompt = prompts[key]
    system_prompt += "\nФормат: 🍽️ Название\n📝 Ингредиенты\n👨‍🍳 Приготовление\n💡 Совет\nОтвечай на русском. Без Markdown."
    
    try:
        recipe = await ask_ai(system_prompt, user_prompt)
        inc_usage(user_id)
    except:
        recipe = "⚠️ Ошибка."
    
    await callback.message.edit_text(recipe, reply_markup=recipe_menu(key))

@dp.callback_query(F.data.startswith("custom_"))
async def custom_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not check_limit(user_id):
        await callback.message.edit_text(f"🔒 Лимит исчерпан.", reply_markup=back_to_menu())
        return
    
    key = callback.data.replace("custom_", "")
    await state.set_state(RecipeStates.waiting_custom)
    await state.update_data(custom_key=key)
    await callback.message.edit_text("✏️ Напиши уточнение:")

@dp.message(RecipeStates.waiting_custom)
async def custom_generate(message: types.Message, state: FSMContext):
    data = await state.get_data()
    key = data["custom_key"]
    label = CATEGORIES[key]
    await state.clear()
    
    await message.answer(f"👨‍🍳 Готовлю {label.lower()} с учётом: {message.text}...")
    
    system_prompt = f"Ты — шеф-повар. Придумай рецепт. Учти пожелание: {message.text}.\nФормат: 🍽️ Название\n📝 Ингредиенты\n👨‍🍳 Приготовление\n💡 Совет\nОтвечай на русском. Без Markdown."
    
    try:
        recipe = await ask_ai(system_prompt, f"Придумай рецепт с учётом пожелания: {message.text}")
        inc_usage(message.from_user.id)
    except:
        recipe = "⚠️ Ошибка."
    
    await message.answer(recipe, reply_markup=recipe_menu(key))

@dp.callback_query(F.data == "fridge_start")
async def fridge_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not check_limit(user_id):
        await callback.message.edit_text(f"🔒 Лимит исчерпан.", reply_markup=back_to_menu())
        return
    
    await state.set_state(RecipeStates.waiting_fridge)
    await callback.message.edit_text("🧊 Напиши, что есть в холодильнике (через запятую):")

@dp.message(RecipeStates.waiting_fridge)
async def fridge_generate(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👨‍🍳 Думаю...")
    
    system_prompt = f"Ты — шеф-повар. Придумай блюдо из: {message.text}.\nФормат: 🍽️ Название\n📝 Ингредиенты\n👨‍🍳 Приготовление\n💡 Совет\nОтвечай на русском. Без Markdown."
    
    try:
        recipe = await ask_ai(system_prompt, f"Придумай блюдо из: {message.text}")
        inc_usage(message.from_user.id)
    except:
        recipe = "⚠️ Ошибка."
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📸 Фото блюда", callback_data="photo_fridge"))
    builder.add(InlineKeyboardButton(text="🧊 Ещё рецепт", callback_data="fridge_start"))
    builder.add(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))
    builder.adjust(1)
    
    await message.answer(recipe, reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("fav_"))
async def add_fav(callback: types.CallbackQuery):
    key = callback.data.replace("fav_", "")
    recipe = callback.message.text
    
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO favorites (user_id, category, recipe) VALUES (?, ?, ?)", 
                (callback.from_user.id, key, recipe))
    conn.commit()
    conn.close()
    
    await callback.answer("⭐ Добавлено в избранное!")

@dp.callback_query(F.data == "show_fav")
async def show_fav(callback: types.CallbackQuery):
    conn = sqlite3.connect("chef.db")
    cur = conn.cursor()
    cur.execute("SELECT category, recipe FROM favorites WHERE user_id = ? ORDER BY created_at DESC LIMIT 10", 
                (callback.from_user.id,))
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        await callback.message.edit_text("⭐ Избранное пусто.", reply_markup=main_menu())
        return
    
    text = "⭐ Твои избранные рецепты:\n\n"
    for cat, rec in rows:
        first_line = rec.split("\n")[0] if rec else "Без названия"
        text += f"• {first_line}\n"
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("photo_"))
async def photo_handler(callback: types.CallbackQuery):
    recipe_text = callback.message.text or ""
    key = callback.data.replace("photo_", "")
    
    await callback.message.edit_text("📸 Генерирую фото...")
    
    try:
        photo_url = await generate_photo(recipe_text)
        await callback.message.answer_photo(photo=photo_url, caption="📸 Готово!")
    except Exception as e:
        await callback.message.answer(f"⚠️ Не удалось сгенерировать фото.")
    
    await callback.message.edit_text(recipe_text, reply_markup=recipe_menu(key))

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
EOF
