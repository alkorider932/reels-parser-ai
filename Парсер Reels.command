#!/bin/bash

PROJECT_DIR="$HOME/Desktop/VS CODE/transckription-cleaner"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python3"
SCRIPT_PATH="$PROJECT_DIR/analyze_competitor.py"

# Нативное диалоговое окно macOS для ввода ссылки/ника
URL=$(osascript -e '
tell application "System Events"
    activate
    set userInput to text returned of (display dialog "Вставьте ссылку на профиль Instagram или никнейм:" default answer "" with title "🎬 Запуск AI-Парсера Reels" buttons {"Отмена", "Запустить анализ"} default button "Запустить анализ")
end tell
userInput
')

# Проверка на отмену или пустой ввод
if [ -z "$URL" ]; then
    echo "Отменено."
    exit 0
fi

# Если передан просто никнейм (например, 'username' или '@username'), приводим к полному URL
if [[ ! "$URL" =~ ^https?:// ]]; then
    CLEAN_USER=$(echo "$URL" | tr -d '@' | tr -d ' ')
    URL="https://www.instagram.com/$CLEAN_USER/"
fi

echo "=========================================="
echo "🚀 Запуск анализа: $URL"
echo "=========================================="

# Переходим в рабочую папку и запускаем скрипт
cd "$PROJECT_DIR" || exit 1
"$PYTHON_BIN" "$SCRIPT_PATH" "$URL"

# Уведомление и открытие папки с результатом
if [ $? -eq 0 ]; then
    afplay /System/Library/Sounds/Glass.aiff &
    osascript -e 'display notification "Анализ завершен! Открываю папку с отчетом." with title "🎬 Готово"'
    open "$PROJECT_DIR/outputs"
else
    afplay /System/Library/Sounds/Basso.aiff &
    osascript -e 'display alert "Ошибка при выполнении парсера. Проверьте лог в окне терминала."'
fi

echo ""
echo "Нажмите Enter для закрытия окна..."
read -r
