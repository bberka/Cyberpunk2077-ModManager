PYTHON ?= python

.PHONY: build-cli build-gui build-all clean

build-cli:
	$(PYTHON) -m PyInstaller --noconfirm --clean --onefile --name cp77mm-cli cli_entry.py

build-gui:
	$(PYTHON) -m PyInstaller --noconfirm --clean --windowed --onefile --name cp77mm-gui gui_entry.py

build-all: build-cli build-gui

clean:
	-$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['build','dist','__pycache__']]"
	-$(PYTHON) -c "import pathlib; [p.unlink(missing_ok=True) for p in pathlib.Path('.').glob('*.spec')]"
