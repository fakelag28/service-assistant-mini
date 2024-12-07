import g4f
import requests
import time
import json
import base64
import mysql.connector
from g4f.client import AsyncClient
import logging
import asyncio
from datetime import date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    InlineQueryHandler,
    filters,
    CallbackQueryHandler,
)
from telegram.constants import ChatAction
from uuid import uuid4

# Настройки логгера
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

TOKEN = "" # Токен телеграмм бота

gemini_api_key = "" # API ключ для работы с Gemini

active_requests = {} # Словарь для хранения активных запросов

# Список доступных моделей
MODELS = {
    "gemini-1.5-flash": {
        "name": "Gemini 1.5 Flash",
        "desc": "Высококвалифицированная нейросеть с самым быстрым ответом",
        "limit_of_day": 1500,
        "max_context_tokens": 8192,
    },
    "gemini-1.5-pro": {
        "name": "Gemini 1.5 Pro",
        "desc": "Высококвалифицированная нейросеть для лучших текстовых ответов",
        "limit_of_day": 50,
        "max_context_tokens": 8192,
    },
    "gemini-pro": {
        "name": "Gemini 1.0 Pro",
        "desc": "Высококлассная нейросеть с умеренной быстротой и хорошими способностями",
        "limit_of_day": "Нет",
        "max_context_tokens": 8192,
    },
    "claude-sonnet-3.5": {
        "name": "Claude Sonnet 3.5",
        "desc": "Высококлассная нейросеть с умеренной быстротой и хорошими способностями",
        "limit_of_day": "Нет",
        "max_context_tokens": 8192,
    },
    "gpt-4o": {
        "name": "GPT 4o",
        "desc": "Высококлассная нейросеть с умеренной быстротой и хорошими способностями",
        "limit_of_day": "Нет",
        "max_context_tokens": 8192,
    },
    "gpt-4o-mini": {
        "name": "GPT 4o mini",
        "desc": "Предлагает доступное, но менее продвинутое решение чем GPT-4o",
        "limit_of_day": "Нет",
        "max_context_tokens": 8192,
    },
}

# Конфигурация базы данных
db_config = {
    "host": "",
    "user": "",
    "password": "",
    "database": "",
}

# Функция для получения данных из базы данных
def get_db_connection():
    return mysql.connector.connect(**db_config)

def limit_context_of_model(model):
    for model_key, model_data in MODELS.items():
        if model_key == model:
            return model_data['max_context_tokens']
        
def limit_of_day_of_model(model):
    for model_key, model_data in MODELS.items():
        if model_key == model:
            return model_data['limit_of_day']

def format_text(model, type, response, all_time, tokens_used=None, limit_of_user_model=None):
    if not tokens_used == None:
        tokens_text = f'*📂 | Занято {tokens_used} контекстного окна из {limit_of_user_model}*\n'
    else: tokens_text = ''
    text = (
        f"*💬 | Ответ от нейросети {model}:*\n\n"
        f"{response}\n\n"
        f"*📌 | Тип запроса: {type}*\n"
        f"*🕑 | {all_time:.2f} секунд*\n"
        f"{tokens_text}"
        f"*🔻 | Для возврата в меню используйте /start*"
    )
    return text

def format_image(model, all_time):
    text = (
        f"*💬 | Изображение, сгенерированное нейросетью {model}*\n"
        f"*📌 | Тип запроса: Генерация изображения (/img)*\n"
        f"*🕑 | {all_time:.2f} секунд*\n"
        f"*🔻 | Для возврата в меню используйте /start*"
    )
    return text

def get_user_model_text(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT model_text FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        cursor.close()
        conn.close()


def get_user_model_vision(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT model_vision FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        cursor.close()
        conn.close()


def get_user_model_image(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT model_image FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        cursor.close()
        conn.close()


def save_message(user_id, message, is_user_message):
    if user_id:
        ensure_user_exists(user_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "INSERT INTO chats (user_id, message, is_user_message) VALUES (%s, %s, %s)"
    cursor.execute(query, (user_id, message, is_user_message))
    conn.commit()
    cursor.close()
    conn.close()


def delete_messages(user_id):
    if user_id:
        ensure_user_exists(user_id)
    logging.info(f"Попытка удалить сообщения для user_id: {user_id}")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = "DELETE FROM chats WHERE user_id = %s"
        cursor.execute(query, (user_id,))
        conn.commit()
        logging.info("Сообщения успешно удалены")
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка при удалении сообщений: {str(e)}")


def get_chat_history(user_id, limit):
    if user_id:
        ensure_user_exists(user_id)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = "SELECT message, is_user_message FROM chats WHERE user_id = %s ORDER BY timestamp DESC"
    cursor.execute(query, (user_id,))
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    
    history = history[::-1]
    
    total_chars = sum(len(entry['message']) for entry in history)
    
    while total_chars > limit and history:
        removed_message = history.pop(0)
        total_chars -= len(removed_message['message'])

    return history, total_chars

def get_usage_limit_model(network_name):
    if network_name.find('gemini-1.5'):
        return 1000
    reset_value = limit_of_day_of_model(network_name)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT usage_count, last_used FROM neural_network_limits WHERE network_name = %s", (network_name,))
    result = cursor.fetchone()
    
    if result:
        usage_count, last_used = result
        if date.today() - last_used > timedelta(days=1):
            cursor.execute("UPDATE neural_network_limits SET usage_count = %s, last_used = %s WHERE network_name = %s", (reset_value, date.today(), network_name))
            conn.commit()
            return reset_value
        else:
            return usage_count
    else:
        cursor.execute("INSERT INTO neural_network_limits (network_name, usage_count, last_used) VALUES (%s, %s, %s)", (network_name, reset_value, date.today()))
        conn.commit()
        return reset_value
    
def decrease_usage(network_name):
    if network_name.find('gemini-1.5'):
        return
    mydb = get_db_connection()
    cursor = mydb.cursor()
    cursor.execute("UPDATE neural_network_limits SET usage_count = usage_count - 1 WHERE network_name = %s", (network_name,))
    mydb.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
    else:
        user_id = update.effective_user.id
    if user_id:
        ensure_user_exists(user_id)
    reply_markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔗 | Сменить модель", callback_data="models")],
            [InlineKeyboardButton("🛠 | Инструменты", callback_data="tools")],
            [
                InlineKeyboardButton(
                    "❌ | Завершить текущий чат", callback_data="end_chat"
                )
            ],
        ]
    )
    text = (
        f"*👤 | Профиль пользователя @{update.effective_user.username}:*\n"
        f"*📝 | Модель для текста: {get_user_model_text(user_id)}*\n"
        f"*👀 | Модель распознования изображений: {get_user_model_vision(user_id)}*\n"
        f"*🖼 | Модель генерации изображений: {get_user_model_image(user_id)}*\n\n"
        f"*♦️ | Дневные лимиты на всех пользователей:*\n"
        f"*Gemini 1.5 Pro: {get_usage_limit_model('gemini-1.5-pro')}/{limit_of_day_of_model('gemini-1.5-pro')}*\n"
        f"*Gemini 1.5 Flash: {get_usage_limit_model('gemini-1.5-flash')}/{limit_of_day_of_model('gemini-1.5-flash')}*"
    )
    if not update.callback_query:
        await update.message.reply_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )


async def exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_requests[user_id] = "exam"
    await update.message.reply_text(
        "Ожидаю отправки изображения теста. Введите /cancel, если хотите отменить."
    )

async def img(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_requests[user_id] = "img"
    await update.message.reply_text(
        "Ожидаю отправки промта для генерации изображения. Введите /cancel, если хотите отменить."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_requests:
        del active_requests[user_id]
        await update.message.reply_text("Запрос отменён.")
    else:
        await update.message.reply_text("У вас нет активных запросов.")


async def choose_model_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Обязательно отвечаем на callback

    user_id = query.from_user.id  # Используем данные пользователя из CallbackQuery

    # Получаем текущую модель пользователя из базы данных
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT model_text FROM users WHERE user_id = %s", (user_id,))
    user_data = cursor.fetchone()
    current_model = user_data[0] if user_data else None
    cursor.close()
    conn.close()

    # Создание клавиатуры с выбором моделей
    keyboard = []
    for model_key in MODELS.keys():
        # Если это выбранная модель, добавляем галочку
        button_text = f"✅ | {model_key}" if model_key == current_model else model_key
        keyboard.append(
            [InlineKeyboardButton(button_text, callback_data=f"model_{model_key}")]
        )

    keyboard.append(
        [InlineKeyboardButton("🔻 | Вернуться в меню", callback_data=f"menu")]
    )

    models_info = []
    for model_key, model_data in MODELS.items():
        model_string = (
            f"*{model_data['name']}:* {model_data['desc']}\n"
            f"Дневной лимит на запросы от всех пользователей: {model_data['limit_of_day']}\n"
            f"Максимальный контекст: {model_data['max_context_tokens']}\n\n"
        )
        models_info.append(model_string)

    # Отправляем обновленный текст в сообщении, вызвавшем CallbackQuery
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text="📌 Выберите модель для использования:\n" + "".join(models_info),
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def set_model(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    model = query.data.split("_")[1]  # Получаем выбранную модель

    # Обновление модели пользователя в базе данных
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET model_text = %s WHERE user_id = %s", (model, user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Создание обновленной клавиатуры
    keyboard = []
    for model_key in MODELS.keys():
        # Если это выбранная модель, добавляем галочку
        button_text = f"✅ | {model_key}" if model_key == model else model_key
        keyboard.append(
            [InlineKeyboardButton(button_text, callback_data=f"model_{model_key}")]
        )

    keyboard.append(
        [InlineKeyboardButton("🔻 | Вернуться в меню", callback_data=f"menu")]
    )

    models_info = []
    for model_key, model_data in MODELS.items():
        model_string = (
            f"*{model_data['name']}:* {model_data['desc']}\n"
            f"Дневной лимит на запросы от всех пользователей: {model_data['limit_of_day']}\n"
            f"Максимальный контекст: {model_data['max_context_tokens']}\n\n"
        )
        models_info.append(model_string)

    # Обновляем сообщение
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📌 Выберите модель для использования:\n" + "".join(models_info),
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id in active_requests:
        if active_requests[user_id] == 'img':
            await handle_img_gen(update, context)
            return
        else:
            await update.message.reply_text(
                "Пожалуйста, подождите, пока я обработаю ваш предыдущий запрос (handle_text)."
            )
            return

    if int(get_usage_limit_model(get_user_model_text(user_id))) < 1:
        await update.message.reply_text(
            f"Текущий глобальный дневной лимит использования нейросети {get_user_model_text(user_id)} исчерпан!"
        )
        return

    active_requests[user_id] = "text"

    user_input = update.message.text
    save_message(user_id, user_input, True)

    processing_message = await update.message.reply_text(
        "_Ваш запрос (Text) обрабатывается..._", parse_mode="Markdown"
    )

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    response_text, response_no_format = await process_text(user_input, user_id)

    await context.bot.delete_message(
        chat_id=chat_id, message_id=processing_message.message_id
    )

    if response_text and response_text.find("При обработке запроса произошла ошибка!"):
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ | Завершить чат", callback_data="end_chat")]]
        )
        await update.message.reply_text(
            response_text, parse_mode="Markdown", reply_markup=reply_markup
        )
        save_message(user_id, response_no_format, False)
    else:
        await update.message.reply_text(response_text, parse_mode="Markdown")

    del active_requests[user_id]

async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    
    try:
        if not query:
            return
        
        response_text = (
            '- @'
            + query.from_user.username
            + ': "'
            + query.query
            + '"\n\n- ИИ: "'
            + await process_text_inline_mode(query.query, query.from_user.id)
            + '"'
        )

        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="Результат",
                description=str(response_text),
                input_message_content=InputTextMessageContent(message_text=str(response_text))
            )
        ]

        await update.inline_query.answer(results)

    except asyncio.TimeoutError:
        await context.bot.answer_inline_query(
            inline_query_id=query.id,
            results=[],
            cache_time=0
        )
    except Exception as e:
        logging.error(f"Inline query error: {e}")
        await context.bot.answer_inline_query(
            inline_query_id=query.id,
            results=[],
            cache_time=0
        )


async def process_text(user_input: str, user_id: int) -> str:
    type_request = "Текстовый"
    try:
        start_time = time.time()
        client = AsyncClient()

        user_model = get_user_model_text(user_id)
        limit_of_user_model = limit_context_of_model(user_model)

        chat_history, tokens_used = get_chat_history(user_id, limit_of_user_model)
        messages = [
            {
                "role": "system",
                "content": "Ты — экспертный помощник, предоставляющий качественные и лаконичные ответы.\n"
                + "1. Если пользователь не указывает длину ответа, дай краткий и ясный ответ (не более 3 предложений).\n"
                + "2. Если пользователь просит конкретную длину, соблюдай это требование.\n"
                + "3. НЕ Форматируй ответ под какой-либо стиль: отвечай исключительно обычным текстом без форматирования.",
            }
        ]

        for msg in chat_history:
            role = "user" if msg["is_user_message"] else "assistant"
            messages.append({"role": role, "content": msg["message"]})

        messages.append({"role": "user", "content": user_input})

        if not user_model.find("gemini-1.5"):
            headers = {
                "Authorization": f"Bearer {gemini_api_key}",
                "Content-Type": "application/json",
            }
            data = {"model": user_model, "messages": messages}
            try:
                response = requests.post(
                    "https://my-openai-gemini-demo.vercel.app/v1/chat/completions",
                    timeout=15,
                    headers=headers,
                    data=json.dumps(data),
                )
            except requests.exceptions.Timeout:
                print("Timed out")
            else:
                if response.status_code == 200:
                    result = response.json()["choices"][0]["message"]["content"].strip()
        else:
            response = await client.chat.completions.create(
                model=user_model,
                provider=g4f.Provider.Blackbox,
                messages=messages,
            )
            result = response.choices[0].message.content
        end_time = time.time()
        decrease_usage(user_model)
        return (
            format_text(
                user_model,
                type_request,
                result,
                end_time - start_time,
                tokens_used,
                limit_of_user_model
            ),
            result,
        )
    except Exception as e:
        return f"При обработке запроса произошла ошибка!\n```\n{str(e)}\n```", ""
    
async def process_text_inline_mode(user_input: str, user_id: int) -> str:
    try:
        start_time = time.time()
        client = AsyncClient()

        user_model = "gemini-1.5-flash"
        limit_of_user_model = limit_context_of_model(user_model)

        chat_history, tokens_used = get_chat_history(user_id, limit_of_user_model)
        messages = [
            {
                "role": "system",
                "content": "Ты — экспертный помощник, предоставляющий качественные и очень краткие ответы.\n"
                + "1. Отвечай очень-очень кратко.\n"
                + "2. Если возможно сокращай ответ под 1-2 предложения.\n"
                + "3. НЕ Форматируй ответ под какой-либо стиль: отвечай исключительно обычным текстом без форматирования.",
            }
        ]

        for msg in chat_history:
            role = "user" if msg["is_user_message"] else "assistant"
            messages.append({"role": role, "content": msg["message"]})

        messages.append({"role": "user", "content": user_input})

        if not user_model.find("gemini-1.5"):
            headers = {
                "Authorization": f"Bearer {gemini_api_key}",
                "Content-Type": "application/json",
            }
            data = {"model": user_model, "messages": messages}
            try:
                response = requests.post(
                    "https://my-openai-gemini-demo.vercel.app/v1/chat/completions",
                    timeout=15,
                    headers=headers,
                    data=json.dumps(data),
                )
            except requests.exceptions.Timeout:
                print("Timed out")
            else:
                if response.status_code == 200:
                    result = response.json()["choices"][0]["message"]["content"].strip()
        else:
            response = await client.chat.completions.create(
                model=user_model,
                provider=g4f.Provider.Blackbox,
                messages=messages,
            )
            result = response.choices[0].message.content
        end_time = time.time()
        decrease_usage(user_model)
        return result
    except Exception as e:
        return f"При обработке запроса произошла ошибка!\n```\n{str(e)}\n```", ""

async def handle_img_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    active_requests[user_id] = "img"

    user_input = update.message.text

    processing_message = await update.message.reply_text(
        "_Ваш запрос (/img) обрабатывается..._", parse_mode="Markdown"
    )

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    response_text, image_url = await process_image_with_flux(user_input)
    image_data = base64.b64decode(image_url)

    with open("generated_image.png", "wb") as image_file:
        image_file.write(image_data)

    await context.bot.delete_message(
        chat_id=chat_id, message_id=processing_message.message_id
    )

    if response_text and response_text.find("При обработке запроса произошла ошибка!"):
        if not image_url == 'error':
            await update.message.reply_text(
                response_text, parse_mode="Markdown"
            )
            await update.message.reply_photo(open("generated_image.png", 'rb'))
        else:
            await update.message.reply_text(response_text, parse_mode="Markdown")
    else:
        await update.message.reply_text(response_text, parse_mode="Markdown")

    del active_requests[user_id]

async def process_image_with_flux(promt_image: str) -> str:
    try:
        client = AsyncClient()

        # Этап 1: Загрузка изображения
        start_time = time.time()
        
        response = await client.images.generate(
            prompt=promt_image,
            model="flux-4o",
            response_format="b64_json"
        )

        end_time = time.time()

        return format_image(
            "flux",
            end_time - start_time,
        ), response.data[0].b64_json

    except Exception as e:
        return "При обработке произошла ошибка!\n```\n" + str(e) + "\n```", 'error'

async def end_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    try:
        delete_messages(user_id)
        if user_id in active_requests:
            del active_requests[user_id]

        await query.message.reply_text(
            "Чат завершен. История очищена. Для возврата в меню используйте /start"
        )
    except Exception as e:
        await query.message.reply_text("Не удалось завершить чат из-за ошибки.")
        await query.message.reply_text(e)


async def models(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await choose_model_handler(update, context)


async def menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await start(update, context)


async def tools(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    text = (
        "*🛠 | Инструменты Service Assistant* - специальные режимы обработки текста/изображений, которые дают возможность"
        " пользователю легко и просто выполнять сложную работу с нейросетями.\n\n"
        "*📜 | Текущий список инструментов (Для использования нажмите на команду):*\n"
        "*/exam* - позволяет получить текстовый ответ на школьный тест по изображению. Рекомендуется использование "
        "исключительно на обществоведческих предметах (История, биология, обществознание, ОБЖ и прочие)\n"
        "*/img* - генерация изображений на основе заданного вами промта"
    )

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔻 | Вернуться в меню", callback_data=f"menu")]]
    )

    await query.edit_message_text(
        text, reply_markup=reply_markup, parse_mode="Markdown"
    )


async def handle_mixed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений с текстом и изображением"""
    user_id = update.effective_user.id

    # Проверяем активный запрос
    if user_id in active_requests:
        await update.message.reply_text(
            "Пожалуйста, подождите, пока я обработаю ваш предыдущий запрос (handle_mixed)."
        )
        return

    active_requests[user_id] = "image"

    # Получаем текст и фото
    user_input = update.message.caption or ""
    photo_file = await update.message.photo[-1].get_file()
    image_url = photo_file.file_path

    user_input_model = "Text+" if user_input else ""

    processing_message = await update.message.reply_text(
        "_Ваш запрос (" + user_input_model + "Image) обрабатывается..._",
        parse_mode="Markdown",
    )

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    # Обработка текста и изображения через нейросеть
    response_text = await process_image_and_text(image_url, user_input)

    await context.bot.delete_message(
        chat_id=update.effective_chat.id, message_id=processing_message.message_id
    )

    if response_text:
        await update.message.reply_text(response_text, parse_mode="Markdown")
    else:
        await update.message.reply_text("Произошла ошибка при обработке запроса.")

    del active_requests[user_id]


async def process_image_and_text(image_url: str, text: str) -> str:
    """Обработка изображения и текста через нейросеть"""
    type_request_text = " с текстовым запросом" if text else ""
    type_request = "Изображение" + type_request_text
    try:
        start_time = time.time()
        client = AsyncClient()
        image = requests.get(image_url, stream=True).raw
        # Анализ изображения
        response_1 = await client.chat.completions.create(
            model=g4f.models.default,
            provider=g4f.Provider.Blackbox,
            messages=[
                {
                    "role": "system",
                    "content": "Ты — умный анализатор изображений. Твоя задача:\n"
                    + "1. Если предоставлено изображение, сначала подробно его опиши. Укажи цвета, формы, текстуры, что изображено, и любые другие детали.\n"
                    + "2. Если с изображением был передан вопрос или просьба, обработай его в контексте изображения и дай понятный ответ. Если вопроса или просьбы нет, просто предоставь описание.\n"
                    + "3. НЕ Форматируй ответ под какой-либо стиль: отвечай исключительно обычным текстом без форматирования.\n",
                },
                {
                    "role": "user",
                    "content": text if text else "Опиши изображение или текст с него",
                },
            ],
            image=image,
        )

        response_2 = await client.chat.completions.create(
            model=g4f.models.default,
            provider=g4f.Provider.Blackbox,
            messages=[
                {
                    "role": "system",
                    "content": "Ты — экспертный переводчик, выполняющий перевод текста с английского на русский.\n"
                    + "1. Убери любое форматирование, включая символы разметки, такие как **жирный текст**, *курсив*, заголовки, списки и другие элементы.\n"
                    + "2. Твой ответ должен быть простым текстом на русском языке, без каких-либо специальных символов или структурирования.\n"
                    + "3. Сохраняй смысл и контекст оригинального текста.",
                },
                {
                    "role": "user",
                    "content": "Переведи ответ нейросети на русский язык и удали форматирование из ответа:\n"
                    + response_1.choices[0].message.content,
                },
            ],
        )
        end_time = time.time()
        return format_text(
            "gemini-pro | gpt-4o",
            type_request,
            response_2.choices[0].message.content,
            end_time - start_time,
        )

    except Exception as e:
        return f"Произошла ошибка при обработке запроса: {str(e)}"


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка изображения, отправленного пользователем"""
    user_id = update.effective_user.id

    # Проверяем активный запрос
    if not user_id in active_requests:
        await handle_mixed(update, context)
        # await update.message.reply_text("Сначала используйте команду /exam.")
        return

    # Получаем ссылку на изображение
    photo_file = await update.message.photo[-1].get_file()
    image_url = photo_file.file_path

    # Уведомление пользователя
    processing_message = await update.message.reply_text(
        "_Ваш запрос (/exam) обрабатывается..._", parse_mode="Markdown"
    )

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    # Отправляем запрос к GPT-4o
    response_text = await process_exams_with_gpt4o(image_url)

    # Удаляем сообщение "Вопросы обрабатываются..."
    await context.bot.delete_message(
        chat_id=update.effective_chat.id, message_id=processing_message.message_id
    )

    # Отправляем ответ от нейросети
    if response_text:
        await update.message.reply_text(response_text, parse_mode="Markdown")
    else:
        await update.message.reply_text("Произошла ошибка при обработке изображения.")

    # Завершаем активный запрос
    del active_requests[user_id]

async def process_exams_with_gpt4o(image_url: str) -> str:
    type_request = "Изображение с текстовым запросом (/exam)"
    try:
        client = AsyncClient()

        time_tracker = {}

        # Этап 1: Загрузка изображения
        start_time = time.time()
        image = requests.get(image_url, stream=True).raw
        end_time = time.time()
        time_tracker["Загрузка изображения"] = end_time - start_time

        # Этап 2: Извлечение текста с изображения
        start_time = time.time()
        response_1 = await client.chat.completions.create(
            model=g4f.models.default,
            provider=g4f.Provider.Blackbox,
            messages=[
                {
                    "role": "user",
                    "content": "Пожалуйста, проанализируй изображение, содержащее текст школьного теста. Извлеки весь текст с изображения и предоставь его в виде текста. Не говори ничего, просто выпиши текст с изображения теста. Пожалуйста, убедись, что текст извлечён максимально точно.",
                }
            ],
            image=image,
        )
        end_time = time.time()
        time_tracker["Извлечение текста с изображения"] = end_time - start_time

        # Этап 3: Анализ и редактирование текста
        start_time = time.time()
        response_2 = await client.chat.completions.create(
            model="gpt-4o",
            provider=g4f.Provider.Blackbox,
            messages=[
                {
                    "role": "system",
                    "content": "Ты — эксперт в анализе и редактировании текстов.",
                },
                {
                    "role": "user",
                    "content": "Вот текст теста:"
                    + response_1.choices[0].message.content
                    + "."
                    "Отредактируй его, сделай более читабельным, укажи предмет, к которому относится тест, "
                    "и верни результат в формате текста.",
                },
            ],
        )
        end_time = time.time()
        time_tracker["Анализ и редактирование текста"] = end_time - start_time

        question = response_2.choices[0].message.content

        # Этап 4: Обработка и решение вопросов
        start_time = time.time()
        response_3 = await client.chat.completions.create(
            model="gpt-4o",
            provider=g4f.Provider.Blackbox,
            messages=[
                {
                    "role": "system",
                    "content": "Ты высококвалифицированный учитель в школе, стаж твоей работы 80 лет.",
                },
                {
                    "role": "user",
                    "content": "Я тебе отправлю текст школьного теста, твоя задача решить его правильно.\n"
                    + "Тебе нужно решить правильно следующие задания из теста:\n"
                    + question
                    + "\nВ своём ответе предоставь исключительно верный ответ из предложенных или краткий ответ на поставленный вопрос."
                    + 'Предоставь ответ на русском языке в формате "1) Вопрос\n- Ответ\n2)Вопрос\n- Ответ\n'
                    + "Также убери любое форматирование текста, типо ### ** ** или любое другое.",
                },
            ],
        )
        end_time = time.time()
        time_tracker["Обработка и решение вопросов"] = end_time - start_time

        all_time_tracker = (
            time_tracker["Загрузка изображения"]
            + time_tracker["Извлечение текста с изображения"]
            + time_tracker["Анализ и редактирование текста"]
            + time_tracker["Обработка и решение вопросов"]
        )

        # Возвращаем финальный результат
        return format_text(
            "gemini-pro | gpt-4o",
            type_request,
            response_3.choices[0].message.content,
            all_time_tracker,
        )

    except Exception as e:
        return "При обработке произошла ошибка!\n```\n" + str(e) + "\n```"


def ensure_user_exists(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if user exists
    cursor.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
    if not cursor.fetchone():
        # User doesn't exist, create a new user
        cursor.execute(
            "INSERT INTO users (user_id, model_text, model_vision, model_image) VALUES (%s, %s, %s, %s)",
            (user_id, "gpt-4o", "gemini-pro", "flux"),
        )
        conn.commit()

    cursor.close()
    conn.close()


def main():
    """Основная функция для запуска бота"""
    application = ApplicationBuilder().token(TOKEN).concurrent_updates(True).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(CommandHandler("exam", exam))
    application.add_handler(CommandHandler("img", img))
    application.add_handler(CommandHandler("cancel", cancel))

    application.add_handler(CallbackQueryHandler(end_chat, pattern="end_chat"))
    application.add_handler(CallbackQueryHandler(set_model, pattern="^model_"))
    application.add_handler(CallbackQueryHandler(models, pattern="models"))
    application.add_handler(CallbackQueryHandler(tools, pattern="tools"))
    application.add_handler(CallbackQueryHandler(menu, pattern="menu"))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    application.add_handler(
        MessageHandler(filters.PHOTO & filters.CAPTION, handle_mixed)
    )

    # Обработчик фотографий
    application.add_handler(
        MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo)
    )

    application.add_handler(InlineQueryHandler(handle_inline_query))

    # Запуск бота
    application.run_polling()


if __name__ == "__main__":
    main()
