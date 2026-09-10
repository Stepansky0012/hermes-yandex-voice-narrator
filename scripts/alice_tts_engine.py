#!/usr/bin/env python3
"""
Alice TTS Engine & Obsidian Note Preprocessor
==============================================
Официальный синтез речи голосом Алисы (Татьяна Шитова / shitova.us)
через WebSocket Uniproxy (wss://uniproxy.alice.yandex.net/uni.ws).

Включает:
1. Очистку Markdown, Obsidian wikilinks [[link|text]], YAML frontmatter, таблиц, callouts.
2. Нормализацию чисел, порядковых числительных, дат, валют, сокращений и технических терминов.
3. Контекстный анализ эмоций (good / evil / neutral) по предложениям и абзацам.
4. Бесшовную склейку аудиодорожек через ffmpeg в Opus .ogg для Telegram voice notes.
"""

import sys
import os
import re
import json
import uuid
import time
import asyncio
import tempfile
import argparse
import subprocess
from typing import List, Tuple, Optional
import websockets

UNIPROXY_URL = "wss://uniproxy.alice.yandex.net/uni.ws"

# ==============================================================================
# 1. ЧИСЛИТЕЛЬНЫЕ И НОРМАЛИЗАЦИЯ ЧИСЕЛ
# ==============================================================================

UNITS_M = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
UNITS_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
UNITS_N = ["", "одно", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", 
         "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]

THOUSANDS_TABLE = [
    ("", "", "", "m"),
    ("тысяча", "тысячи", "тысяч", "f"),
    ("миллион", "миллиона", "миллионов", "m"),
    ("миллиард", "миллиарда", "миллиардов", "m"),
    ("триллион", "триллиона", "триллионов", "m")
]

def int_to_ru_words(num: int, gender: str = "m") -> str:
    """Перевод целого числа в слова на русском языке."""
    if num == 0:
        return "ноль"
    
    parts = []
    groups = []
    temp = abs(num)
    while temp > 0:
        groups.append(temp % 1000)
        temp //= 1000
        
    for i, g in enumerate(groups):
        if g == 0:
            continue
        g_words = []
        h = g // 100
        t = (g % 100) // 10
        u = g % 10
        
        if h > 0:
            g_words.append(HUNDREDS[h])
            
        g_gender = THOUSANDS_TABLE[i][3] if i > 0 else gender
        u_map = UNITS_F if g_gender == "f" else (UNITS_N if g_gender == "n" else UNITS_M)
        
        if t == 1:
            g_words.append(TEENS[u])
        else:
            if t > 1:
                g_words.append(TENS[t])
            if u > 0:
                g_words.append(u_map[u])
                
        if i > 0:
            name_1, name_2_4, name_5, _ = THOUSANDS_TABLE[i]
            if t == 1:
                t_word = name_5
            elif u == 1:
                t_word = name_1
            elif 2 <= u <= 4:
                t_word = name_2_4
            else:
                t_word = name_5
            g_words.append(t_word)
            
        parts = g_words + parts
        
    res = " ".join(parts)
    if num < 0:
        res = "минус " + res
    return res

def int_to_ordinal_ru(n: int, suffix: str) -> str:
    """Склонение порядковых числительных (1-й, 2-го, 12-му и т.д.)."""
    ordinals_base = {
        1: ("перв", "ый"), 2: ("втор", "ой"), 3: ("трет", "ий"), 4: ("четверт", "ый"),
        5: ("пят", "ый"), 6: ("шест", "ой"), 7: ("седьм", "ой"), 8: ("восьм", "ой"),
        9: ("девят", "ый"), 10: ("десят", "ый"), 11: ("одиннадцат", "ый"),
        12: ("двенадцат", "ый"), 13: ("тринадцат", "ый"), 14: ("четырнадцат", "ый"),
        15: ("пятнадцат", "ый"), 16: ("шестнадцат", "ый"), 17: ("семнадцат", "ый"),
        18: ("восемнадцат", "ый"), 19: ("девятнадцат", "ый"), 20: ("двадцат", "ый"),
        30: ("тридцат", "ый"), 40: ("сороков", "ой"), 50: ("пятидесят", "ый"),
        60: ("шестидесят", "ый"), 70: ("семидесят", "ый"), 80: ("восьмидесят", "ый"),
        90: ("девяност", "ый"), 100: ("сот", "ый")
    }
    
    stem = ""
    prefix = ""
    if n in ordinals_base:
        stem = ordinals_base[n][0]
    elif 21 <= n <= 99:
        t = (n // 10) * 10
        u = n % 10
        tens_names = {20: "двадцать", 30: "тридцать", 40: "сорок", 50: "пятьдесят", 60: "шестьдесят", 70: "семьдесят", 80: "восемьдесят", 90: "девяносто"}
        prefix = tens_names.get(t, "") + " "
        if u in ordinals_base:
            stem = ordinals_base[u][0]
        else:
            stem = str(u)
    else:
        return f"{n}-{suffix}"
        
    s = suffix.lower()
    if stem == "трет":
        endings = {"й": "ий", "го": "ьего", "му": "ьему", "м": "ьем", "я": "ья", "е": "ье", "ю": "ью", "х": "ьих", "ми": "ьими"}
    else:
        endings = {"й": "ый" if stem[-1] not in ['р', 'м'] else "ой", "го": "ого", "му": "ому", "м": "ом", "я": "ая", "е": "ое", "ю": "ую", "х": "ых", "ми": "ыми"}
        
    end = endings.get(s, s)
    return prefix + stem + end

def declension_word(n: int, word_1: str, word_2_4: str, word_5: str) -> str:
    """Склонение существительного по числу."""
    abs_n = abs(n) % 100
    last = abs_n % 10
    if 11 <= abs_n <= 19:
        return word_5
    if last == 1:
        return word_1
    if 2 <= last <= 4:
        return word_2_4
    return word_5

def normalize_numbers_and_units(text: str) -> str:
    """Нормализация числительных, валют, процентов, диапазонов и дат."""
    
    # Порядковые с дефисом: 12-го, 1-й, 2-я, 5-му
    def replace_ordinal(m):
        num = int(m.group(1))
        sfx = m.group(2)
        return int_to_ordinal_ru(num, sfx)
    text = re.sub(r'\b(\d+)-(й|го|му|м|я|е|ю|х|ми)\b', replace_ordinal, text, flags=re.IGNORECASE)

    # 1. Года: "в 2026 году" / "в 2026 г." / "2026 год" / "2026 г."
    def replace_year_prep(m):
        year = int(m.group(1))
        if 2000 <= year <= 2099:
            y_tail = year - 2000
            if y_tail == 0:
                return "в двухтысячном году"
            elif 1 <= y_tail <= 9:
                ords = ["", "первом", "втором", "третьем", "четвертом", "пятом", "шестом", "седьмом", "восьмом", "девятом"]
                return f"в две тысячи {ords[y_tail]} году"
            elif 10 <= y_tail <= 19:
                ords = ["десятом", "одиннадцатом", "двенадцатом", "тринадцатом", "четырнадцатом", "пятнадцатом",
                        "шестнадцатом", "семнадцатом", "восемнадцатом", "девятнадцатом"]
                return f"в две тысячи {ords[y_tail - 10]} году"
            elif 20 <= y_tail <= 99:
                t = y_tail // 10
                u = y_tail % 10
                tens_names = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
                if u == 0:
                    tens_ords = ["", "", "двадцатом", "тридцатом", "сороковом", "пятидесятом", "шестидесятом", "семидесятом", "восьмидесятом", "девяностом"]
                    return f"в две тысячи {tens_ords[t]} году"
                else:
                    ords = ["", "первом", "втором", "третьем", "четвертом", "пятом", "шестом", "седьмом", "восьмом", "девятом"]
                    return f"в две тысячи {tens_names[t]} {ords[u]} году"
        return f"в {int_to_ru_words(year)} году"

    text = re.sub(r'\b[в|В]\s+(\d{4})\s*(?:г\.|году|года)?\b', replace_year_prep, text)

    def replace_year_nom(m):
        year = int(m.group(1))
        if 2000 <= year <= 2099:
            y_tail = year - 2000
            if y_tail == 0:
                return "двухтысячный год"
            elif 1 <= y_tail <= 9:
                ords = ["", "первый", "второй", "третий", "четвертый", "пятый", "шестой", "седьмой", "восьмой", "девятый"]
                return f"две тысячи {ords[y_tail]} год"
            elif 10 <= y_tail <= 19:
                ords = ["десятый", "одиннадцатый", "двенадцатый", "тринадцатый", "четырнадцатый", "пятнадцатый",
                        "шестнадцатый", "семнадцатый", "восемнадцатый", "девятнадцатый"]
                return f"две тысячи {ords[y_tail - 10]} год"
            elif 20 <= y_tail <= 99:
                t = y_tail // 10
                u = y_tail % 10
                tens_names = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
                if u == 0:
                    tens_ords = ["", "", "двадцатый", "тридцатый", "сороковой", "пятидесятый", "шестидесятый", "семидесятый", "восьмидесятый", "девяностый"]
                    return f"две тысячи {tens_ords[t]} год"
                else:
                    ords = ["", "первый", "второй", "третий", "четвертый", "пятый", "шестой", "седьмой", "восьмой", "девятый"]
                    return f"две тысячи {tens_names[t]} {ords[u]} год"
        return f"{int_to_ru_words(year)} год"

    text = re.sub(r'\b(\d{4})\s*(?:г\.|год)\b', replace_year_nom, text)

    # 2. Валюты: 100 руб, 100 ₽, $50, 50€
    def replace_rub(m):
        n = int(m.group(1))
        w = int_to_ru_words(n, "m")
        cur = declension_word(n, "рубль", "рубля", "рублей")
        return f"{w} {cur}"
    text = re.sub(r'(\d+)\s*(?:руб\.?|рублей|₽)', replace_rub, text)

    def replace_usd(m):
        n = int(m.group(1))
        w = int_to_ru_words(n, "m")
        cur = declension_word(n, "доллар", "доллара", "долларов")
        return f"{w} {cur}"
    text = re.sub(r'\$\s*(\d+)', replace_usd, text)
    text = re.sub(r'(\d+)\s*(?:usd|\$|долларов)', replace_usd, text, flags=re.IGNORECASE)

    def replace_eur(m):
        n = int(m.group(1))
        w = int_to_ru_words(n, "m")
        cur = declension_word(n, "евро", "евро", "евро")
        return f"{w} {cur}"
    text = re.sub(r'€\s*(\d+)', replace_eur, text)
    text = re.sub(r'(\d+)\s*(?:eur|€|евро)', replace_eur, text, flags=re.IGNORECASE)

    # 3. Проценты: 15% / 15 %
    def replace_percent(m):
        n = int(m.group(1))
        w = int_to_ru_words(n, "m")
        p = declension_word(n, "процент", "процента", "процентов")
        return f"{w} {p}"
    text = re.sub(r'(\d+)\s*%', replace_percent, text)

    # 4. Диапазоны: 10-15 -> от десяти до пятнадцати
    def replace_range(m):
        n1 = int(m.group(1))
        n2 = int(m.group(2))
        return f"от {int_to_ru_words(n1)} до {int_to_ru_words(n2)}"
    text = re.sub(r'\b(\d+)\s*[-–—]\s*(\d+)\b', replace_range, text)

    # 5. Дробные числа: 3.14 или 3,14
    def replace_decimal(m):
        whole = int(m.group(1))
        frac = m.group(2)
        w_words = int_to_ru_words(whole, "f")
        w_decl = declension_word(whole, "целая", "целых", "целых")
        frac_n = int(frac)
        f_words = int_to_ru_words(frac_n, "f" if str(frac_n).endswith("1") or str(frac_n).endswith("2") else "m")
        if len(frac) == 1:
            f_decl = declension_word(frac_n, "десятая", "десятых", "десятых")
        elif len(frac) == 2:
            f_decl = declension_word(frac_n, "сотая", "сотых", "сотых")
        elif len(frac) == 3:
            f_decl = declension_word(frac_n, "тысячная", "тысячных", "тысячных")
        else:
            f_decl = "дробных"
        return f"{w_words} {w_decl} {f_words} {f_decl}"
    text = re.sub(r'\b(\d+)[.,](\d{1,3})\b', replace_decimal, text)

    # 6. Номер №: № 5 -> номер пять
    text = re.sub(r'№\s*(\d+)', lambda m: f"номер {int_to_ru_words(int(m.group(1)))}", text)

    # 7. Единицы измерения
    units_map = [
        (r'(\d+)\s*км\b', "километр", "километра", "километров", "m"),
        (r'(\d+)\s*м\b', "метр", "метра", "метров", "m"),
        (r'(\d+)\s*см\b', "сантиметр", "сантиметра", "сантиметров", "m"),
        (r'(\d+)\s*мм\b', "миллиметр", "миллиметра", "миллиметров", "m"),
        (r'(\d+)\s*кг\b', "килограмм", "килограмма", "килограммов", "m"),
        (r'(\d+)\s*г\b', "грамм", "грамма", "граммов", "m"),
        (r'(\d+)\s*(?:сек\.?|с\.)\b', "секунда", "секунды", "секунд", "f"),
        (r'(\d+)\s*(?:мин\.?|м\.)\b', "минута", "минуты", "минут", "f"),
        (r'(\d+)\s*(?:час\.?|ч\.)\b', "час", "часа", "часов", "m"),
        (r'(\d+)\s*мс\b', "миллисекунда", "миллисекунды", "миллисекунд", "f"),
        (r'(\d+)\s*(?:ГБ|Гб|GB|gb)\b', "гигабайт", "гигабайта", "гигабайт", "m"),
        (r'(\d+)\s*(?:МБ|Мб|MB|mb)\b', "мегабайт", "мегабайта", "мегабайт", "m"),
        (r'(\d+)\s*(?:КБ|Кб|KB|kb)\b', "килобайт", "килобайта", "килобайт", "m"),
        (r'(\d+)\s*(?:ТБ|Тб|TB|tb)\b', "терабайт", "терабайта", "терабайт", "m"),
        (r'(\d+)\s*(?:°C|градус(?:ов|а)? цельсия)\b', "градус цельсия", "градуса цельсия", "градусов цельсия", "m")
    ]
    for pattern, w1, w2, w5, g in units_map:
        def make_rep(word1, word2, word5, gen):
            def repl(m):
                n = int(m.group(1))
                w = int_to_ru_words(n, gen)
                u = declension_word(n, word1, word2, word5)
                return f"{w} {u}"
            return repl
        text = re.sub(pattern, make_rep(w1, w2, w5, g), text)

    # 8. Оставшиеся целые числа
    def replace_remaining_ints(m):
        n = int(m.group(0))
        return int_to_ru_words(n, "m")
    text = re.sub(r'\b\d+\b', replace_remaining_ints, text)

    return text

# ==============================================================================
# 2. СЛОВАРЬ СОКРАЩЕНИЙ И IT-ТЕРМИНОВ
# ==============================================================================

ABBREVIATIONS = {
    r'\bт\.д\.\b': 'так далее',
    r'\bт\.п\.\b': 'тому подобное',
    r'\bт\.е\.\b': 'то есть',
    r'\bт\.к\.\b': 'так как',
    r'\bт\.о\.\b': 'таким образом',
    r'\bт\.н\.\b': 'так называемый',
    r'\bв т\.ч\.\b': 'в том числе',
    r'\bдр\.\b': 'другие',
    r'\bпр\.\b': 'прочее',
    r'\bсм\.\b': 'смотри',
    r'\bул\.\b': 'улица',
    r'\bстр\.\b': 'страница',
    r'\bрис\.\b': 'рисунок',
    r'\bтабл\.\b': 'таблица',
    r'\bгл\.\b': 'глава',
    r'\bтел\.\b': 'телефон',
}

TECH_TERMS = {
    r'\bAI\b': 'и-и',
    r'\bИИ\b': 'и-и',
    r'\bLLM\b': 'эл-эл-эм',
    r'\bTTS\b': 'тэ-тэ-эс',
    r'\bSTT\b': 'эс-тэ-тэ',
    r'\bAPI\b': 'апи',
    r'\bCLI\b': 'си-эл-ай',
    r'\bUI\b': 'ю-ай',
    r'\bUX\b': 'ю-икс',
    r'\bOS\b': 'операционная система',
    r'\bОС\b': 'операционная система',
    r'\bMCP\b': 'эм-си-пи',
    r'\bSQL\b': 'сиквел',
    r'\bPostgreSQL\b': 'постгрес',
    r'\bPostgres\b': 'постгрес',
    r'\bDocker\b': 'докер',
    r'\bPython\b': 'пайтон',
    r'\bGit\b': 'гит',
    r'\bGitHub\b': 'гитхаб',
    r'\bTelegram\b': 'телеграм',
    r'\bTG\b': 'телеграм',
    r'\bТГ\b': 'телеграм',
    r'\bWB\b': 'вайлдберриз',
    r'\bВБ\b': 'вайлдберриз',
    r'\bVK\b': 'вконтакте',
    r'\bВК\b': 'вконтакте',
    r'\bPR\b': 'пулреквест',
    r'\bURL\b': 'урл',
    r'\bID\b': 'айди',
    r'\bHTTP\b': 'хттп',
    r'\bHTTPS\b': 'хттпс',
    r'\bWS\b': 'вебсокет',
    r'\bWSS\b': 'вебсокет',
    r'\bJSON\b': 'джейсон',
    r'\bYAML\b': 'ямл',
    r'\bCPU\b': 'си-пи-ю',
    r'\bGPU\b': 'джи-пи-ю',
    r'\bRAM\b': 'оперативная память',
    r'\bWebSockets?\b': 'вебсокеты',
    r'\bFastAPI\b': 'фаст-апи',
    r'\bClaude\b': 'клод',
    r'\bChatGPT\b': 'чат-гпт',
    r'\bGemini\b': 'джеминай',
    r'\bDeepSeek\b': 'дипсик',
    r'\bHermes\b': 'гермес',
    r'\bObsidian\b': 'обсидиан',
    r'\bMarkdown\b': 'маркдаун',
    r'\bUniproxy\b': 'юнипрокси',
    r'\bSpeechKit\b': 'спичкит',
    r'\b[CcСс]1\b': 'си-один',
    r'\b[CcСс]2\b': 'си-два',
    r'\b[CcСс]3\b': 'си-три',
    r'\b[CcСс]4\b': 'си-четыре',
}

def expand_abbreviations_and_tech(text: str) -> str:
    """Замена сокращений и транслитерация IT терминов для естественной озвучки."""
    for pattern, replacement in ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    for pattern, replacement in TECH_TERMS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

# ==============================================================================
# 3. ОЧИСТКА И НОРМАЛИЗАЦИЯ MARKDOWN / OBSIDIAN ЗАМЕТОК
# ==============================================================================

def clean_markdown_and_obsidian(text: str) -> str:
    """Полная очистка Markdown, Obsidian Wiki-структур и спецсимволов."""
    # 1. Удаление YAML Frontmatter
    text = re.sub(r'^---\s*\n.*?\n---\s*\n', '', text, flags=re.DOTALL)
    
    # 2. Удаление HTML тегов и комментариев
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 3. Obsidian Callouts: > [!NOTE], > [!WARNING], > [!TIP], > [!INFO]
    callouts = {
        r'>\s*\[!NOTE\]\s*': 'Примечание: ',
        r'>\s*\[!WARNING\]\s*': 'Внимание! ',
        r'>\s*\[!CAUTION\]\s*': 'Осторожно! ',
        r'>\s*\[!TIP\]\s*': 'Совет: ',
        r'>\s*\[!INFO\]\s*': 'Информация: ',
        r'>\s*\[!IMPORTANT\]\s*': 'Важно: ',
        r'>\s*\[!SUCCESS\]\s*': 'Успешно! ',
        r'>\s*\[!FAILURE\]\s*': 'Ошибка! ',
        r'>\s*\[!QUESTION\]\s*': 'Вопрос: '
    }
    for c_pat, c_rep in callouts.items():
        text = re.sub(c_pat, c_rep, text, flags=re.IGNORECASE)
        
    # 4. Блоки кода: заменяем на краткое упоминание, чтобы не читать скобки
    text = re.sub(r'```(\w+)?\n.*?\n```', r' Приводится фрагмент кода. ', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # 5. Obsidian Wikilinks: [[Target|Display]] -> Display; [[Target]] -> Target
    text = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', text)
    
    # 6. Markdown ссылки и изображения
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'https?://[^\s]+', 'по ссылке', text)
    
    # 7. Таблицы Markdown: конвертация в структурированный текст
    def process_table_line(line):
        if not line.strip().startswith('|'):
            return line
        cells = [c.strip() for c in line.split('|') if c.strip()]
        if not cells or all(re.match(r'^:?-+:?$', c) for c in cells):
            return ''
        return ", ".join(cells) + "."
    
    lines = [process_table_line(l) for l in text.splitlines()]
    text = "\n".join([l for l in lines if l])
    
    # 8. Заголовки: превращаем в отдельные предложения с паузой
    text = re.sub(r'^#{1,6}\s*(.+)$', r'\1.', text, flags=re.MULTILINE)
    
    # 9. Списки и цитаты
    text = re.sub(r'^\s*[-*+]\s*\[[ xX]\]\s*', 'Пункт: ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*+]\s*', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s*', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)
    
    # 10. Форматирование: жирный, курсив, зачеркивание, сноски
    text = re.sub(r'[*_~=]{1,3}([^*_~=]+)[*_~=]{1,3}', r'\1', text)
    text = re.sub(r'\[\^\d+\]', '', text)
    
    # 11. Очистка повторов и лишних спецсимволов
    text = re.sub(r'\b(Внимание!)\s+\1\b', r'\1', text, flags=re.IGNORECASE)
    text = re.sub(r'[\\#*_{}\[\]<>]', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

# ==============================================================================
# 4. КОНТЕКСТНЫЙ АНАЛИЗ ЭМОЦИЙ
# ==============================================================================

GOOD_WORDS = {
    'отлично', 'ура', 'поздравляю', 'супер', 'прекрасно', 'замечательно', 
    'успешно', 'победа', 'рада', 'великолепно', 'здорово', 'класс', 'круто', 
    'люблю', 'спасибо', 'благодарю', 'блестяще', 'восхитительно', 'радость',
    'восторг', 'потрясающе', 'красота', 'success', 'great', 'awesome'
}

EVIL_WORDS = {
    'внимание', 'ошибка', 'опасно', 'запрещено', 'сбой', 'провал', 'катастрофа', 
    'критично', 'ужас', 'плохо', 'баг', 'отклонено', 'нельзя', 'авария', 
    'предупреждение', 'тревога', 'угроза', 'дефект', 'сломано', 'error', 
    'failed', 'warning', 'danger', 'critical', 'alert'
}

def analyze_emotion(text: str) -> str:
    """Определение контекстной эмоции ('good', 'evil', 'neutral')."""
    words = set(re.findall(r'\b\w+\b', text.lower()))
    good_score = len(words.intersection(GOOD_WORDS))
    evil_score = len(words.intersection(EVIL_WORDS))
    
    exclamations = text.count('!')
    if exclamations > 0 and good_score > 0:
        good_score += 1
    if exclamations > 0 and evil_score > 0:
        evil_score += 1
        
    if good_score > evil_score and good_score >= 1:
        return 'good'
    elif evil_score > good_score and evil_score >= 1:
        return 'evil'
    return 'neutral'

# ==============================================================================
# 5. РАЗБИЕНИЕ ТЕКСТА НА СЕМАНТИЧЕСКИЕ ЧАНКИ
# ==============================================================================

def preprocess_text(raw_text: str) -> str:
    """Полный пайплайн предпроцессинга текста."""
    t = clean_markdown_and_obsidian(raw_text)
    t = expand_abbreviations_and_tech(t)
    t = normalize_numbers_and_units(t)
    return t

def split_into_emotional_chunks(text: str, max_chars: int = 800) -> List[Tuple[str, str]]:
    """
    Разбиение текста на предложения с группировкой по одинаковой эмоции
    до max_chars на чанк для эмоционально выразительной озвучки.
    """
    sentences = re.split(r'(?<=[.!?…])\s+', text)
    chunks = []
    current_chunk = []
    current_emotion = None
    current_len = 0
    
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        s_emo = analyze_emotion(s)
        
        # Если изменилась эмоция или превышен лимит длины
        if (current_emotion is not None and s_emo != current_emotion and current_len > 0) or (current_len + len(s) > max_chars):
            chunk_str = " ".join(current_chunk)
            chunks.append((chunk_str, current_emotion))
            current_chunk = [s]
            current_emotion = s_emo
            current_len = len(s)
        else:
            if current_emotion is None:
                current_emotion = s_emo
            current_chunk.append(s)
            current_len += len(s) + 1
            
    if current_chunk:
        chunk_str = " ".join(current_chunk)
        chunks.append((chunk_str, current_emotion))
        
    return chunks

# ==============================================================================
# 6. СИНТЕЗ ЧЕРЕЗ WEBSOCKET UNIPROXY И СКЛЕЙКА
# ==============================================================================

async def synthesize_chunk(ws, text: str, voice: str = "nastya", emotion: str = "neutral", speed: float = 1.0) -> bytes:
    """Синтез одного чанка текста через активный вебсокет."""
    msg_id = str(uuid.uuid4())
    payload = {
        "event": {
            "header": {
                "namespace": "TTS",
                "name": "Generate",
                "messageId": msg_id
            },
            "payload": {
                "voice": voice,
                "lang": "ru-RU",
                "format": "audio/opus",
                "speed": speed,
                "emotion": emotion,
                "text": text
            }
        }
    }
    await ws.send(json.dumps(payload))
    
    audio_chunks = []
    target_stream_id = None
    
    while True:
        msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
        if isinstance(msg, str):
            data = json.loads(msg)
            if "directive" in data:
                hdr = data["directive"].get("header", {})
                if hdr.get("name") == "Speak" and hdr.get("refMessageId") == msg_id:
                    target_stream_id = hdr.get("streamId")
            elif "streamcontrol" in data:
                ctrl = data["streamcontrol"]
                if ctrl.get("streamId") == target_stream_id and ctrl.get("action") == 0:
                    break
        elif isinstance(msg, bytes) and len(msg) > 4:
            stream_id = int.from_bytes(msg[:4], "big")
            if target_stream_id is None or stream_id == target_stream_id:
                audio_chunks.append(msg[4:])
                
    return b"".join(audio_chunks)

async def synthesize_text_to_file(raw_text: str, output_file: str, voice: str = "nastya", speed: float = 1.0) -> str:
    """
    Основная функция: предобработка текста, эмоциональный чанкинг,
    синтез каждого чанка и склейка в валидный Telegram Opus Ogg.
    """
    clean_txt = preprocess_text(raw_text)
    if not clean_txt.strip():
        raise ValueError("Текст после предобработки оказался пустым.")
        
    chunks = split_into_emotional_chunks(clean_txt)
    print(f"[*] Текст предобработан: {len(clean_txt)} симв., разбито на {len(chunks)} смысловых чанков.")
    
    temp_files = []
    
    for idx, (chunk_text, emotion) in enumerate(chunks, 1):
        print(f"  [+] Синтез чанка {idx}/{len(chunks)} (голос: '{voice}', эмоция: '{emotion}', длина: {len(chunk_text)} симв.)...")
        raw_audio = None
        last_error = None
        for attempt in range(1, 5):
            try:
                # Uniproxy can close long-lived sockets during long narrations.
                # Reconnect per chunk and retry without discarding completed work.
                async with websockets.connect(UNIPROXY_URL, ping_interval=10, ping_timeout=15) as ws:
                    raw_audio = await synthesize_chunk(
                        ws, chunk_text, voice=voice, emotion=emotion, speed=speed
                    )
                break
            except Exception as exc:
                last_error = exc
                if attempt < 4:
                    await asyncio.sleep(attempt * 1.5)
        if raw_audio is None:
            raise RuntimeError(
                f"Не удалось синтезировать чанк {idx}/{len(chunks)} после 4 попыток"
            ) from last_error

        tmp_f = tempfile.NamedTemporaryFile(suffix=f"_chunk_{idx}.ogg", delete=False)
        tmp_f.write(raw_audio)
        tmp_f.close()
        temp_files.append(tmp_f.name)
            
    # Если чанк один — проверяем и копируем
    if len(temp_files) == 1:
        subprocess.run([
            "ffmpeg", "-y", "-i", temp_files[0],
            "-c:a", "copy", output_file
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    else:
        filter_inputs = "".join([f"[{i}:a]" for i in range(len(temp_files))])
        filter_complex = f"{filter_inputs}concat=n={len(temp_files)}:v=0:a=1[out]"
        
        cmd = ["ffmpeg", "-y"]
        for f in temp_files:
            cmd.extend(["-i", f])
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:a", "libopus",
            "-b:a", "48k",
            "-ar", "48000",
            "-ac", "1",
            "-application", "voip",
            output_file
        ])
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
    for f in temp_files:
        try:
            os.remove(f)
        except OSError:
            pass
            
    print(f"[✓] Готово! Итоговый файл сохранен: {output_file}")
    return output_file

# ==============================================================================
# 7. CLI И ТОЧКА ВХОДА
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Alice TTS Engine with Advanced Markdown & Note Preprocessor")
    parser.add_argument("text", nargs="?", help="Текст для озвучки (если не указан --input)")
    parser.add_argument("-i", "--input", help="Путь к файлу заметки (.md, .txt) для озвучки")
    parser.add_argument("-o", "--output", default="output.ogg", help="Выходной файл (.ogg)")
    parser.add_argument("-v", "--voice", default="nastya", help="Голос (по умолчанию: nastya, варианты: shitova.us, jane, oksana, omazh, sasha, zahar, ermil, kolya, kostya)")
    parser.add_argument("-s", "--speed", type=float, default=1.0, help="Скорость речи (по умолчанию: 1.0)")
    parser.add_argument("--preview-text", action="store_true", help="Только показать очищенный текст без генерации аудио")
    
    args = parser.parse_args()
    
    raw_text = ""
    if args.input:
        if not os.path.exists(args.input):
            print(f"Ошибка: Файл {args.input} не найден!", file=sys.stderr)
            sys.exit(1)
        with open(args.input, "r", encoding="utf-8") as f:
            raw_text = f.read()
    elif args.text:
        raw_text = args.text
    else:
        raw_text = sys.stdin.read()
        
    if not raw_text.strip():
        print("Ошибка: Нет текста для озвучки.", file=sys.stderr)
        sys.exit(1)
        
    if args.preview_text:
        processed = preprocess_text(raw_text)
        chunks = split_into_emotional_chunks(processed)
        print("=== ПРЕДОБРАБОТАННЫЙ ТЕКСТ ===")
        print(processed)
        print("\n=== ЧАНКИ И ЭМОЦИИ ===")
        for i, (c, emo) in enumerate(chunks, 1):
            print(f"[{i}] [{emo.upper()}] {c}\n")
        return
        
    asyncio.run(synthesize_text_to_file(raw_text, args.output, voice=args.voice, speed=args.speed))

if __name__ == "__main__":
    main()
