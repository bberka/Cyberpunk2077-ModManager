PYTHON ?= python

.PHONY: package-python release clean

package-python:
	pwsh -File ./scripts/package-python-release.ps1 -Version "$$(tr -d '[:space:]' < VERSION)"

release: package-python

clean:
	-$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['build','dist','__pycache__']]"
