import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
from datetime import datetime, timedelta
import re
import json
from ai_functions import normalize_text_with_ai, categorize_expense, parse_free_text, generate_financial_insights

# --------------------------
# Хранилище данных (в памяти)
# --------------------------
transactions = []  # Каждая запись: {"description": str, "amount": float, "date": str, "timestamp": datetime, "category": str}
favorites = {}  # Формат: {"name": {"amount": float, "category": str}}

# Состояния для ConversationHandler
WAITING_FOR_FAVORITE_DESCRIPTION = 0
WAITING_FOR_FAVORITE_NAME = 1
WAITING_FOR_FAVORITE_AMOUNT = 2

# --------------------------
# Форматирование суммы
# --------------------------
def format_amount(amount):
    """Форматирует сумму без копеек и с валютой."""
    return f"{int(amount)} uzs"

# --------------------------
# Форматирование сообщения о транзакции
# --------------------------
def format_transaction_message(description: str, amount: float, category: str = "Другое") -> str:
    """
    Форматирует сообщение о добавлении транзакции в единый стиль.
    
    Пример:
    📉 Записано: Покупка кофе — 100 uzs [Еда]
    """
    emoji = "📈" if amount > 0 else "📉"
    category_text = f" [{category}]" if category != "Другое" else ""
    return f"{emoji} Записано: {description} — {format_amount(amount)}{category_text}"

# --------------------------
# Форматирование даты
# --------------------------
def format_date(date_str):
    """
    Преобразует дату из формата YYYY-MM-DD в формат DD month, YYYY
    Например: 2008-07-19 -> 19 july, 2008
    """
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    months = {
        1: "january", 2: "february", 3: "march", 4: "april",
        5: "may", 6: "june", 7: "july", 8: "august",
        9: "september", 10: "october", 11: "november", 12: "december"
    }
    month_name = months[date_obj.month]
    return f"{date_obj.day} {month_name}, {date_obj.year}"

# --------------------------
# Нормализация текста
# --------------------------
def normalize_description(text):
    """
    Простая функция нормализации.
    - Приводим к нижнему регистру
    """
    return text.lower()

# --------------------------
# Парсинг транзакции
# --------------------------
def parse_transaction(text):
    """
    Парсит сообщение в формате:
    - "coffee -25" (expense)
    - "+300 salary" (income)
    - "-100" (just amount)
    
    Возвращает: (description, amount) или None если ошибка
    """
    text = text.strip()
    
    # Ищем число со знаком + или - в начале или конце
    # Формат: "+300 mom" или "coffee -25" или "-100 food"
    
    # Попытка 1: формат "[описание] [+/-]число"
    match = re.search(r'([+-]?\d+\.?\d*)', text)
    if not match:
        return None
    
    amount_str = match.group(1)
    amount = float(amount_str)
    
    # Получаем описание (все кроме числа)
    description = text.replace(amount_str, "").strip()
    
    # Если описание пусто, используем "transaction"
    if not description:
        description = "transaction"
    
    return description, amount

# --------------------------
# Добавление транзакции (с ИИ)
# --------------------------
async def add_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # Игнорируем команды
    if text.startswith("/"):
        return
    
    # Проверяем, является ли это избранным транзакцией
    if text.lower() in favorites:
        favorite = favorites[text.lower()]
        amount = favorite["amount"]
        category = favorite["category"]
        normalized = text.lower()
        
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        
        transactions.append({
            "description": normalized,
            "amount": amount,
            "date": date_str,
            "timestamp": now,
            "category": category
        })
        
        msg = format_transaction_message(normalized, amount, category)
        await update.message.reply_text(msg)
        return

    try:
        # Пытаемся распарсить со старой функцией
        result = parse_transaction(text)
        if result is None:
            # Если не получилось, пробуем ИИ парсинг
            ai_result = await parse_free_text(text)
            if not ai_result["success"]:
                await update.message.reply_text("❌ Не смог определить сумму. Используй формат:\n"
                                               "• coffee -25\n"
                                               "• +300 salary\n"
                                               "• -50")
                return
            description = ai_result["description"]
            amount = ai_result["amount"]
        else:
            description, amount = result
        
        # Нормализуем описание через ИИ
        normalized = await normalize_text_with_ai(description)
        
        # Определяем категорию через ИИ
        category = await categorize_expense(normalized, amount)
        
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        
        transactions.append({
            "description": normalized,
            "amount": amount,
            "date": date_str,
            "timestamp": now,
            "category": category
        })
        
        msg = format_transaction_message(normalized, amount, category)
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при добавлении: {e}")

# --------------------------
# Удалить последнюю транзакцию
# --------------------------
async def undo_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not transactions:
        await update.message.reply_text("❌ Нет транзакций для удаления.")
        return
    
    removed = transactions.pop()
    category = removed.get("category", "Другое")
    msg = format_transaction_message(removed['description'], removed['amount'], category)
    await update.message.reply_text(f"✅ Удалена транзакция:\n{msg}")

# --------------------------
# Показ баланса
# --------------------------
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not transactions:
        await update.message.reply_text("💰 Баланс: 0 uzs\n(нет транзакций)")
        return
    
    balance = sum(t["amount"] for t in transactions)
    income = sum(t["amount"] for t in transactions if t["amount"] > 0)
    expenses = sum(t["amount"] for t in transactions if t["amount"] < 0)
    
    await update.message.reply_text(
        f"💰 <b>Баланс</b>: {format_amount(balance)}\n"
        f"📈 <b>Доход</b>: {format_amount(income)}\n"
        f"📉 <b>Расходы</b>: {format_amount(expenses)}",
        parse_mode="HTML"
    )

# --------------------------
# Показ истории
# --------------------------
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not transactions:
        await update.message.reply_text("📋 История пуста.")
        return
    
    # Ограничиваем 150 последними транзакциями
    limited_transactions = transactions[-150:]
    
    lines = []
    for i, t in enumerate(limited_transactions, 1):
        emoji = "➕" if t["amount"] > 0 else "➖"
        formatted_date = format_date(t['date'])
        lines.append(f"{i}. {emoji} {t['description']}: {format_amount(t['amount'])} — {formatted_date}")
    
    history_text = "\n".join(lines)
    total_trans = len(transactions)
    note = f"\n\n(показано последних 150 из {total_trans})" if total_trans > 150 else ""
    await update.message.reply_text(f"📋 <b>История транзакций</b>:\n\n{history_text}{note}", parse_mode="HTML")

# --------------------------
# Показ транзакций за сегодня
# --------------------------
async def show_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    today_transactions = [t for t in transactions if t["date"] == today]
    
    if not today_transactions:
        await update.message.reply_text("📅 Транзакций за сегодня нет.")
        return
    
    lines = []
    for i, t in enumerate(today_transactions, 1):
        emoji = "➕" if t["amount"] > 0 else "➖"
        time_str = t["timestamp"].strftime("%H:%M")
        lines.append(f"{i}. {emoji} {t['description']}: {format_amount(t['amount'])} — {time_str}")
    
    day_balance = sum(t["amount"] for t in today_transactions)
    day_income = sum(t["amount"] for t in today_transactions if t["amount"] > 0)
    day_expenses = sum(t["amount"] for t in today_transactions if t["amount"] < 0)
    
    day_text = "\n".join(lines)
    await update.message.reply_text(
        f"📅 <b>Транзакции за сегодня</b>:\n\n{day_text}\n\n"
        f"<b>Баланс</b>: {format_amount(day_balance)}\n"
        f"<b>Доход</b>: {format_amount(day_income)}\n"
        f"<b>Расходы</b>: {format_amount(day_expenses)}",
        parse_mode="HTML"
    )

# --------------------------
# Показ транзакций за неделю
# --------------------------
async def show_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now()
    week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    
    week_transactions = [t for t in transactions if t["date"] >= week_ago]
    
    if not week_transactions:
        await update.message.reply_text("📊 Транзакций за неделю нет.")
        return
    
    lines = []
    for i, t in enumerate(week_transactions, 1):
        emoji = "➕" if t["amount"] > 0 else "➖"
        formatted_date = format_date(t['date'])
        lines.append(f"{i}. {emoji} {t['description']}: {format_amount(t['amount'])} — {formatted_date}")
    
    week_balance = sum(t["amount"] for t in week_transactions)
    week_income = sum(t["amount"] for t in week_transactions if t["amount"] > 0)
    week_expenses = sum(t["amount"] for t in week_transactions if t["amount"] < 0)
    
    week_text = "\n".join(lines)
    await update.message.reply_text(
        f"📊 <b>Транзакции за неделю</b>:\n\n{week_text}\n\n"
        f"<b>Баланс</b>: {format_amount(week_balance)}\n"
        f"<b>Доход</b>: {format_amount(week_income)}\n"
        f"<b>Расходы</b>: {format_amount(week_expenses)}",
        parse_mode="HTML"
    )

# --------------------------
# Показ транзакций за две недели
# --------------------------
async def show_two_weeks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now()
    two_weeks_ago = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    
    two_weeks_transactions = [t for t in transactions if t["date"] >= two_weeks_ago]
    
    if not two_weeks_transactions:
        await update.message.reply_text("📈 Транзакций за две недели нет.")
        return
    
    lines = []
    for i, t in enumerate(two_weeks_transactions, 1):
        emoji = "➕" if t["amount"] > 0 else "➖"
        formatted_date = format_date(t['date'])
        lines.append(f"{i}. {emoji} {t['description']}: {format_amount(t['amount'])} — {formatted_date}")
    
    two_weeks_balance = sum(t["amount"] for t in two_weeks_transactions)
    two_weeks_income = sum(t["amount"] for t in two_weeks_transactions if t["amount"] > 0)
    two_weeks_expenses = sum(t["amount"] for t in two_weeks_transactions if t["amount"] < 0)
    
    two_weeks_text = "\n".join(lines)
    await update.message.reply_text(
        f"📈 <b>Транзакции за две недели</b>:\n\n{two_weeks_text}\n\n"
        f"<b>Баланс</b>: {format_amount(two_weeks_balance)}\n"
        f"<b>Доход</b>: {format_amount(two_weeks_income)}\n"
        f"<b>Расходы</b>: {format_amount(two_weeks_expenses)}",
        parse_mode="HTML"
    )

# --------------------------
# Показ транзакций за месяц
# --------------------------
async def show_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now()
    month_ago = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    
    month_transactions = [t for t in transactions if t["date"] >= month_ago]
    
    if not month_transactions:
        await update.message.reply_text("📅 Транзакций за месяц нет.")
        return
    
    lines = []
    for i, t in enumerate(month_transactions, 1):
        emoji = "➕" if t["amount"] > 0 else "➖"
        formatted_date = format_date(t['date'])
        lines.append(f"{i}. {emoji} {t['description']}: {format_amount(t['amount'])} — {formatted_date}")
    
    month_balance = sum(t["amount"] for t in month_transactions)
    month_income = sum(t["amount"] for t in month_transactions if t["amount"] > 0)
    month_expenses = sum(t["amount"] for t in month_transactions if t["amount"] < 0)
    
    month_text = "\n".join(lines)
    await update.message.reply_text(
        f"📅 <b>Транзакции за месяц (30 дней)</b>:\n\n{month_text}\n\n"
        f"<b>Баланс</b>: {format_amount(month_balance)}\n"
        f"<b>Доход</b>: {format_amount(month_income)}\n"
        f"<b>Расходы</b>: {format_amount(month_expenses)}",
        parse_mode="HTML"
    )

# --------------------------
# Анализ расходов по категориям (ИИ)
# --------------------------
async def analyze_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализирует расходы по категориям"""
    if not transactions:
        await update.message.reply_text("📊 Нет транзакций для анализа.")
        return
    
    # Подготавливаем данные по категориям
    categories_summary = {}
    total_spent = 0
    
    for t in transactions:
        category = t.get("category", "Другое")
        amount = t["amount"]
        
        if amount < 0:  # Только расходы
            if category not in categories_summary:
                categories_summary[category] = 0
            categories_summary[category] += abs(amount)
            total_spent += abs(amount)
    
    if not categories_summary:
        await update.message.reply_text("📊 Нет расходов для анализа.")
        return
    
    # Создаем текст для отправки
    lines = []
    for category, amount in sorted(categories_summary.items(), key=lambda x: x[1], reverse=True):
        percentage = (amount / total_spent * 100) if total_spent > 0 else 0
        lines.append(f"  <b>{category}</b>: {format_amount(-amount)} ({percentage:.1f}%)")
    
    summary_text = "📊 <b>Расходы по категориям (ИИ)</b>:\n\n" + "\n".join(lines)
    summary_text += f"\n\n<b>Всего расходов</b>: {format_amount(-total_spent)}"
    
    await update.message.reply_text(summary_text, parse_mode="HTML")

# --------------------------
# Умные финансовые инсайты (ИИ)
# --------------------------
async def insights_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерирует финансовые инсайты"""
    if not transactions:
        await update.message.reply_text("📊 Нет данных для анализа.")
        return
    
    await update.message.reply_text("⏳ Анализирую твои финансы...")
    
    insights = await generate_financial_insights(transactions, period_days=30)
    
    await update.message.reply_text(
        f"💡 <b>Финансовые инсайты (30 дней)</b>:\n\n{insights}",
        parse_mode="HTML"
    )

# --------------------------
# Приветствие и справка
# --------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🤖 <b>Добро пожаловать в Personal Finance Bot!</b>

Это простой бот для отслеживания своих доходов и расходов.

<b>📚 ФУНКЦИИ БОТА:</b>

📝 <b>Добавить транзакцию</b>
Просто напиши: <code>кофе -100</code> или <code>+5000 зарплата</code>
• Знак <b>+</b> = доход (деньги пришли)
• Знак <b>-</b> = расход (потратил)

💰 <b>/balance</b> - Показать баланс
Видишь: общий баланс, общий доход, общие расходы

📋 <b>/history</b> - Вся история транзакций
Последние 150 операций

📅 <b>/day</b> - Транзакции за сегодня
Только сегодняшние операции с временем

📊 <b>/week</b> - Отчёт за неделю + статистика

📈 <b>/two_weeks</b> - Отчёт за две недели + статистика

📅 <b>/month</b> - Отчёт за месяц + статистика

📊 <b>/analyze</b> - Анализ расходов по категориям (ИИ)
Видишь как распределены твои расходы

 <b>/insights</b> - Умные финансовые инсайты (ИИ)
Анализ и рекомендации по твоим расходам

↩️  <b>/undo</b> - Удалить последнюю транзакцию
Если ошибся - просто удаляем последнюю операцию

⭐ <b>/add_favorite</b> - Сохрани часто используемые операции
Например: кофе -100, такси -50

⭐ <b>/favorites</b> - Посмотреть все избранные

❓ <b>/help</b> - Справка и примеры

<b>💡 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ:</b>
кофе -100
бензин -250
+10000 зарплата
обед -500
такси -50
подарок +500

<b>Начни с отправки любой операции!</b>
Например: <code>кофе -50</code>
"""
    await update.message.reply_text(welcome_text, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 <b>Справка по командам</b>

<b>📝 Добавить транзакцию:</b>
Отправь сообщение в формате:
<code>кофе -100</code> или <code>+5000 зарплата</code>

<b>💰 /balance</b> - Текущий баланс и статистика

<b>📋 /history</b> - История всех транзакций (последние 150)

<b>📅 /day</b> - Транзакции за сегодня

<b>� История за конкретный день:</b>
Просто отправь дату в формате <code>DD/MM/YYYY</code>
Например: <code>19/07/2008</code>
Бот покажет историю за этот день

<b>�📊 /week</b> - Транзакции за неделю + статистика

<b>📈 /two_weeks</b> - Транзакции за две недели + статистика

<b>📅 /month</b> - Транзакции за месяц + статистика

<b>📊 /analyze</b> - Анализ расходов по категориям (с ИИ)
Показывает распределение расходов по категориям с процентами

<b> /insights</b> - Умные финансовые инсайты (ИИ)
Анализирует твои расходы и дает рекомендации

<b>↩️  /undo</b> - Удалить последнюю транзакцию

<b>⭐ /add_favorite</b> - Добавить избранную транзакцию
Сохраняй часто повторяющиеся операции

<b>⭐ /favorites</b> - Список всех избранных

<b>❌ /remove_favorite</b> - Удалить из избранных

<b>❓ /help</b> - Эта справка

<b>📊 Формат транзакций:</b>
• <code>кофе -100</code> (описание и сумма)
• <code>+5000 зарплата</code> (сумма и описание)
• <code>-50</code> (только сумма)

Все суммы в <b>UZS</b> (узбекских сумах)
"""
    await update.message.reply_text(help_text, parse_mode="HTML")

# --------------------------
# Показ истории по конкретной дате
# --------------------------
async def show_day_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает историю за конкретную дату в формате DD/MM/YYYY"""
    text = update.message.text.strip()
    
    # Пытаемся распарсить дату в формате DD/MM/YYYY
    try:
        date_parts = text.split("/")
        if len(date_parts) != 3:
            return
        
        day, month, year = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
        
        # Проверяем валидность даты
        if not (1 <= day <= 31 and 1 <= month <= 12 and year > 0):
            return
        
        # Преобразуем в формат YYYY-MM-DD для поиска
        target_date = datetime(year, month, day).strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        # Не удалось распарсить дату, пропускаем
        return
    
    # Ищем транзакции за этот день
    day_transactions = [t for t in transactions if t["date"] == target_date]
    
    if not day_transactions:
        formatted = format_date(target_date)
        await update.message.reply_text(f"📅 Транзакций за {formatted} нет.")
        return
    
    lines = []
    for i, t in enumerate(day_transactions, 1):
        emoji = "➕" if t["amount"] > 0 else "➖"
        time_str = t["timestamp"].strftime("%H:%M")
        lines.append(f"{i}. {emoji} {t['description']}: {format_amount(t['amount'])} — {time_str}")
    
    day_balance = sum(t["amount"] for t in day_transactions)
    formatted = format_date(target_date)
    day_income = sum(t["amount"] for t in day_transactions if t["amount"] > 0)
    day_expenses = sum(t["amount"] for t in day_transactions if t["amount"] < 0)
    
    day_text = "\n".join(lines)
    await update.message.reply_text(
        f"📅 <b>Транзакции за {formatted}</b>:\n\n{day_text}\n\n"
        f"<b>Баланс</b>: {format_amount(day_balance)}\n"
        f"<b>Доход</b>: {format_amount(day_income)}\n"
        f"<b>Расходы</b>: {format_amount(day_expenses)}",
        parse_mode="HTML"
    )

# --------------------------
# Избранные транзакции
# --------------------------
async def start_add_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начнём добавлять избранное - просим описание"""
    await update.message.reply_text(
        "⭐ <b>Добавление избранной транзакции</b>\n\n"
        "Что это за транзакция? (например: <code>кофе</code>, <code>поездка на такси</code>, <code>зарплата от компании</code>)",
        parse_mode="HTML"
    )
    return WAITING_FOR_FAVORITE_DESCRIPTION

async def get_favorite_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получили описание, определяем категорию через ИИ, спрашиваем имя"""
    description = update.message.text.strip()
    context.user_data['favorite_description'] = description
    
    # Пытаемся определить категорию через ИИ
    # Используем 0 как пробную сумму для определения категории
    category = await categorize_expense(description, 0)
    context.user_data['favorite_category'] = category
    
    await update.message.reply_text(
        f"✅ Категория определена: <b>{category}</b>\n\n"
        f"Отлично! Теперь <b>сохраним это как избранное</b>.\n\n"
        "Как назвать эту транзакцию для быстрого добавления? (например: <code>кофе</code>, <code>такси</code>, <code>зп</code>)",
        parse_mode="HTML"
    )
    return WAITING_FOR_FAVORITE_NAME

async def get_favorite_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получили имя, теперь просим сумму"""
    context.user_data['favorite_name'] = update.message.text.strip().lower()
    description = context.user_data['favorite_description']
    category = context.user_data['favorite_category']
    
    await update.message.reply_text(
        f"✅ Сокращение: <code>{context.user_data['favorite_name']}</code> → \"<b>{description}</b>\" [<b>{category}</b>]\n\n"
        "Теперь введи сумму (например: <code>-100</code> для расхода, <code>+5000</code> для дохода)",
        parse_mode="HTML"
    )
    return WAITING_FOR_FAVORITE_AMOUNT

async def get_favorite_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получили сумму, сохраняем избранное с категорией"""
    text = update.message.text.strip()
    
    try:
        amount = float(text)
        name = context.user_data['favorite_name']
        description = context.user_data['favorite_description']
        category = context.user_data['favorite_category']
        
        # Сохраняем избранное с категорией
        favorites[name] = {
            "amount": amount,
            "category": category
        }
        
        emoji = "📈" if amount > 0 else "📉"
        await update.message.reply_text(
            f"✅ <b>Готово!</b>\n\n"
            f"{emoji} <b>{name}</b>: {description} — {format_amount(amount)} [<b>{category}</b>]\n\n"
            f"Теперь просто напиши <code>{name}</code>, и я автоматически добавлю эту операцию!",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Неверная сумма. Введи число (например: <code>-100</code> или <code>+5000</code>)",
            parse_mode="HTML"
        )
        return WAITING_FOR_FAVORITE_AMOUNT
    
    return ConversationHandler.END

async def cancel_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена добавления избранного"""
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все избранные транзакции"""
    if not favorites:
        await update.message.reply_text("⭐ Нет сохранённых избранных.")
        return
    
    lines = []
    for name, data in sorted(favorites.items()):
        amount = data["amount"]
        category = data["category"]
        emoji = "📈" if amount > 0 else "📉"
        lines.append(f"  {emoji} <b>{name}</b>: {format_amount(amount)} [<b>{category}</b>]")
    
    text = "⭐ <b>Избранные транзакции:</b>\n\n" + "\n".join(lines)
    await update.message.reply_text(text, parse_mode="HTML")

async def start_remove_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показываем список избранных для удаления"""
    if not favorites:
        await update.message.reply_text("⭐ Нет сохранённых избранных для удаления.")
        return ConversationHandler.END
    
    lines = []
    for name, data in sorted(favorites.items()):
        amount = data["amount"]
        category = data["category"]
        lines.append(f"<code>{name}</code> — {format_amount(amount)} [<b>{category}</b>]")
    
    text = "❌ <b>Какое избранное удалить?</b>\n\n" + "\n".join(lines)
    await update.message.reply_text(text, parse_mode="HTML")
    return 1

async def remove_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляем избранное"""
    name = update.message.text.strip().lower()
    
    if name in favorites:
        data = favorites.pop(name)
        amount = data["amount"]
        category = data["category"]
        emoji = "📈" if amount > 0 else "📉"
        await update.message.reply_text(
            f"✅ Удалено из избранных:\n{emoji} <b>{name}</b>: {format_amount(amount)} [<b>{category}</b>]",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"❌ <b>{name}</b> не найдено в избранных.",
            parse_mode="HTML"
        )
    
    return ConversationHandler.END

# --------------------------
# Основная часть бота
# --------------------------
if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8766236446:AAGxuFpyJj6L3x9w5DhJY7OonRLCFEEYU-U")

    print("🤖 Бот запускается...")

    app = ApplicationBuilder().token(TOKEN).build()

    # Хендлер ConversationHandler для добавления избранных
    add_favorite_handler = ConversationHandler(
        entry_points=[CommandHandler("add_favorite", start_add_favorite)],
        states={
            WAITING_FOR_FAVORITE_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_favorite_description)],
            WAITING_FOR_FAVORITE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_favorite_name)],
            WAITING_FOR_FAVORITE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_favorite_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel_favorite)],
    )
    
    # Хендлер ConversationHandler для удаления избранных
    remove_favorite_handler = ConversationHandler(
        entry_points=[CommandHandler("remove_favorite", start_remove_favorite)],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_favorite)],
        },
        fallbacks=[CommandHandler("cancel", cancel_favorite)],
    )
    
    # Добавляем все хендлеры
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", show_balance))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("day", show_day))
    app.add_handler(CommandHandler("week", show_week))
    app.add_handler(CommandHandler("two_weeks", show_two_weeks))
    app.add_handler(CommandHandler("month", show_month))
    app.add_handler(CommandHandler("analyze", analyze_expenses))
    app.add_handler(CommandHandler("insights", insights_command))
    app.add_handler(CommandHandler("undo", undo_transaction))
    app.add_handler(CommandHandler("favorites", show_favorites))
    
    # ConversationHandler'ы должны быть добавлены перед обычным MessageHandler'ом
    app.add_handler(add_favorite_handler)
    app.add_handler(remove_favorite_handler)
    
    # Хендлер для проверки дат в формате DD/MM/YYYY (должен быть перед обычным add_transaction)
    app.add_handler(MessageHandler(filters.Regex(r'^\d{1,2}/\d{1,2}/\d{4}$') & ~filters.COMMAND, show_day_by_date))
    
    # Хендлер для обычных сообщений (должен быть в конце)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_transaction))

    app.run_polling()