import os
import logging
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

TOKEN = os.environ.get("7548409263:AAFNaPL60NY57fB8mwXunFZkpawUPksNZPI")

ADMIN_ID = 417084716  # Замените на ваш ID

# Хранилище FSM
storage = MemoryStorage()

# Инициализация бота и диспетчера
bot = Bot(TOKEN)
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


# FSM для предложений
class Suggestion(StatesGroup):
    waiting_for_suggestion = State()


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


def main_keyboard(user_id=None):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("📋 Список аттестаций")
    keyboard.add("➕ Добавить", "🗑 Удалить")
    
    # Для админа добавляем кнопку админ панели в одну строку с предложениями
    if user_id and is_admin(user_id):
        keyboard.add("💡 Предложения", "🔧 Админ панель")
    else:
        keyboard.add("💡 Предложения")
    
    return keyboard


# Команда /start
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот для отслеживания аттестаций оборудования.\n\nКоманды:\n/add — добавить аттестацию\n/list — список аттестаций\n/delete — удаление аттестаций\n/whoami — информация о пользователе",
        reply_markup=main_keyboard(message.from_user.id))


# Команда /whoami для отображения информации о пользователе
@dp.message_handler(commands=['whoami'])
async def cmd_whoami(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Не установлен"
    first_name = message.from_user.first_name or "Не указано"
    is_admin_status = "✅ Да" if is_admin(user_id) else "❌ Нет"
    
    info_msg = f"👤 Информация о пользователе:\n\n" \
               f"🆔 Ваш ID: {user_id}\n" \
               f"👨‍💼 Имя: {first_name}\n" \
               f"📱 Username: @{username}\n" \
               f"🔧 Администратор: {is_admin_status}"
    
    await message.answer(info_msg, reply_markup=main_keyboard(user_id))


# Команда /add
@dp.message_handler(commands=['add'])
@dp.message_handler(lambda message: message.text == "➕ Добавить")
async def cmd_add(message: types.Message):
    await message.answer("Введите имя оборудования:")
    await AddCert.waiting_for_name.set()


@dp.message_handler(state=AddCert.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите дату окончания аттестации (ДД.ММ.ГГГГ):")
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
    user_data.append({'name': user_state['name'], 'date': message.text})
    data[user_id] = user_data
    save_data(data)
    await message.answer("Аттестация добавлена!", reply_markup=main_keyboard(message.from_user.id))
    await state.finish()


def get_status_emoji(cert_date_str):
    """Возвращает эмодзи статуса в зависимости от даты аттестации"""
    try:
        cert_date = datetime.strptime(cert_date_str, "%d.%m.%Y")
        now = datetime.now()
        days_diff = (cert_date - now).days
        
        if days_diff < 0:
            return "🔴"  # Просрочена
        elif days_diff <= 3:
            return "🟡"  # Скоро истекает
        else:
            return "🟢"  # Актуально
    except ValueError:
        return "❓"  # Ошибка в формате даты


# Команда /list
@dp.message_handler(commands=['list'])
@dp.message_handler(lambda message: message.text == "📋 Список аттестаций")
async def cmd_list(message: types.Message):
    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data.get(user_id, [])
    if not user_data:
        await message.answer("Список аттестаций пуст.",
                             reply_markup=main_keyboard(message.from_user.id))
    else:
        msg = "Текущие аттестации:\n\n"
        for idx, item in enumerate(user_data):
            status_emoji = get_status_emoji(item['date'])
            msg += f"{idx + 1}. {status_emoji} {item['name']} — {item['date']}\n"
        
        msg += "\n🟢 — Актуально\n🟡 — Скоро истекает (≤3 дня)\n🔴 — Просрочена"
        await message.answer(msg, reply_markup=main_keyboard(message.from_user.id))


@dp.message_handler(commands=['delete'])
@dp.message_handler(lambda message: message.text == "🗑 Удалить")
async def cmd_delete(message: types.Message):
    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data.get(user_id, [])
    if not user_data:
        await message.answer("Список пуст.", reply_markup=main_keyboard(message.from_user.id))
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
    await message.answer(f"Удалено: {removed['name']} ({removed['date']})",
                         reply_markup=main_keyboard(message.from_user.id))
    await state.finish()


# FSM для обновления даты
class UpdateDate(StatesGroup):
    waiting_for_new_date = State()


# Обработчик кнопок
@dp.callback_query_handler(lambda c: c.data.startswith('attest_'))
async def attest_done(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = str(callback_query.from_user.id)
    index = int(callback_query.data.split('_')[1])
    data = load_data()
    user_data = data.get(user_id, [])

    if index >= len(user_data):
        await callback_query.answer("Устаревшая кнопка.")
        return

    await state.update_data(cert_index=index)
    await bot.send_message(
        user_id,
        f"Введите новую дату для {user_data[index]['name']} (ДД.ММ.ГГГГ):")
    await UpdateDate.waiting_for_new_date.set()
    await callback_query.answer()


@dp.message_handler(state=UpdateDate.waiting_for_new_date)
async def process_new_date(message: types.Message, state: FSMContext):
    try:
        new_date = datetime.strptime(message.text, "%d.%m.%Y")
    except ValueError:
        await message.answer("Неверный формат даты. Попробуйте еще раз.")
        return

    user_id = str(message.from_user.id)
    data = load_data()
    user_data = data.get(user_id, [])
    user_state = await state.get_data()
    index = user_state['cert_index']

    if index < len(user_data):
        user_data[index]['date'] = message.text
        data[user_id] = user_data
        save_data(data)
        await message.answer("Дата обновлена!", reply_markup=main_keyboard(int(user_id)))
    await send_due_reminders(user_id)
    await state.finish()


# Обработчик предложений
@dp.message_handler(lambda message: message.text == "💡 Предложения")
async def cmd_suggestions(message: types.Message):
    await message.answer(
        "💡 Есть идея для улучшения бота?\n\n"
        "Напишите ваше предложение, и я передам его разработчику!")
    await Suggestion.waiting_for_suggestion.set()


@dp.message_handler(state=Suggestion.waiting_for_suggestion)
async def process_suggestion(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "Без username"
    first_name = message.from_user.first_name or "Анонимный"

    suggestion_text = f"💡 Новое предложение от пользователя:\n\n" \
                     f"👤 Имя: {first_name}\n" \
                     f"📱 Username: @{username}\n" \
                     f"🆔 ID: {user_id}\n\n" \
                     f"📝 Предложение:\n{message.text}"

    try:
        await bot.send_message(ADMIN_ID, suggestion_text)
        await message.answer(
            "✅ Спасибо за предложение! Оно передано разработчику.",
            reply_markup=main_keyboard(message.from_user.id))
    except Exception as e:
        logging.error(f"Ошибка отправки предложения: {e}")
        await message.answer(
            "❌ Произошла ошибка при отправке предложения. Попробуйте позже.",
            reply_markup=main_keyboard(message.from_user.id))

    await state.finish()


# FSM для админских команд
class AdminMessage(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_message = State()


class AdminNotify(StatesGroup):
    waiting_for_user_id = State()


# Проверка админских прав
def is_admin(user_id):
    return user_id == ADMIN_ID


# Админская команда для отправки сообщения пользователю
@dp.message_handler(commands=['admin_message'])
async def admin_message_start(message: types.Message):
    
    await message.answer("👤 Введите ID пользователя для отправки сообщения:")
    await AdminMessage.waiting_for_user_id.set()


@dp.message_handler(state=AdminMessage.waiting_for_user_id)
async def admin_message_get_user(message: types.Message, state: FSMContext):
    
    try:
        target_user_id = int(message.text.strip())
        await state.update_data(target_user_id=target_user_id)
        await message.answer("📝 Введите сообщение для отправки:")
        await AdminMessage.waiting_for_message.set()
    except ValueError:
        await message.answer("❌ Неверный формат ID. Введите числовой ID пользователя:")


@dp.message_handler(state=AdminMessage.waiting_for_message)
async def admin_message_send(message: types.Message, state: FSMContext):
    
    user_state = await state.get_data()
    target_user_id = user_state['target_user_id']
    admin_message = message.text
    
    try:
        await bot.send_message(
            target_user_id,
            f"📢 Сообщение от администратора:\n\n{admin_message}"
        )
        await message.answer(f"✅ Сообщение отправлено пользователю {target_user_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки сообщения: {e}")
    
    await state.finish()


# Админская команда для ручной отправки уведомлений
@dp.message_handler(commands=['admin_notify'])
async def admin_notify_start(message: types.Message):
    
    await message.answer("👤 Введите ID пользователя для отправки уведомлений об аттестациях (или 'all' для всех пользователей):")
    await AdminNotify.waiting_for_user_id.set()


@dp.message_handler(state=AdminNotify.waiting_for_user_id)
async def admin_notify_send(message: types.Message, state: FSMContext):
    
    target = message.text.strip().lower()
    
    try:
        if target == 'all':
            # Отправить уведомления всем пользователям
            data = load_data()
            sent_count = 0
            for user_id in data.keys():
                await send_due_reminders(user_id)
                sent_count += 1
            await message.answer(f"✅ Уведомления отправлены {sent_count} пользователям")
        else:
            # Отправить уведомления конкретному пользователю
            target_user_id = int(target)
            await send_due_reminders(str(target_user_id))
            await message.answer(f"✅ Уведомления отправлены пользователю {target_user_id}")
    except ValueError:
        await message.answer("❌ Неверный формат. Введите числовой ID или 'all':")
        return
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки уведомлений: {e}")
    
    await state.finish()


# Админская команда для просмотра статистики
@dp.message_handler(commands=['admin_stats'])
async def admin_stats(message: types.Message):
    
    data = load_data()
    total_users = len(data)
    total_certs = sum(len(certs) for certs in data.values())
    
    # Подсчет статусов
    overdue_count = 0
    due_soon_count = 0
    active_count = 0
    
    now = datetime.now()
    for user_certs in data.values():
        for cert in user_certs:
            try:
                cert_date = datetime.strptime(cert['date'], "%d.%m.%Y")
                days_diff = (cert_date - now).days
                
                if days_diff < 0:
                    overdue_count += 1
                elif days_diff <= 3:
                    due_soon_count += 1
                else:
                    active_count += 1
            except ValueError:
                continue
    
    stats_msg = f"📊 Статистика бота:\n\n" \
                f"👥 Всего пользователей: {total_users}\n" \
                f"📋 Всего аттестаций: {total_certs}\n\n" \
                f"🟢 Актуальных: {active_count}\n" \
                f"🟡 Скоро истекают: {due_soon_count}\n" \
                f"🔴 Просроченных: {overdue_count}\n\n" \
                f"📝 Доступные админ-команды:\n" \
                f"/admin_message - отправить сообщение пользователю\n" \
                f"/admin_notify - отправить уведомления об аттестациях\n" \
                f"/admin_stats - показать статистику"
    
    await message.answer(stats_msg)


# Обработчик кнопки "Админ панель"
@dp.message_handler(lambda message: message.text == "🔧 Админ панель")
async def cmd_admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer(f"❌ У вас нет прав администратора.\n\n🆔 Ваш ID: {message.from_user.id}\n🔧 Статус: Обычный пользователь")
        return
    
    admin_menu = """
🔧 **Админ панель**

📊 `/admin_stats` - Статистика бота
📢 `/admin_message` - Отправить сообщение пользователю  
🔔 `/admin_notify` - Отправить уведомления

💡 Выберите нужную команду или введите её вручную.
    """
    
    # Создаем инлайн клавиатуру для админ панели
    admin_kb = InlineKeyboardMarkup(row_width=1)
    admin_kb.add(
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("📢 Отправить сообщение", callback_data="admin_message"),
        InlineKeyboardButton("🔔 Отправить уведомления", callback_data="admin_notify")
    )
    
    await message.answer(admin_menu, reply_markup=admin_kb, parse_mode="Markdown")


# Обработчик инлайн кнопок админ панели
@dp.callback_query_handler(lambda c: c.data.startswith('admin_'))
async def admin_panel_callback(callback_query: types.CallbackQuery):
    
    command = callback_query.data
    
    if command == "admin_stats":
        await admin_stats(callback_query.message)
    elif command == "admin_message":
        await admin_message_start(callback_query.message)
    elif command == "admin_notify":
        await admin_notify_start(callback_query.message)
    
    await callback_query.answer()


async def send_due_reminders(user_id):
    now = datetime.now()
    data = load_data()  # Всегда загружаем свежие данные
    certs = data.get(str(user_id), [])

    for i, item in enumerate(certs):
        try:
            cert_date = datetime.strptime(item['date'], "%d.%m.%Y")
        except:
            continue

        days_diff = (cert_date - now).days

        # Отправляем напоминание только если условия выполнены
        if days_diff in [3, 0] or days_diff < 0:
            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("✅ Аттестовано",
                                     callback_data=f"attest_{i}"))
            try:
                status = ""
                if days_diff < 0:
                    status = f" (просрочено на {abs(days_diff)} дн.)"
                elif days_diff == 0:
                    status = " (сегодня)"
                elif days_diff == 3:
                    status = " (через 3 дня)"

                await bot.send_message(
                    user_id,
                    f"🔔 Напоминание об аттестации: {item['name']}\nДата: {item['date']}{status}",
                    reply_markup=kb)
            except Exception as e:
                logging.warning(f"Не удалось отправить напоминание: {e}")


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
                            InlineKeyboardButton("✅ Аттестовано",
                                                 callback_data=f"attest_{i}"))
                        await bot.send_message(
                            user_id,
                            f"🔔 Напоминание об аттестации: {item['name']}\nДата: {item['date']}",
                            reply_markup=kb)
                    except Exception as e:
                        logging.warning(f"Не удалось отправить сообщение: {e}")


async def startup_reminders():
    """Проверка и отправка напоминаний при запуске бота"""
    data = load_data()
    for user_id in data.keys():
        await send_due_reminders(user_id)


async def on_startup(dp):
    """Выполняется при запуске бота"""
    await startup_reminders()
    logging.info("Startup reminders sent")


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(reminder_loop())
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)

