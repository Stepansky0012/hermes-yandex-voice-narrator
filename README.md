# 🎙️ Hermes Yandex Voice Narrator Skill

> Автономный навык высококачественной озвучки заметок Obsidian / LLM Wiki и текстов голосами экосистемы Яндекса (**Настя**, **Алиса**, **Захар**, **Джейн** и др.) для **Hermes Agent**.

Синтез работает напрямую через WebSocket-протокол Яндекс Uniproxy (`wss://uniproxy.alice.yandex.net/uni.ws`) без сторонних сервисов и включает многоступенчатый русскоязычный предпроцессор текста.

---

## 🌟 Основные возможности

1. **Голоса Яндекса на выбор:**
   - `nastya` — Настя (молодежный, живой, по умолчанию для Светочки)
   - `shitova.us` — Официальная Алиса (Татьяна Шитова)
   - `jane` — Джейн (деловой, спокойный тон)
   - `oksana` — Оксана (мягкий повествовательный)
   - `omazh` — Омаж (эмоциональный)
   - `sasha` — Саша (дикторский)
   - `zahar` — Захар (глубокий мужской баритон)
   - `ermil` — Ермил (строгий классический диктор)
   - `kolya` — Коля (молодой мужской)
   - `kostya` — Костя (нейтральный мужской баритон)

2. **Русскоязычный предпроцессор:**
   - **Очистка Markdown / Obsidian:** удаление YAML frontmatter, html-разметки, трансляция callouts (`> [!NOTE]` -> «Примечание:», `> [!WARNING]` -> «Внимание!»), разворачивание wikilinks `[[Link|Text]]` -> `Text`, форматирование таблиц в связную речь.
   - **Нормализация числительных и дат:** автоматическое преобразование дат («в 2026 году»), порядковых числительных («12-го» -> «двенадцатого»), валют («100 руб.», «$500»), процентов («15%»), единиц («15 мс», «2 ГБ», «10 км»).
   - **IT-термины и аббревиатуры:** правильное чтение `AI`, `LLM`, `TTS`, `STT`, `API`, `PostgreSQL`, `Docker`, `GitHub`, `C1–C4`.
   - **Контекстные эмоции:** сегментация текста и вычисление эмоционального окраса (`good`, `evil`, `neutral`) для каждого фрагмента.
   - **Бесшовная склейка лонгридов:** тексты любого размера автоматически чанкуются и склеиваются через `ffmpeg` в единый чистый Opus `.ogg` (48 kHz) для Telegram Voice Notes.

---

## 🚀 Быстрый старт и импорт в Hermes

### 1. Установка зависимостей
```bash
pip install websockets
sudo apt-get install -y ffmpeg
```

### 2. Клонирование навыка в Hermes
```bash
git clone https://github.com/Stepansky0012/hermes-yandex-voice-narrator.git ~/.hermes/skills/research/alice-voice-narrator
```

### 3. Настройка `~/.hermes/config.yaml`
```yaml
tts:
  provider: alice
  speed: 1.0
  providers:
    alice:
      type: command
      command: "python3 ~/.hermes/skills/research/alice-voice-narrator/scripts/alice_tts_engine.py --input {input_path} --output {output_path} --voice nastya --speed {speed}"
      output_format: ogg
```

---

## 💻 Использование через CLI

```bash
# Озвучить заметку Obsidian:
python3 scripts/alice_tts_engine.py -i /path/to/note.md -o output.ogg

# Озвучить с выбором голоса (например, Захар):
python3 scripts/alice_tts_engine.py -i /path/to/note.md -v zahar -o voice.ogg

# Просмотр очищенного текста и эмоций:
python3 scripts/alice_tts_engine.py -i /path/to/note.md --preview-text
```

---

## 📄 Лицензия
MIT License
