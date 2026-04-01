import asyncio
import logging
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import gspread
from google.oauth2.service_account import Credentials

# ===================== НАСТРОЙКИ =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
bot = Bot(token=BOT_TOKEN)
SHEET_ID = '13vZPiFQZxUOrCbCjeDuIWK6H7s57rXsaM2Zv_QlNbiE'
SHEET_NAME = 'отчет по средствам на карте'
WEB_APP_URL = 'https://script.google.com/macros/s/AKfycbz_EjCPMmN8OnEcS8CeTDjhuwJuEJ7DR49ef16aJo3wqi2DmwXGa0dLkyz62lRmpYXG/exec?page=dashboard'
PASSWORD = '2026'
CREDENTIALS_FILE = 'credentials.json'
# =====================================================

logging.basicConfig(level=logging.INFO)

# Google Sheets
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Авторизованные пользователи
authorized_users = set()

class Form(StatesGroup):
    waiting_password = State()
    waiting_type = State()
    waiting_amount = State()
    waiting_reason = State()

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Добавить запись', callback_data='new_record')],
        [InlineKeyboardButton(text='📊 Открыть дашборд', web_app=WebAppInfo(url=WEB_APP_URL))]
    ])

def type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📈 Поступление', callback_data='type_in')],
        [InlineKeyboardButton(text='📉 Расход', callback_data='type_out')],
        [InlineKeyboardButton(text='« Назад', callback_data='back_menu')]
    ])

def after_record_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Ещё запись', callback_data='new_record')],
        [InlineKeyboardButton(text='📊 Открыть дашборд', web_app=WebAppInfo(url=WEB_APP_URL))]
    ])

def get_today():
    return datetime.now().strftime('%d.%m.%y')

def fmt(n):
    return f'{int(n):,}'.replace(',', ' ')

def write_to_sheet(date, amount, reason, op_type):
    data = sheet.get_all_values()
    today_short = date[:5]  # dd.mm
    target_row = None

    for i, row in enumerate(data[3:], start=4):
        cell = str(row[0])
        if today_short in cell:
            target_row = i
            break

    if target_row is None:
        target_row = len(data) + 1
        sheet.update_cell(target_row, 1, date)

    if op_type == 'in':
        sheet.update_cell(target_row, 2, amount)
    else:
        sheet.update_cell(target_row, 3, amount)
        sheet.update_cell(target_row, 4, reason)

# ==================== ХЭНДЛЕРЫ ====================

@dp.message(Command('start'))
async def cmd_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in authorized_users:
        await state.set_state(Form.waiting_password)
        await message.answer('🔒 Введи пароль для доступа:')
        return
    await message.answer('👋 Главное меню:', reply_markup=main_menu_kb())

@dp.message(Form.waiting_password)
async def check_password(message: types.Message, state: FSMContext):
    if message.text == PASSWORD:
        authorized_users.add(message.from_user.id)
        await state.clear()
        await message.answer('✅ Доступ открыт! Добро пожаловать.', reply_markup=main_menu_kb())
    else:
        await message.answer('❌ Неверный пароль. Попробуй ещё раз:')

@dp.message(Form.waiting_amount)
async def process_amount(message: types.Message, state: FSMContext):
    if message.from_user.id not in authorized_users:
        await state.set_state(Form.waiting_password)
        await message.answer('🔒 Введи пароль:')
        return

    try:
        amount = float(message.text.replace(' ', '').replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer('❌ Введи сумму числом, например: *1500*', parse_mode='Markdown')
        return

    data = await state.get_data()
    op_type = data.get('type')
    await state.update_data(amount=amount)

    if op_type == 'out':
        await state.set_state(Form.waiting_reason)
        await message.answer('📝 Укажи обоснование расхода:')
    else:
        date = get_today()
        write_to_sheet(date, amount, '', 'in')
        await state.clear()
        await message.answer(
            f'✅ *Записано!*\n📅 Дата: {date}\n📈 Поступление: +{fmt(amount)} ₽',
            parse_mode='Markdown',
            reply_markup=after_record_kb()
        )

@dp.message(Form.waiting_reason)
async def process_reason(message: types.Message, state: FSMContext):
    if message.from_user.id not in authorized_users:
        await state.set_state(Form.waiting_password)
        await message.answer('🔒 Введи пароль:')
        return

    data = await state.get_data()
    amount = data.get('amount')
    reason = message.text
    date = get_today()

    write_to_sheet(date, amount, reason, 'out')
    await state.clear()
    await message.answer(
        f'✅ *Записано!*\n📅 Дата: {date}\n📉 Расход: −{fmt(amount)} ₽\n📝 {reason}',
        parse_mode='Markdown',
        reply_markup=after_record_kb()
    )

@dp.message()
async def handle_any(message: types.Message, state: FSMContext):
    if message.from_user.id not in authorized_users:
        await state.set_state(Form.waiting_password)
        await message.answer('🔒 Введи пароль для доступа:')
        return
    await message.answer('👋 Главное меню:', reply_markup=main_menu_kb())

@dp.callback_query(F.data == 'new_record')
async def cb_new_record(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in authorized_users:
        await callback.answer('Сначала введи пароль')
        return
    await callback.message.edit_text('📊 Выбери тип операции:', reply_markup=type_kb())

@dp.callback_query(F.data == 'type_in')
async def cb_type_in(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(type='in')
    await state.set_state(Form.waiting_amount)
    await callback.message.edit_text('💰 Введи сумму поступления (₽):')

@dp.callback_query(F.data == 'type_out')
async def cb_type_out(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(type='out')
    await state.set_state(Form.waiting_amount)
    await callback.message.edit_text('💸 Введи сумму расхода (₽):')

@dp.callback_query(F.data == 'back_menu')
async def cb_back_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('👋 Главное меню:', reply_markup=main_menu_kb())

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
