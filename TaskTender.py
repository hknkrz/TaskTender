import asyncio
import re

from aiogram import Bot, Dispatcher, executor, types, filters
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message, InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger

from db import db_start, add_task, sent_check, insert_user, get_task, get_users_list, blacklist_update, blacklist_add


async def on_startup(_):
    await db_start()


loop = asyncio.get_event_loop()
storage = MemoryStorage()
bot = Bot(token="123")
dp = Dispatcher(bot, storage=MemoryStorage())

ADMIN = 456
CHAT_ID = 789


class AdminStates(StatesGroup):
    started = State()
    term = State()
    price = State()
    task = State()
    priority = State()
    sent = State()


class AdminDiscuss(StatesGroup):
    started = State()


class UserStates(StatesGroup):
    awaiting_decision = State()
    conditions = State()
    sent = State()


@dp.message_handler(filters.Command("start"))
async def start_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN:
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Новый таск")],
        ],
        resize_keyboard=True
    )
    await AdminStates.started.set()
    await message.answer("Чтобы отправить таску - нажмите на кнопку", reply_markup=keyboard)


@dp.message_handler(lambda message: message.text == "Новый таск", state=AdminStates.started)
async def new_handler(message: types.Message, state: FSMContext):
    await AdminStates.term.set()
    await message.answer("Срок реализации?")


@dp.message_handler(state=AdminStates.term)
async def term_handler(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["term"] = message.text
    await AdminStates.price.set()
    await message.answer("Укажите цену")


@dp.message_handler(state=AdminStates.price)
async def price_handler(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["price"] = message.text
    await AdminStates.task.set()
    await message.answer("Каково условие задачи?")


@dp.message_handler(state=AdminStates.task)
async def task_handler(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["task"] = message.text
    await AdminStates.priority.set()
    await message.answer("Какой приоритет у задачи?")


@dp.message_handler(state=AdminStates.priority)
async def priority_handler(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["priority"] = message.text
    await AdminStates.sent.set()
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton(text="Отправить", callback_data="Отправить"),
                 InlineKeyboardButton(text="Отмена", callback_data="Отмена"))
    await message.answer("Отправить задачу в чат?", reply_markup=keyboard)


@dp.callback_query_handler(state=AdminStates.sent)
async def sent_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if callback_query.data != "Отправить":
        await callback_query.answer("Задача отменена")
        await state.finish()
        return
    await blacklist_update()
    async with state.proxy() as data:
        message_text = f"{data['term']}\n{data['price']}\n{data['task']}\n{data['priority']}"

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton(text="Взять в работу", callback_data="Взять в работу"),
                 InlineKeyboardButton(text="Обсудить", callback_data="Обсудить"))
    sent_message = await dp.bot.send_message(chat_id=-CHAT_ID, text=message_text, reply_markup=keyboard)

    await add_task(sent_message.message_id, -CHAT_ID, message_text)

    await state.finish()


@dp.callback_query_handler(Text(equals="Взять в работу"))
async def accept_task(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    message_id = callback_query.message.message_id
    chat_id = callback_query.message.chat.id

    # DEBUG
    # await callback_query.message.reply(f"message - {message_id},chat - {chat_id}")

    # DEBUG

    is_sent = await sent_check(callback_query.from_user.id, message_id, chat_id)
    if is_sent is not None:
        await callback_query.answer(f"Вы уже взяли эту задачу")
        return

    async with state.proxy() as data:
        data["message_id"] = message_id
        data["chat_id"] = chat_id
    await callback_query.message.reply("Ваши условия?")
    await UserStates.awaiting_decision.set()


@dp.message_handler(state=UserStates.awaiting_decision, content_types=types.ContentType.TEXT)
async def handle_condition(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton(text="Взять в работу", callback_data="Взять в работу"),
                 InlineKeyboardButton(text="Обсудить", callback_data="Обсудить"))

    async with state.proxy() as data:
        # DEBUG
        await message.answer(f'message - {data["message_id"]}, chat - {data["chat_id"]}')

        # DEBUG

        # Add user booking
        await insert_user(message.from_user.id, data["message_id"], data["chat_id"], message.from_user.username,
                          message.text)

        # Get text of task message
        old_text = await get_task(data['chat_id'], data['message_id'])
        # Update message
        await bot.edit_message_text(chat_id=data["chat_id"], message_id=data["message_id"],
                                    text=f'{old_text[1]}\n{message.from_user.username} - {message.text}',
                                    reply_markup=keyboard)
    await state.finish()


@dp.callback_query_handler(Text(equals="Обсудить"), user_id=ADMIN)
async def handle_discuss(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    users_list = await get_users_list(callback_query.message.chat.id, callback_query.message.message_id)
    keyboard = InlineKeyboardMarkup(resize_keyboard=True, row_width=3)
    button_list = [[InlineKeyboardButton(text=f"{x[0]}, принять", callback_data=f"accept {x[0]}"),
                    InlineKeyboardButton(text="Отклонить", callback_data=f"reject {x[0]}"),
                    InlineKeyboardButton(text="Варн", callback_data=f"warning {x[0]}")] for x in users_list]

    final_list = []
    for button in button_list:
        final_list += button

    keyboard.add(*final_list)
    await dp.bot.send_message(chat_id=callback_query.from_user.id, text="Список пользователей:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: re.match(r"(accept|reject|warning) (.*?)", c.data), user_id=ADMIN)
async def handle_user(callback_query: types.CallbackQuery, state: FSMContext):
    command, user = callback_query.data.split(" ", 1)
    if command == "accept":
        await callback_query.answer(f"Заявка {user} принята")
        await dp.bot.send_message(chat_id=user, text="Ваша заявка была принята")
    elif command == "reject":
        await callback_query.answer(f"Заявка {user} отклонена")
        await dp.bot.send_message(user, "Ваша заявка была отклонена")
    elif command == "warning":
        await blacklist_add(user)
        await callback_query.answer(f"Пользователю {user} отправлено предупреждение")
        await dp.bot.send_message(user,
                                  "Вам было выслано предупреждение, вы не сможете участвовать в следующем тендере")


def main():
    logger.success("Start")
    try:
        executor.start_polling(dp, on_startup=on_startup)
    except Exception as err:
        logger.exception("Error:", err)
        asyncio.sleep(5)
        loop.create_task(main())


if __name__ == "__main__":
    loop.create_task(main())
    loop.run_forever()
