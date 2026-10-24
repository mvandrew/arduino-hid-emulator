from setuptools import setup, find_packages
import pathlib

# Путь к README-RU.md
here = pathlib.Path(__file__).parent.resolve()
readme_path = here / "README.md"

# Чтение описания с указанием кодировки
with open(readme_path, encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="arduino-hid-emulator",
    version="1.1.0",
    description="A Python library for controlling Arduino HID devices",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Andrey Mishchenko",
    author_email="msav@msav.ru",
    url="https://github.com/mvandrew/arduino-hid-emulator",
    packages=find_packages(include=["arduino_hid_emulator", "arduino_hid_emulator.*"]),
    install_requires=[
        "pyserial==3.5",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    extras_require={"legacy-mouse": ["pyautogui==0.9.54"], "test": ["pytest>=8,<10"]},
)
