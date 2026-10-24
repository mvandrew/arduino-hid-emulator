# Arduino HID Emulator 1.0.0

Новая библиотека и прошивка реализуют ограниченный HID v1 для Arduino Leonardo.
Явный порт, CRC, session/id/generation, подтверждение завершения, отмена,
освобождение клавиш, heartbeat lease и аппаратный watchdog описаны в
[основной инструкции](README.md) и [контракте](docs/protocol-v1.md).

Это несовместимое изменение wire-протокола: старые команды True/False не
исполняются новой прошивкой. Старый скетч сохранён в `arduino/legacy_hid_emulator/`;
старые Python-классы требуют явных `port="COM3", legacy=True`, для мыши отдельно
устанавливается extra `legacy-mouse`. Автоматического fallback нет.

Python >=3.10, проверен 3.12.14 / Windows 11; Leonardo COM3, AVR core 1.8.8,
Arduino CLI 1.5.1. Поддержка других плат raw-драйвером не заявляется.

Обычный запуск примера выполняет только handshake:

```powershell
python -m pip install -e .
python examples/hid_v1.py --port COM3
```

Реальный ввод и загрузка платы выполняются только явно указанными командами
основной инструкции. Приложение отдельно отвечает за раскладки ОС, Unicode,
файлы и ритм набора; эти функции в библиотеку и прошивку не перенесены.
