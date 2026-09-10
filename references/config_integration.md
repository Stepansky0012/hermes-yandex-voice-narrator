# Интеграция навыка в конфигурацию любого агента Hermes

Чтобы любой Hermes-агент мог использовать этот TTS-движок через стандартный инструмент `text_to_speech`:

### 1. Установка зависимостей
```bash
pip install websockets
# и убедиться, что установлен ffmpeg:
sudo apt-get install -y ffmpeg
```

### 2. Регистрация кастомного провайдера в `~/.hermes/config.yaml`
Добавьте в `~/.hermes/config.yaml`:
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

### 3. Проверка
Вызовите инструмент `text_to_speech`:
```python
text_to_speech(text="Привет! Навык успешно импортирован.")
```
