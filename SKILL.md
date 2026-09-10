---
name: alice-voice-narrator
description: Высококачественная озвучка заметок Obsidian / LLM Wiki и произвольного текста голосами Яндекса (Настя, Алиса, Захар и др.) через Uniproxy WebSocket с контекстным предпроцессором.
---

# Alice & Yandex Voice Narrator for Hermes

Полнофункциональный скилл синтеза речи на базе WebSocket-протокола Яндекс Uniproxy (`wss://uniproxy.alice.yandex.net/uni.ws`) со встроенным русскоязычным предпроцессором текста, нормализатором числительных и контекстным эмоциональным анализом.

Скилл полностью автономен: содержит готовый скрипт движка, инструкции по интеграции в любой Hermes-агент и шаблоны конфигурации.

---

## 1. Возможности скилла

- **Голоса экосистемы Яндекса:**
  - `nastya` — Настя (молодежный, живой женский голос, по умолчанию для Светочки).
  - `shitova.us` — Официальная Алиса (Татьяна Шитова, ироничный брендовый тембр).
  - `jane` — Джейн (деловой, спокойный аналитический тон).
  - `oksana` — Оксана (мягкий повествовательный тембр).
  - `omazh` — Омаж (выразительный, эмоциональный).
  - `sasha` — Саша (спокойный дикторский женский голос).
  - `zahar` — Захар (глубокий авторитетный мужской баритон).
  - `ermil` — Ермил (строгий классический дикторский голос).
  - `kolya` — Коля (молодой мужской тембр).
  - `kostya` — Костя (деловой нейтральный мужской голос).
- **Многоступенчатый предпроцессор текста:**
  - Очистка Markdown, YAML-шапок, ссылок Obsidian `[[Target|Display]]`, callout-блоков и таблиц.
  - Нормализация дат (`в 2026 году`), числительных, валют (`100 руб.`, `$500`), процентов, единиц (`15 мс`, `2 ГБ`, `10 км`).
  - Словарь IT-терминов: `AI`, `LLM`, `TTS`, `STT`, `API`, `PostgreSQL`, `Docker`, `C1`–`C4`, `GitHub`.
  - Контекстный анализ эмоций (`good`, `evil`, `neutral`) по предложениям и абзацам.
  - Потоковое разбиение длинных текстов на смысловые чанки и бесшовная склейка в моно Opus `.ogg` (48 kHz) через `ffmpeg` для нативных голосовых сообщений Telegram.

---

## 2. Как импортировать скилл в другой Hermes-агент

### Шаг A. Перенос директории скилла
Скопируйте папку навыка в директорию скиллов целевого агента:
```bash
cp -r ~/.hermes/skills/research/alice-voice-narrator ~/.hermes/skills/research/
```

### Шаг B. Зависимости
Убедитесь, что установлены необходимые пакеты:
```bash
uv pip install websockets # или pip install websockets
sudo apt-get update && sudo apt-get install -y ffmpeg
```

### Шаг C. Подключение в конфигурацию Hermes (`~/.hermes/config.yaml`)
Добавьте или обновите секцию `tts` в файле `~/.hermes/config.yaml`:
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

## 3. Команды использования

> **Обязательное правило для Telegram:** запросы «озвучь», «голосом», «сделай войс» должны завершаться отправкой нативного голосового сообщения, а не обычного аудиофайла или документа. В финальном ответе всегда ставьте отдельной строкой `[[audio_as_voice]]` непосредственно перед `MEDIA:/absolute/path/output.ogg`. Одного расширения `.ogg` и параметра ffmpeg `-application voip` недостаточно: без директивы шлюз Telegram может выбрать `sendDocument`.

### Через системный инструмент Hermes:
```python
text_to_speech(text="Привет! Текст озвучивается через встроенный навык.")
```

### Через CLI:
```bash
# Озвучка файла заметки:
python3 ~/.hermes/skills/research/alice-voice-narrator/scripts/alice_tts_engine.py -i note.md -o output.ogg

# Выбор другого голоса (например, Захар или Алиса) и скорости:
python3 ~/.hermes/skills/research/alice-voice-narrator/scripts/alice_tts_engine.py -i note.md -v zahar -s 1.1 -o output.ogg

# Предварительный просмотр очищенного текста и эмоций без генерации аудио:
python3 ~/.hermes/skills/research/alice-voice-narrator/scripts/alice_tts_engine.py -i note.md --preview-text
```

---

## 4. Проверка качества и доставка в Telegram

Перед отправкой аудио в Telegram валидируйте параметры через `ffprobe`:
```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,sample_rate,channels -of default=noprint_wrappers=1 output.ogg
```
Ожидаемый результат: `codec_name=opus`, `sample_rate=48000`, `channels=1`.

### Доставка в Telegram как нативного голосового сообщения (Voice Bubble):
Чтобы Telegram отправил аудиофайл как нативное голосовое сообщение (круглый войс с визуальной звуковой волной), в финальном ответе агента обязательно используйте директиву `[[audio_as_voice]]`:

```markdown
[[audio_as_voice]]
MEDIA:/home/ubuntu/.hermes/audio_cache/everything_as_code.ogg
```
