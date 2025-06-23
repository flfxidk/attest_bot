import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from datetime import datetime, timedelta, time
import asyncio
import json

API_TOKEN = '7548409263:AAFNaPL60NY57fB8mwXunFZkpawUPksNZPI'
ADMIN_ID = 417084716  # Замените на ваш ID

# Хранилище FSM
storage = MemoryStorage()

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=storage)

# Логирование
logging.basicConfig(level=logging.INFO)

# Путь к файлу данных
DATA_FILE = 'certifications.json'

# FSM для удаления
class DeleteCert(StatesGroup):
    waiting_for_index = State()

# FSM состояния
class AddCert(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()

# Загрузка и сохранение данных
def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("📋 Список аттестаций")
    keyboard.add("➕ Добавить", "🗑 Удалить")
    return keyboard

# Команда /start
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот для отслеживания аттестаций оборудования.\n\nКоманды:\n/add — добавить аттестацию\n/list — список аттестаций\n/delete — удаление аттестаций")

# Команда /add
@dp.message_handler(commands=['add'])
@dp.message_handler(lambda message: message.text == "➕ Добавить")
async def cmd_add(message: types.Message):
    await message.answer("Введите имя оборудования:")
    await AddCert.waiting_for_name.set()

@dp.message_handler(state=AddCert.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите дату аттестации (ДД.ММ.ГГГГ):")
    await AddCert.waiting_for_date.set()

@dp.message_handler(state=AddCert.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    try:
        cert_date = datetime.strptime(message.text, "%d.%m.%Y")
    except ValueError:
        await message.answer("Неверный формат даты. Попробуйте еще раз.")
        return

    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data.get(user_id, [])
    user_state = await state.get_data()
    user_data.append({
        'name': user_state['name'],
        'date': message.text
    })
    data[user_id] = user_data
    save_data(data)
    await message.answer("Аттестация добавлена!")
    await send_due_reminders(user_id)
    await state.finish()

# Команда /list
@dp.message_handler(commands=['list'])
@dp.message_handler(lambda message: message.text == "📋 Список аттестаций")
async def cmd_list(message: types.Message):
    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data.get(user_id, [])
    if not user_data:
        await message.answer("Список аттестаций пуст.")
    else:
        msg = "Текущие аттестации:\n"
        for idx, item in enumerate(user_data):
            msg += f"{idx + 1}. 📌 {item['name']} — {item['date']}\n"
        await message.answer(msg, reply_markup=main_keyboard())

@dp.message_handler(commands=['delete'])
@dp.message_handler(lambda message: message.text == "🗑 Удалить")
async def cmd_delete(message: types.Message):
    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data.get(user_id, [])
    if not user_data:
        await message.answer("Список пуст.", reply_markup=main_keyboard())
        return
    msg = "Выберите номер оборудования для удаления:\n"
    for i, item in enumerate(user_data):
        msg += f"{i + 1}. {item['name']} ({item['date']})\n"
    await message.answer(msg)
    await DeleteCert.waiting_for_index.set()

@dp.message_handler(state=DeleteCert.waiting_for_index)
async def process_delete(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data.get(user_id, [])
    try:
        index = int(message.text.strip()) - 1
        if index < 0 or index >= len(user_data):
            raise ValueError
    except:
        await message.answer("Неверный номер. Попробуйте еще раз.")
        return
    removed = user_data.pop(index)
    data[user_id] = user_data
    save_data(data)
    await message.answer(f"Удалено: {removed['name']} ({removed['date']})", reply_markup=main_keyboard())
    await send_due_reminders(user_id)
    await state.finish()      

# Обработчик кнопок
@dp.callback_query_handler(lambda c: c.data.startswith('attest_'))
async def attest_done(callback_query: types.CallbackQuery):
    user_id = str(callback_query.from_user.id)
    index = int(callback_query.data.split('_')[1])
    data = load_data()
    user_data = data.get(user_id, [])

    if index >= len(user_data):
        await callback_query.answer("Устаревшая кнопка.")
        return

    await bot.send_message(user_id, f"Введите новую дату для {user_data[index]['name']} (ДД.ММ.ГГГГ):")

    async def new_date_handler(message: types.Message):
        try:
            new_date = datetime.strptime(message.text, "%d.%m.%Y")
        except ValueError:
            await message.answer("Неверный формат. Попробуйте еще раз.")
            return await new_date_handler(message)
        user_data[index]['date'] = message.text
        data[user_id] = user_data
        await send_due_reminders(user_id) 
        save_data(data)
        await message.answer("Дата обновлена!")
        await send_due_reminders(user_id) 
        dp.unregister_message_handler(new_date_handler)

    dp.register_message_handler(new_date_handler)

async def send_due_reminders(user_id):
    now = datetime.now()
    data = load_data()
    certs = data.get(str(user_id), [])
    for i, item in enumerate(certs):
        try:
            cert_date = datetime.strptime(item['date'], "%d.%m.%Y")
        except:
            continue
        days_diff = (cert_date - now).days
        if days_diff in [3, 0] or days_diff < 0:
            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("✅ Аттестовано", callback_data=f"attest_{i}")
            )
            try:
                await bot.send_message(user_id,
                    f"🔔 Напоминание об аттестации: {item['name']}\nДата: {item['date']}",
                    reply_markup=kb
                )
            except Exception as e:
                logging.warning()    

# Фоновая задача напоминаний каждый день в 9:00
async def reminder_loop():
    while True:
        now = datetime.now()
        target_time = datetime.combine(now.date(), time(9, 00))
        if now > target_time:
            target_time += timedelta(days=1)
        await asyncio.sleep((target_time - now).total_seconds())

        data = load_data()
        for user_id, certs in data.items():
            for i, item in enumerate(certs):
                try:
                    cert_date = datetime.strptime(item['date'], "%d.%m.%Y")
                except:
                    continue
                days_diff = (cert_date - datetime.now()).days
                if days_diff in [3, 0] or days_diff < 0:
                    try:
                        kb = InlineKeyboardMarkup().add(
                            InlineKeyboardButton("✅ Аттестовано", callback_data=f"attest_{i}")
                        )
                        await bot.send_message(user_id,
                            f"🔔 Напоминание об аттестации: {item['name']}\nДата: {item['date']}",
                            reply_markup=kb
                        )
                    except Exception as e:
                        logging.warning(f"Не удалось отправить сообщение: {e}")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(reminder_loop())
    executor.start_polling(dp, skip_updates=True)
