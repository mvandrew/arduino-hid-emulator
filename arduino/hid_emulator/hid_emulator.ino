#include <Keyboard.h>
#include <Mouse.h>
#include <math.h>

// Интервалы для выполнения действий с клавиатурой и мышью
#define KEY_INTERVAL_MIN 150  // Минимальный интервал (мс)
#define KEY_INTERVAL_MAX 300  // Максимальный интервал (мс)
#define MOUSE_MOVE_DURATION_MIN 500  // Минимальная продолжительность движения мыши (мс)
#define MOUSE_MOVE_DURATION_MAX 1500 // Максимальная продолжительность движения мыши (мс)

void setup() {
    Keyboard.begin();   // Инициализация HID клавиатуры
    Mouse.begin();      // Инициализация HID мыши
    Serial.begin(9600); // Устанавливаем соединение для взаимодействия с Python
}

void loop() {
    // Проверяем, есть ли входящие команды через последовательный порт
    if (Serial.available() > 0) {
        String command = Serial.readStringUntil('\n'); // Читаем команду до символа новой строки
        bool result = processCommand(command);        // Обрабатываем команду
        Serial.println(result ? "True" : "False");    // Возвращаем результат выполнения команды
    }
}

// Обработка команды прямолинейного движения мыши
bool handleMouseMoveDirect(String params) {
    int sep = params.indexOf(','); // Определяем позицию разделителя (запятая)
    if (sep == -1) return false;   // Если запятая отсутствует, возвращаем false

    // Парсим координаты X и Y из строки
    int targetX = params.substring(0, sep).toInt();
    int targetY = params.substring(sep + 1).toInt();

    // Перемещаем мышь на указанные координаты без задержек
    Mouse.move(targetX, targetY);
    return true;
}

// Обработка входящих команд
bool processCommand(String command) {
    // Определяем тип команды и вызываем соответствующую функцию
    if (command.startsWith("mouse_move_direct ")) {
        return handleMouseMoveDirect(command.substring(18));
    } else if (command.startsWith("key_down ")) {
        char key = parseKey(command.substring(9));
        delay(random(KEY_INTERVAL_MIN, KEY_INTERVAL_MAX)); // Задержка перед нажатием
        Keyboard.press(key);
        return true;
    } else if (command.startsWith("key_up ")) {
        char key = parseKey(command.substring(7));
        delay(random(KEY_INTERVAL_MIN, KEY_INTERVAL_MAX)); // Задержка перед отпусканием
        Keyboard.release(key);
        return true;
    } else if (command.startsWith("key_press ")) {
        char key = parseKey(command.substring(10));
        delay(random(KEY_INTERVAL_MIN, KEY_INTERVAL_MAX)); // Задержка перед нажатием
        Keyboard.press(key);
        delay(random(KEY_INTERVAL_MIN, KEY_INTERVAL_MAX)); // Задержка между нажатием и отпусканием
        Keyboard.release(key);
        return true;
    } else if (command.startsWith("key_combo ")) {
        return handleKeyCombo(command.substring(10));
    } else if (command.startsWith("mouse_move ")) {
        return handleMouseMove(command.substring(11));
    } else if (command.startsWith("mouse_down ")) {
        return handleMousePress(command.substring(11), true);
    } else if (command.startsWith("mouse_up ")) {
        return handleMousePress(command.substring(9), false);
    } else if (command.startsWith("mouse_click ")) {
        return handleMouseClick(command.substring(12));
    }
    return false; // Если команда не распознана, возвращаем false
}

// Преобразование строки в символ клавиши
char parseKey(String keyStr) {
    keyStr.trim(); // Удаляем пробелы в начале и конце строки
    // Проверяем на совпадение с известными клавишами
    if (keyStr == "ctrl") return KEY_LEFT_CTRL;
    if (keyStr == "shift") return KEY_LEFT_SHIFT;
    if (keyStr == "alt") return KEY_LEFT_ALT;
    if (keyStr == "tab") return KEY_TAB;
    if (keyStr == "enter") return KEY_RETURN;
    if (keyStr == "space") return ' ';
    if (keyStr.startsWith("0x")) return strtol(keyStr.c_str(), NULL, 16);
    return keyStr[0]; // Если символ не распознан, возвращаем первый символ строки
}

// Обработка комбинации клавиш, например "ctrl+tab"
bool handleKeyCombo(String combo) {
    // Разбиваем строку по символу '+'
    int keysCount = 0;
    int keys[10]; // Максимум 10 клавиш в комбинации
    int lastPos = 0;

    while (true) {
        int idx = combo.indexOf('+', lastPos);
        if (idx == -1) {
            // Добавляем последнюю клавишу
            String keyStr = combo.substring(lastPos);
            keys[keysCount++] = parseKey(keyStr);
            break;
        }

        // Добавляем очередную клавишу
        String keyStr = combo.substring(lastPos, idx);
        keys[keysCount++] = parseKey(keyStr);
        lastPos = idx + 1;

        if (keysCount >= 10) break; // Защита от переполнения
    }

    // Нажимаем все клавиши по порядку
    for (int i = 0; i < keysCount; i++) {
        Keyboard.press(keys[i]);
        delay(random(KEY_INTERVAL_MIN, KEY_INTERVAL_MAX));
    }

    // Отпускаем в обратном порядке
    for (int i = keysCount - 1; i >= 0; i--) {
        Keyboard.release(keys[i]);
        delay(random(KEY_INTERVAL_MIN, KEY_INTERVAL_MAX));
    }

    return true;
}

// Плавное движение мыши по кривой Безье
bool handleMouseMove(String params) {
    // Определяем позиции разделителей в строке параметров
    int paramX = params.indexOf(',');
    if (paramX == -1) return false;

    int paramY = params.indexOf(',', paramX + 1);
    if (paramY == -1) return false;

    int paramFactorX = params.indexOf(',', paramY + 1);
    if (paramFactorX == -1) return false;

    int paramFactorY = params.indexOf(',', paramFactorX + 1);
    int paramDurationMin = params.indexOf(',', paramFactorY + 1);
    int paramDurationMax = params.indexOf(',', paramDurationMin + 1);

    // Извлекаем параметры из строки
    int targetX = params.substring(0, paramX).toInt(); // Смещение по X
    int targetY = params.substring(paramX + 1, paramY).toInt(); // Смещение по Y
    float factorX = params.substring(paramY + 1, paramFactorX).toFloat(); // Коэффициент для X
    float factorY = params.substring(paramFactorX + 1, paramFactorY == -1 ? params.length() : paramFactorY).toFloat(); // Коэффициент для Y

    // Устанавливаем диапазон длительности перемещения
    unsigned long durationMin = MOUSE_MOVE_DURATION_MIN; // Минимальная длительность
    unsigned long durationMax = MOUSE_MOVE_DURATION_MAX; // Максимальная длительность

    // Если указан только один параметр для длительности, используем фиксированное значение
    if (paramFactorY != -1 && paramDurationMin == -1) {
        durationMin = durationMax = params.substring(paramFactorY + 1).toInt();
    } 
    // Если заданы два параметра для диапазона длительности
    else if (paramFactorY != -1 && paramDurationMin != -1) {
        durationMin = params.substring(paramFactorY + 1, paramDurationMin).toInt();
        durationMax = paramDurationMax != -1 ? params.substring(paramDurationMin + 1, paramDurationMax).toInt()
                                             : params.substring(paramDurationMin + 1).toInt();
    }

    // Вычисляем длительность перемещения
    unsigned long duration = (durationMin == durationMax) ? durationMin : random(durationMin, durationMax);

    // Применяем коэффициенты к целевым координатам
    targetX = round(targetX * factorX);
    targetY = round(targetY * factorY);

    // Если конечная цель (0,0), отменяем движение
    if (targetX == 0 && targetY == 0) {
        return false;
    }

    int steps = 100; // Количество шагов для плавности движения

    // Начальные координаты
    int currentX = 0, currentY = 0;

    // Вычисляем параметры кривой Безье
    float deltaX = targetX - currentX;
    float deltaY = targetY - currentY;
    float distance = sqrt(deltaX * deltaX + deltaY * deltaY);
    float bezierOffset = distance * 0.2; // Смещение для контрольных точек

    float normalX = -deltaY / distance; // Нормализованное направление по X
    float normalY = deltaX / distance;  // Нормализованное направление по Y

    int controlPoint1X = targetX / 3 + normalX * bezierOffset;
    int controlPoint1Y = targetY / 3 + normalY * bezierOffset;
    int controlPoint2X = 2 * targetX / 3 - normalX * bezierOffset;
    int controlPoint2Y = 2 * targetY / 3 - normalY * bezierOffset;

    // Плавное движение по кривой Безье
    for (int i = 1; i <= steps; i++) {
        float t = (float)i / steps;
        int bezierX = round((1 - t) * (1 - t) * (1 - t) * 0 +
                            3 * (1 - t) * (1 - t) * t * controlPoint1X +
                            3 * (1 - t) * t * t * controlPoint2X +
                            t * t * t * targetX);
        int bezierY = round((1 - t) * (1 - t) * (1 - t) * 0 +
                            3 * (1 - t) * (1 - t) * t * controlPoint1Y +
                            3 * (1 - t) * t * t * controlPoint2Y +
                            t * t * t * targetY);

        int moveX = bezierX - currentX;
        int moveY = bezierY - currentY;

        currentX += moveX;
        currentY += moveY;

        if ((moveX > 0 && currentX > targetX) || (moveX < 0 && currentX < targetX)) {
            currentX = targetX;
            moveX = 0;
        }
        if ((moveY > 0 && currentY > targetY) || (moveY < 0 && currentY < targetY)) {
            currentY = targetY;
            moveY = 0;
        }

        Mouse.move(moveX, moveY);
        delay(duration / steps);
    }

    // Финальная коррекция для точного достижения цели
    int remainingX = targetX - currentX;
    int remainingY = targetY - currentY;
    int correctionSteps = 20;

    for (int i = 0; i < correctionSteps; i++) {
        int stepX = remainingX / correctionSteps;
        int stepY = remainingY / correctionSteps;
        Mouse.move(stepX, stepY);
        remainingX -= stepX;
        remainingY -= stepY;
        delay(200 / correctionSteps);
    }

    return true;
}

// Нажатие или отпускание кнопок мыши
bool handleMousePress(String button, bool isDown) {
    delay(random(KEY_INTERVAL_MIN, KEY_INTERVAL_MAX));
    if (button == "left") {
        if (isDown) Mouse.press(MOUSE_LEFT);
        else Mouse.release(MOUSE_LEFT);
    } else if (button == "right") {
        if (isDown) Mouse.press(MOUSE_RIGHT);
        else Mouse.release(MOUSE_RIGHT);
    }
    return true;
}

// Имитация клика мыши
bool handleMouseClick(String button) {
    return handleMousePress(button, true) && handleMousePress(button, false);
}
