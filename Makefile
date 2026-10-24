# Makefile для управления публикацией пакета arduino-hid-emulator

PACKAGE_NAME = arduino-hid-emulator
PYPI_REPO = pypi
TEST_PYPI_REPO = testpypi
DIST_DIR = dist

.PHONY: all clean build test-publish publish test test-install
PYTHON ?= python

# Очистка старых сборок
clean:
	rm -rf $(DIST_DIR) build *.egg-info

# Сборка пакета
build: clean
	python setup.py sdist bdist_wheel

# Публикация в TestPyPI
test-publish: build
	twine upload --repository $(TEST_PYPI_REPO) $(DIST_DIR)/*

# Публикация в PyPI
publish: build
	twine upload --repository $(PYPI_REPO) $(DIST_DIR)/*

# Тестовая установка из TestPyPI
test-install:
	pip install --index-url https://test.pypi.org/simple/ --no-deps $(PACKAGE_NAME)

# Локальные проверки не публикуют пакет и не удаляют артефакты.
test:
	$(PYTHON) -m pytest -q
