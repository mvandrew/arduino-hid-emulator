import pyautogui
import time


class MouseController:
    """
    Класс для управления виртуальной мышью.
    """

    def __init__(self, arduino_connection, default_factor_x=1/3, default_factor_y=1/3):
        self.arduino = arduino_connection
        self.factor_x = default_factor_x
        self.factor_y = default_factor_y

    def mouse_direct(self, x, y):
        """
        Прямолинейное перемещение мыши на заданные координаты.

        :param x: Конечная координата по оси X.
        :param y: Конечная координата по оси Y.
        """
        # Получаем текущие координаты курсора
        current_x, current_y = pyautogui.position()

        # Вычисляем смещение
        delta_x = x - current_x
        delta_y = y - current_y

        while abs(delta_x) > 1 or abs(delta_y) > 1:
            # Формируем команду для Arduino
            command = f"mouse_move_direct {delta_x},{delta_y}"

            # Отправляем команду на устройство
            success = self.arduino.send_command(command)

            # Если команда не выполнена, прерываем выполнение
            if not success:
                raise RuntimeError(f"Ошибка выполнения команды: {command}")

            # Проверяем новое положение курсора
            time.sleep(0.1)  # Небольшая пауза для обновления положения
            current_x, current_y = pyautogui.position()

            # Вычисляем новое смещение
            delta_x = x - current_x
            delta_y = y - current_y

        print(f"Курсор успешно перемещён в точку ({x}, {y}).")

    def click(self, button="left"):
        """
        Нажимает и отпускает указанную кнопку мыши.
        """
        return self.arduino.send_command(f"mouse_click {button}")

    def press(self, button="left"):
        """
        Нажимает указанную кнопку мыши.
        """
        return self.arduino.send_command(f"mouse_down {button}")

    def release(self, button="left"):
        """
        Отпускает указанную кнопку мыши.
        """
        return self.arduino.send_command(f"mouse_up {button}")

    def calibrate(self):
        """
        Калибрует коэффициенты компенсации перемещения указателя.
        """
        print("Начинается калибровка...")

        # Получаем размеры экрана
        screen_width, screen_height = pyautogui.size()
        print(f"Размер экрана: {screen_width}x{screen_height}")

        # Устанавливаем начальные коэффициенты
        self.factor_x, self.factor_y = 1 / 3, 1 / 3

        for attempt in range(3):  # Повторяем 3 раза для уточнения коэффициентов
            print(f"Попытка {attempt + 1} из 3")

            # 1. Перемещаем курсор в центр экрана
            center_x, center_y = screen_width // 2, screen_height // 2
            pyautogui.moveTo(center_x, center_y)
            time.sleep(0.1)  # Даем курсору переместиться
            reference_x, reference_y = pyautogui.position()
            print(f"Курсор установлен в центр экрана: {reference_x}, {reference_y}")

            # 2. Перемещаем курсор на 50 пикселей по X и Y средствами Arduino
            self.mouse_direct(reference_x + 50, reference_y + 50)
            time.sleep(0.2)  # Даем время для обработки движения Arduino

            # 3. Фиксируем новые координаты курсора
            new_x, new_y = pyautogui.position()
            print(f"Новое положение курсора: {new_x}, {new_y}")

            # 4. Вычисляем фактическое смещение
            actual_move_x = new_x - reference_x
            actual_move_y = new_y - reference_y

            if actual_move_x == 0 or actual_move_y == 0:
                raise RuntimeError("Не удалось зафиксировать движение курсора. Проверьте соединение.")

            # 5. Обновляем коэффициенты поправки
            self.factor_x *= 50 / actual_move_x
            self.factor_y *= 50 / actual_move_y

            print(f"Обновлённые коэффициенты: factor_x = {self.factor_x}, factor_y = {self.factor_y}")

            # Проверяем точность перемещения
            error_x = abs(actual_move_x * self.factor_x - 50)
            error_y = abs(actual_move_y * self.factor_y - 50)

            if error_x <= 1 and error_y <= 1:
                print("Точность достигнута!")
                break
            else:
                print(f"Текущая ошибка: error_x = {error_x}, error_y = {error_y}")

        print(f"Финальные коэффициенты: factor_x = {self.factor_x}, factor_y = {self.factor_y}")

    def mouse_move(self, x, y, duration_min=500, duration_max=1500):
        """
        Плавное перемещение мыши на заданные координаты с указанной длительностью.

        :param x: Конечная координата по оси X.
        :param y: Конечная координата по оси Y.
        :param duration_min: Минимальная длительность перемещения в миллисекундах.
        :param duration_max: Максимальная длительность перемещения в миллисекундах.
        """
        if duration_min < 0 or duration_max < 0:
            raise ValueError("Длительность перемещения должна быть неотрицательной.")

        if duration_min > duration_max:
            raise ValueError("Минимальная длительность не может превышать максимальную.")

        # Получаем текущие координаты курсора
        current_x, current_y = pyautogui.position()

        # Вычисляем смещение
        delta_x = x - current_x
        delta_y = y - current_y

        while abs(delta_x) > 1 or abs(delta_y) > 1:
            # Формируем команду для Arduino
            command = f"mouse_move {delta_x},{delta_y},{self.factor_x},{self.factor_y},{duration_min},{duration_max}"

            # Отправляем команду на устройство
            success = self.arduino.send_command(command)

            # Если команда не выполнена, прерываем выполнение
            if not success:
                raise RuntimeError(f"Ошибка выполнения команды: {command}")

            # Проверяем новое положение курсора
            time.sleep(0.1)  # Небольшая пауза для обновления положения
            current_x, current_y = pyautogui.position()

            # Вычисляем новое смещение
            delta_x = x - current_x
            delta_y = y - current_y

            # Уменьшаем длительность для корректировок
            duration_min, duration_max = 50, 100

        print(f"Курсор успешно перемещён в точку ({x}, {y}).")
