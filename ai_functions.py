"""
ИИ функции для анализа и нормализации транзакций
Использует OpenAI GPT для улучшения опыта пользователя
"""

import os
import json
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Загружаем переменные из .env файла
load_dotenv()

# Инициализируем OpenAI клиент
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --------------------------
# 1️⃣ НОРМАЛИЗАЦИЯ ТЕКСТА
# --------------------------
async def normalize_text_with_ai(raw_text: str) -> str:
    """
    Превращает криво написанный текст в понятную запись.
    
    Примеры:
    - "долг хумо 200 -" → "Дал в долг другу Хумоюну"
    - "кофе 20 -" → "Покупка кофе"
    - "такси домой 40 -" → "Поездка на такси домой"
    - "мама дала 300 +" → "Получил деньги от мамы"
    """
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Ты помощник для приложения учёта расходов.
                    
Твоя задача: взять криво или коротко написанное описание транзакции и переписать его понятно.

Правила:
- Пиши на русском языке
- Возвращай ТОЛЬКО нормализованное описание, без других комментариев
- Прости опечатки и грамматические ошибки
- Добавляй контекст где нужно
- Максимум 10 слов

Примеры преобразований:
"долг хумо 200 -" → "Дал в долг другу Хумоюну"
"кофе 20 -" → "Покупка кофе"
"такси домой 40 -" → "Поездка на такси домой"
"мама дала 300 +" → "Получил деньги от мамы"
"шоколадка" → "Покупка шоколада"
"билет кино" → "Билет в кино"
"интернет мес" → "Оплата интернета за месяц"
"""
                },
                {
                    "role": "user",
                    "content": f"Нормализуй это описание:\n{raw_text}"
                }
            ],
            temperature=0.3,
            max_tokens=50
        )
        
        normalized = response.choices[0].message.content.strip()
        return normalized
    
    except Exception as e:
        print(f"❌ Ошибка при нормализации текста: {e}")
        # Если ошибка, просто возвращаем оригинальный текст
        return raw_text.lower()

# --------------------------
# 2️⃣ КАТЕГОРИЗАЦИЯ РАСХОДОВ
# --------------------------
async def categorize_expense(description: str, amount: float) -> str:
    """
    Определяет категорию расхода автоматически.
    
    Категории:
    - Еда
    - Транспорт
    - Развлечения
    - Образование
    - Подарки
    - Долги
    - Доходы
    - Другое
    
    Возвращает категорию или "Другое"
    """
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Ты помощник для категоризации транзакций.

Твоя задача: определить категорию расхода на основе описания и суммы.

Доступные категории:
- Еда (кофе, еда, обед, ужин, продукты)
- Транспорт (такси, метро, бензин, билет, поезд)
- Развлечения (кино, игры, музыка, спорт, друзья)
- Образование (книги, курсы, школа, университет)
- Подарки (подарок, для друга, для мамы)
- Долги (долг, заём, вернул)
- Доходы (зарплата, доход, получил, выплатили) - для положительных сумм
- Другое (всё остальное)

Правила:
- Возвращай ТОЛЬКО название категории
- Никаких объяснений
- На русском языке
- Если сумма положительная, скорее всего это доход → "Доходы"
"""
                },
                {
                    "role": "user",
                    "content": f"Описание: {description}\nСумма: {amount}\n\nКакая категория?"
                }
            ],
            temperature=0.2,
            max_tokens=20
        )
        
        category = response.choices[0].message.content.strip()
        
        # Проверяем, что категория в списке
        valid_categories = ["Еда", "Транспорт", "Развлечения", "Образование", 
                          "Подарки", "Долги", "Доходы", "Другое"]
        if category in valid_categories:
            return category
        else:
            return "Другое"
    
    except Exception as e:
        print(f"❌ Ошибка при категоризации: {e}")
        return "Другое"

# --------------------------
# 3️⃣ ПАРСИНГ СВОБОДНОГО ТЕКСТА
# --------------------------
async def parse_free_text(text: str) -> dict:
    """
    Парсит свободный текст и извлекает структурированные данные.
    
    Пример входа:
    "вчера купил кофе за 25"
    
    Возвращает:
    {
        "description": "кофе",
        "amount": -25,
        "success": True,
        "message": ""
    }
    
    Структура возврата:
    {
        "description": str,  # нормализованное описание
        "amount": float,     # сумма (отрицательная для расхода, положительная для дохода)
        "success": bool,     # удалось ли распарсить
        "message": str       # ошибка если не удалось
    }
    """
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Ты парсер для приложения учёта расходов.

Твоя задача: извлечь из свободного текста структурированные данные.

Возвращай JSON с полями:
{
    "description": "описание",  // нормализованное
    "amount": число,            // положительное для дохода, отрицательное для расхода
    "success": true/false,      // удалось ли распарсить
    "message": "ошибка если есть"
}

Примеры:
"вчера купил кофе за 25" →
{
    "description": "Покупка кофе",
    "amount": -25,
    "success": true,
    "message": ""
}

"мама дала 500" →
{
    "description": "Получил деньги от мамы",
    "amount": 500,
    "success": true,
    "message": ""
}

"такси домой 120 рублей" →
{
    "description": "Поездка на такси домой",
    "amount": -120,
    "success": true,
    "message": ""
}

Если не можешь распарсить:
{
    "description": "",
    "amount": 0,
    "success": false,
    "message": "Не смог распарсить текст"
}
"""
                },
                {
                    "role": "user",
                    "content": f"Распарси текст:\n{text}"
                }
            ],
            temperature=0.2,
            max_tokens=150,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)
        
        return result
    
    except json.JSONDecodeError:
        print(f"❌ Ошибка при парсинге JSON из ИИ")
        return {
            "description": "",
            "amount": 0,
            "success": False,
            "message": "Ошибка обработки ИИ"
        }
    except Exception as e:
        print(f"❌ Ошибка при парсинге текста: {e}")
        return {
            "description": "",
            "amount": 0,
            "success": False,
            "message": str(e)
        }

# --------------------------
# 4️⃣ ОБЪЕДИНЕНИЕ ПОХОЖИХ РАСХОДОВ
# --------------------------
async def merge_similar_expenses(transactions_list: list) -> dict:
    """
    Объединяет похожие расходы в обобщённые категории.
    
    Пример входа:
    [
        {"description": "кофе", "amount": -25},
        {"description": "капучино", "amount": -30},
        {"description": "старбакс", "amount": -40},
        {"description": "латте", "amount": -35}
    ]
    
    Возвращает:
    {
        "success": True,
        "merged": {
            "Напитки/Кофе": 130,
            ...
        }
    }
    """
    try:
        # Собираем все описания
        descriptions = [t.get("description", "") for t in transactions_list]
        descriptions_str = "\n".join(descriptions)
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Ты анализатор расходов.

Твоя задача: найти похожие расходы и объединить их в группы.

Вернуть JSON:
{
    "groups": {
        "Напитки (кофе, чай)": ["кофе", "капучино", "латте"],
        "Еда": ["обед", "ужин", "завтрак"],
        "Транспорт": ["такси", "метро", "автобус"]
    }
}

Правила:
- Только на русском
- Группируй по смыслу
- Возвращай ТОЛЬКО JSON
"""
                },
                {
                    "role": "user",
                    "content": f"Вот список расходов:\n{descriptions_str}\n\nГруппируй похожие расходы."
                }
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content.strip())
        
        # Теперь объединяем сумму по группам
        merged = {}
        groups = result.get("groups", {})
        
        for group_name, similar_descriptions in groups.items():
            total = 0
            for transaction in transactions_list:
                if transaction.get("description", "").lower() in [d.lower() for d in similar_descriptions]:
                    total += transaction.get("amount", 0)
            if total != 0:
                merged[group_name] = total
        
        return {
            "success": True,
            "merged": merged
        }
    
    except Exception as e:
        print(f"❌ Ошибка при объединении расходов: {e}")
        return {
            "success": False,
            "merged": {}
        }

# --------------------------
# 5️⃣ УМНЫЕ ФИНАНСОВЫЕ ИНСАЙТЫ
# --------------------------
async def generate_financial_insights(transactions_list: list, period_days: int = 30) -> str:
    """
    Генерирует умные финансовые инсайты на основе данных.
    
    Пример:
    "За последние 7 дней вы потратили 1200 узс. Самые большие расходы - кофе (35%).
    Расходы выросли на 10% по сравнению с прошлой неделей."
    """
    try:
        if not transactions_list:
            return "📊 Нет данных для анализа."
        
        # Подготавливаем статистику
        total_spent = 0
        total_income = 0
        categories = {}
        
        for t in transactions_list:
            amount = t.get("amount", 0)
            category = t.get("category", "Другое")
            description = t.get("description", "")
            
            if amount > 0:
                total_income += amount
            else:
                total_spent += abs(amount)
                if category not in categories:
                    categories[category] = 0
                categories[category] += abs(amount)
        
        # Создаем текст для анализа
        stats_text = f"""За последние {period_days} дней:
- Всего расходов: {total_spent} узс
- Всего доходов: {total_income} узс
- Баланс: {total_income - total_spent} узс

Расходы по категориям:
"""
        for cat, amount in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            percentage = (amount / total_spent * 100) if total_spent > 0 else 0
            stats_text += f"- {cat}: {amount} узс ({percentage:.0f}%)\n"
        
        # Отправляем в ИИ для анализа
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Ты финансовый аналитик.

На основе данных расходов напиши 2-3 умных финансовых инсайта.

Правила:
- Пиши на русском
- Только инсайты, без лишних слов
- Максимум 150 символов
- Указывай факты: какая категория занимает больше всего, есть ли тренды
- Начни с эмодзи 📊"""
                },
                {
                    "role": "user",
                    "content": f"Проанализируй мои расходы:\n{stats_text}"
                }
            ],
            temperature=0.5,
            max_tokens=200
        )
        
        insights = response.choices[0].message.content.strip()
        return insights
    
    except Exception as e:
        print(f"❌ Ошибка при генерации инсайтов: {e}")
        return "📊 Не смог обработать данные."

# --------------------------
# 🧪 ТЕСТИРОВАНИЕ
# --------------------------
async def test_ai_functions():
    """Тест всех ИИ функций"""
    print("🧪 Тестирование ИИ функций...\n")
    
    # Тест 1: Нормализация
    print("1️⃣ Нормализация текста:")
    test_texts = [
        "долг хумо 200 -",
        "кофе 20 -",
        "такси домой 40 -",
        "мама дала 300 +"
    ]
    for text in test_texts:
        normalized = await normalize_text_with_ai(text)
        print(f"  '{text}' → '{normalized}'")
    
    print("\n2️⃣ Категоризация:")
    test_items = [
        ("Покупка кофе", -25),
        ("Поездка на такси", -120),
        ("Зарплата", 5000),
        ("Билет в кино", -200)
    ]
    for desc, amount in test_items:
        category = await categorize_expense(desc, amount)
        print(f"  {desc} ({amount}) → {category}")
    
    print("\n3️⃣ Парсинг свободного текста:")
    test_sentences = [
        "вчера купил кофе за 25",
        "мама дала 500 рублей",
        "такси домой 120",
        "зарплата пришла 10000"
    ]
    for sentence in test_sentences:
        result = await parse_free_text(sentence)
        print(f"  '{sentence}'")
        print(f"    → {result['description']} ({result['amount']})")
        print()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_ai_functions())
