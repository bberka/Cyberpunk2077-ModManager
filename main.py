import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Try to import PySide6 for the UI component
try:
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    UI_AVAILABLE = True
except ImportError:
    UI_AVAILABLE = False

# --- SETTINGS ---
SEVEN_ZIP_EXE = r"C:\Program Files\7-Zip\7z.exe"
CYBERPUNK_ROOTS = {"archive", "bin", "engine", "r6", "red4ext", "mods"}
MOD_EXTS = {".archive", ".xl"}
DOC_EXTS = {".txt", ".md", ".png", ".jpg", ".jpeg", ".pdf"}
STATE_FILE = "mods.json"
DEFAULT_MANAGER_WORKERS = 8

print_lock = threading.Lock()
file_write_lock = threading.Lock()


def safe_print(message, logger=None):
    with print_lock:
        print(message)
        if logger:
            logger.append_log.emit(message)


# --- SHARED HELPERS ---

def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def get_state_path(game_dir):
    return Path(game_dir) / STATE_FILE


def empty_state():
    return {"version": 1, "installed": [], "file_owners": {}}


def load_state(game_dir):
    path = get_state_path(game_dir)
    if not path.exists():
        return empty_state()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return empty_state()
        data.setdefault("version", 1)
        data.setdefault("installed", [])
        data.setdefault("file_owners", {})
        return data
    except Exception:
        return empty_state()


def save_state(game_dir, state):
    path = get_state_path(game_dir)
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def is_archive_file(path):
    return path.is_file() and path.suffix.lower() == ".zip"


def discover_available_items(mods_dir):
    base = Path(mods_dir)
    items = []
    if not base.is_dir():
        return items

    for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
        if is_archive_file(child):
            items.append({"name": child.name, "type": "mod", "path": str(child)})
        elif child.is_dir():
            zips = [z for z in sorted(child.glob("*.zip"), key=lambda p: p.name.lower()) if z.is_file()]
            if zips:
                items.append(
                    {
                        "name": child.name,
                        "type": "pack",
                        "path": str(child),
                        "archives": [str(z) for z in zips],
                    }
                )
    return items


def normalize_relpath(path_obj):
    return Path(path_obj).as_posix()


def make_install_id(item_type, item_name):
    return f"{item_type}:{item_name}"


# --- CORE EXTRACTION/INSTALL LOGIC ---

def extract_archive(archive_path, extract_dir, logger=None):
    if os.path.exists(SEVEN_ZIP_EXE):
        try:
            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                [SEVEN_ZIP_EXE, "x", f"-o{extract_dir}", str(archive_path), "-y"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            if result.returncode == 0:
                return True
        except Exception as e:
            safe_print(f"  [ERROR] 7-Zip failed for {archive_path.name}: {e}", logger)

    if zipfile.is_zipfile(archive_path):
        try:
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(extract_dir)
            return True
        except Exception:
            return False
    return False


def process_extracted_files(temp_dir, dest_dir, archive_name):
    temp_path = Path(temp_dir)
    dest_path = Path(dest_dir)
    copied_relpaths = []

    for file_path in temp_path.rglob("*"):
        if not file_path.is_file():
            continue

        parts = file_path.relative_to(temp_path).parts
        target_path = None
        root_idx = next((i for i, p in enumerate(parts) if p.lower() in CYBERPUNK_ROOTS), -1)

        if root_idx != -1:
            target_path = dest_path.joinpath(*parts[root_idx:])
        else:
            ext = file_path.suffix.lower()
            if ext in MOD_EXTS:
                target_path = dest_path / "archive" / "pc" / "mod" / file_path.name
            elif ext in DOC_EXTS:
                target_path = dest_path / "docs" / file_path.name
            else:
                target_path = dest_path / "other" / archive_name.rsplit(".", 1)[0] / Path(*parts)

        if target_path:
            with file_write_lock:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target_path)
            copied_relpaths.append(normalize_relpath(target_path.relative_to(dest_path)))

    return copied_relpaths


def install_archive_into_game(game_dir, archive_path, logger=None):
    with tempfile.TemporaryDirectory() as temp_dir:
        if not extract_archive(archive_path, temp_dir, logger):
            return False, []
        copied = process_extracted_files(temp_dir, game_dir, Path(archive_path).name)
        return True, copied


def install_one_archive_worker(game_dir, archive_path, logger=None):
    safe_print(f"  [ARCHIVE] {Path(archive_path).name}", logger)
    ok, copied = install_archive_into_game(game_dir, archive_path, logger)
    return Path(archive_path).name, ok, copied


# --- MANAGER LOGIC ---

def manager_list(game_dir, mods_dir=None, logger=None):
    gp = Path(game_dir)
    if not gp.is_dir():
        safe_print(f"[ERROR] Invalid game folder: {gp}", logger)
        return []

    state = load_state(gp)
    installed = state.get("installed", [])
    safe_print(f"Installed entries: {len(installed)}", logger)
    for entry in installed:
        safe_print(
            f"  - {entry.get('id')} [{entry.get('type')}] files={len(entry.get('files', []))}",
            logger,
        )

    if mods_dir:
        available = discover_available_items(mods_dir)
        safe_print(f"Available in '{mods_dir}': {len(available)}", logger)
        for item in available:
            if item["type"] == "pack":
                safe_print(f"  - {item['name']} [pack] zips={len(item.get('archives', []))}", logger)
            else:
                safe_print(f"  - {item['name']} [mod]", logger)
    return installed


def manager_install_item(game_dir, mods_dir, item_name, workers=DEFAULT_MANAGER_WORKERS, logger=None):
    gp = Path(game_dir)
    md = Path(mods_dir)
    if not gp.is_dir():
        safe_print(f"[ERROR] Invalid game folder: {gp}", logger)
        return False
    if not md.is_dir():
        safe_print(f"[ERROR] Invalid mods/download folder: {md}", logger)
        return False

    item_path = md / item_name
    if not item_path.exists():
        safe_print(f"[ERROR] Item not found in download folder: {item_name}", logger)
        return False

    if item_path.is_file() and item_path.suffix.lower() == ".zip":
        item_type = "mod"
        archives = [item_path]
    elif item_path.is_dir():
        archives = [z for z in sorted(item_path.glob("*.zip"), key=lambda p: p.name.lower()) if z.is_file()]
        if not archives:
            safe_print(f"[ERROR] Pack '{item_name}' has no .zip files at its root.", logger)
            return False
        item_type = "pack"
    else:
        safe_print(f"[ERROR] Unsupported item: {item_name}", logger)
        return False

    install_id = make_install_id(item_type, item_name)
    state = load_state(gp)
    if any(e.get("id") == install_id for e in state.get("installed", [])):
        safe_print(f"[INFO] '{install_id}' is already installed. Uninstall first if you want to reinstall.", logger)
        return False

    safe_print(f"Installing {install_id} into {gp}...", logger)
    all_copied = []
    workers = max(1, int(workers))
    effective_workers = min(workers, len(archives))
    safe_print(f"Install workers: requested={workers}, effective={effective_workers}", logger)

    if len(archives) == 1 or effective_workers == 1:
        for archive in archives:
            safe_print(f"  [ARCHIVE] {archive.name}", logger)
            ok, copied = install_archive_into_game(gp, archive, logger)
            if not ok:
                safe_print(f"  [FAILED] Could not extract {archive.name}", logger)
                return False
            all_copied.extend(copied)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as exe:
            futures = {
                exe.submit(install_one_archive_worker, gp, archive, logger): archive.name for archive in archives
            }
            for fut in concurrent.futures.as_completed(futures):
                archive_name, ok, copied = fut.result()
                if not ok:
                    safe_print(f"  [FAILED] Could not extract {archive_name}", logger)
                    return False
                safe_print(f"  [DONE] {archive_name} ({len(copied)} files)", logger)
                all_copied.extend(copied)

    unique_files = sorted(set(all_copied))

    entry = {
        "id": install_id,
        "type": item_type,
        "name": item_name,
        "source": str(item_path),
        "installed_at": now_utc_iso(),
        "archives": [a.name for a in archives],
        "files": unique_files,
    }
    state["installed"].append(entry)

    owners = state["file_owners"]
    for rel in unique_files:
        rel_owners = owners.setdefault(rel, [])
        if install_id not in rel_owners:
            rel_owners.append(install_id)

    save_state(gp, state)
    safe_print(f"Install complete: {install_id} ({len(unique_files)} files tracked)", logger)
    safe_print(f"State updated: {get_state_path(gp)}", logger)
    return True


def remove_empty_parents(start_dir, stop_dir):
    current = Path(start_dir)
    stop = Path(stop_dir)
    while current.exists() and current != stop:
        try:
            if any(current.iterdir()):
                break
            current.rmdir()
            current = current.parent
        except Exception:
            break


def manager_uninstall_item(game_dir, install_id, logger=None):
    gp = Path(game_dir)
    if not gp.is_dir():
        safe_print(f"[ERROR] Invalid game folder: {gp}", logger)
        return False

    state = load_state(gp)
    installed = state.get("installed", [])
    entry = next((e for e in installed if e.get("id") == install_id), None)
    if not entry:
        safe_print(f"[ERROR] Install id not found: {install_id}", logger)
        return False

    owners = state.get("file_owners", {})
    removed_files = 0

    safe_print(f"Uninstalling {install_id}...", logger)
    for rel in entry.get("files", []):
        rel_norm = normalize_relpath(rel)
        rel_owners = owners.get(rel_norm, [])
        if install_id in rel_owners:
            rel_owners.remove(install_id)

        if rel_owners:
            owners[rel_norm] = rel_owners
            continue

        owners.pop(rel_norm, None)
        target = gp / Path(rel_norm)
        if target.exists() and target.is_file():
            try:
                target.unlink()
                removed_files += 1
                safe_print(f"  [REMOVED] {rel_norm}", logger)
                remove_empty_parents(target.parent, gp)
            except Exception as e:
                safe_print(f"  [ERROR] Could not remove {rel_norm}: {e}", logger)

    state["installed"] = [e for e in installed if e.get("id") != install_id]
    state["file_owners"] = owners
    save_state(gp, state)

    safe_print(f"Uninstall complete: {install_id}, files deleted={removed_files}", logger)
    return True


def manager_reinstall_item(game_dir, install_id, workers=DEFAULT_MANAGER_WORKERS, logger=None):
    gp = Path(game_dir)
    if not gp.is_dir():
        safe_print(f"[ERROR] Invalid game folder: {gp}", logger)
        return False

    state = load_state(gp)
    entry = next((e for e in state.get("installed", []) if e.get("id") == install_id), None)
    if not entry:
        safe_print(f"[ERROR] Install id not found: {install_id}", logger)
        return False

    source = Path(entry.get("source", ""))
    if not source.exists():
        safe_print(
            f"[ERROR] Original source path missing for reinstall: {source}. "
            f"Restore it or reinstall manually from downloads.",
            logger,
        )
        return False

    safe_print(f"Reinstalling {install_id}...", logger)
    if not manager_uninstall_item(gp, install_id, logger):
        return False

    return manager_install_item(gp, source.parent, source.name, workers, logger)


def manager_wipe_all(game_path, logger=None):
    gp = Path(game_path)
    if not gp.is_dir():
        safe_print(f"[ERROR] Invalid game folder: {gp}", logger)
        return False

    state = load_state(gp)
    owners = state.get("file_owners", {})
    tracked_files = sorted(owners.keys())
    removed_files = 0

    safe_print(f"Wiping tracked mod files from state: {len(tracked_files)} entries", logger)
    for rel in tracked_files:
        target = gp / Path(rel)
        if target.exists() and target.is_file():
            try:
                target.unlink()
                removed_files += 1
                safe_print(f"  [REMOVED] {rel}", logger)
                remove_empty_parents(target.parent, gp)
            except Exception as e:
                safe_print(f"  [ERROR] Could not remove {rel}: {e}", logger)

    save_state(gp, empty_state())
    safe_print(f"Wipe complete: deleted={removed_files}, state reset={get_state_path(gp)}", logger)
    return True


# --- EXISTING COMMAND HANDLERS (PRESERVED) ---

def run_extract(input_path, output_path, workers, logger=None):
    input_dir = Path(input_path)
    dest_dir = Path(output_path)
    if not input_dir.is_dir():
        safe_print(f"Error: Input directory {input_dir} not found.", logger)
        return

    for f in list(CYBERPUNK_ROOTS) + ["docs", "other", "archive/pc/mod"]:
        (dest_dir / f).mkdir(parents=True, exist_ok=True)

    files = [f for f in input_dir.iterdir() if f.is_file()]
    safe_print(f"Processing {len(files)} files using {workers} workers...\n", logger)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as exe:
        futures = {exe.submit(worker_process_mod, f, dest_dir, logger): f for f in files}
        for fut in concurrent.futures.as_completed(futures):
            name, success = fut.result()
            status = "SUCCESS" if success else "FAILED"
            safe_print(f"  [{status}] {name}", logger)


def worker_process_mod(item, dest_dir, logger=None):
    safe_print(f"Starting: {item.name}", logger)
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            if extract_archive(item, temp_dir, logger):
                process_extracted_files(temp_dir, dest_dir, item.name)
                return item.name, True
            return item.name, False
    except Exception:
        return item.name, False


def run_clear(game_path, logger=None):
    gp = Path(game_path)
    targets = [
        gp / "red4ext",
        gp / "mods",
        gp / "archive" / "pc" / "mod",
        gp / "bin" / "x64" / "plugins",
        gp / "bin" / "x64" / "version.dll",
        gp / "bin" / "x64" / "winmm.dll",
        gp / "bin" / "x64" / "global.ini",
        gp / "r6" / "scripts",
        gp / "r6" / "tweaks",
        gp / "r6" / "cache" / "modded",
    ]
    safe_print(f"Cleaning: {gp}", logger)
    for item in targets:
        if item.exists():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                    safe_print(f"  [REMOVED] Folder: {item.relative_to(gp)}", logger)
                else:
                    item.unlink()
                    safe_print(f"  [REMOVED] File: {item.relative_to(gp)}", logger)
            except Exception as e:
                safe_print(f"  [ERROR] Could not delete {item}: {e}", logger)
    safe_print("Clean complete.", logger)


def run_uninstall(game_path, mod_path, logger=None):
    gp = Path(game_path)
    mp = Path(mod_path)

    if not gp.is_dir() or not mp.is_dir():
        safe_print("[ERROR] Invalid game or mod pack directory.", logger)
        return

    safe_print(f"Uninstalling specific mods from {gp}...", logger)
    touched_dirs = set()

    for item in mp.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(mp)
            target_file = gp / rel_path

            if target_file.exists():
                try:
                    target_file.unlink()
                    safe_print(f"  [DELETED] {rel_path}", logger)
                    touched_dirs.add(target_file.parent)
                except Exception as e:
                    safe_print(f"  [ERROR] Failed to delete {rel_path}: {e}", logger)

    for d in sorted(touched_dirs, key=lambda p: len(p.parts), reverse=True):
        try:
            if d.exists() and not any(d.iterdir()) and d != gp:
                d.rmdir()
                safe_print(f"  [CLEANED] Empty folder: {d.relative_to(gp)}", logger)
        except Exception:
            pass

    safe_print("Uninstall complete.", logger)


# --- GUI CLASSES ---

if UI_AVAILABLE:

    class WorkerThread(QThread):
        append_log = Signal(str)
        finished_sig = Signal()

        def __init__(self, mode, params):
            super().__init__()
            self.mode = mode
            self.params = params

        def run(self):
            if self.mode == "extract":
                run_extract(self.params["i"], self.params["o"], self.params["w"], self)
            elif self.mode == "clear":
                run_clear(self.params["p"], self)
            elif self.mode == "uninstall_template":
                run_uninstall(self.params["p"], self.params["m"], self)
            elif self.mode == "manager_install":
                manager_install_item(
                    self.params["g"],
                    self.params["d"],
                    self.params["item"],
                    self.params.get("w", DEFAULT_MANAGER_WORKERS),
                    self,
                )
            elif self.mode == "manager_reinstall":
                manager_reinstall_item(
                    self.params["g"],
                    self.params["id"],
                    self.params.get("w", DEFAULT_MANAGER_WORKERS),
                    self,
                )
            elif self.mode == "manager_uninstall":
                manager_uninstall_item(self.params["g"], self.params["id"], self)
            elif self.mode == "manager_wipe":
                manager_wipe_all(self.params["g"], self)
            self.finished_sig.emit()


    class CyberModUI(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Cyberpunk 2077 Mod Manager")
            self.setMinimumSize(900, 620)

            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)

            tabs = QTabWidget()
            layout.addWidget(tabs)

            # Manager Tab (main workflow)
            manager_tab = QWidget()
            tabs.addTab(manager_tab, "Mod Manager")
            m_layout = QVBoxLayout(manager_tab)

            info = QLabel(
                "Main workflow: set your game folder and download folder, then install single mods (.zip) or"
                " mod packs (folder that contains .zip files at root). Installed items are tracked in"
                " mods.json in your game folder for safe uninstall and wipe operations. Tip: selecting an"
                " installed item and clicking Install runs a reinstall/repair."
            )
            info.setWordWrap(True)
            m_layout.addWidget(info)

            self.mgr_game_edit = self.add_path_row(m_layout, "Game Folder:")
            self.mgr_mods_edit = self.add_path_row(m_layout, "Download Folder:")
            mgr_w_layout = QHBoxLayout()
            mgr_w_layout.addWidget(QLabel("Install Workers:"))
            self.mgr_worker_spin = QSpinBox()
            self.mgr_worker_spin.setMinimum(1)
            self.mgr_worker_spin.setMaximum(64)
            self.mgr_worker_spin.setValue(DEFAULT_MANAGER_WORKERS)
            mgr_w_layout.addWidget(self.mgr_worker_spin)
            m_layout.addLayout(mgr_w_layout)

            list_row = QHBoxLayout()
            left = QVBoxLayout()
            right = QVBoxLayout()
            left.addWidget(QLabel("Available Mods / Packs"))
            right.addWidget(QLabel("Installed (tracked in mods.json)"))

            self.available_list = QListWidget()
            self.installed_list = QListWidget()
            left.addWidget(self.available_list)
            right.addWidget(self.installed_list)
            list_row.addLayout(left)
            list_row.addLayout(right)
            m_layout.addLayout(list_row)

            btn_row = QHBoxLayout()
            self.btn_refresh = QPushButton("Refresh Lists")
            self.btn_refresh.clicked.connect(self.refresh_manager_lists)
            self.btn_install_item = QPushButton("Install Selected")
            self.btn_install_item.clicked.connect(self.start_manager_install)
            self.btn_uninstall_item = QPushButton("Uninstall Selected")
            self.btn_uninstall_item.clicked.connect(self.start_manager_uninstall)
            self.btn_manager_wipe = QPushButton("Wipe All Mods")
            self.btn_manager_wipe.clicked.connect(self.start_manager_wipe)
            btn_row.addWidget(self.btn_refresh)
            btn_row.addWidget(self.btn_install_item)
            btn_row.addWidget(self.btn_uninstall_item)
            btn_row.addWidget(self.btn_manager_wipe)
            m_layout.addLayout(btn_row)

            # Extract Tab
            extract_tab = QWidget()
            tabs.addTab(extract_tab, "Extract Mods")
            ex_layout = QVBoxLayout(extract_tab)

            ex_info = QLabel(
                "Legacy extraction flow: takes archives from input folder and creates a structured output"
                " directory (archive/bin/r6/red4ext/mods/docs/other)."
            )
            ex_info.setWordWrap(True)
            ex_layout.addWidget(ex_info)

            self.in_edit = self.add_path_row(ex_layout, "Input Folder:")
            self.out_edit = self.add_path_row(ex_layout, "Output Folder:")

            w_layout = QHBoxLayout()
            w_layout.addWidget(QLabel("Workers:"))
            self.worker_spin = QSpinBox()
            self.worker_spin.setValue(3)
            self.worker_spin.setMinimum(1)
            self.worker_spin.setMaximum(32)
            w_layout.addWidget(self.worker_spin)
            ex_layout.addLayout(w_layout)

            self.btn_extract = QPushButton("Run Extraction")
            self.btn_extract.clicked.connect(self.start_extract)
            ex_layout.addWidget(self.btn_extract)

            # Uninstall Specific Template Tab
            uninstall_tab = QWidget()
            tabs.addTab(uninstall_tab, "Uninstall From Template")
            un_layout = QVBoxLayout(uninstall_tab)

            un_info = QLabel(
                "Legacy uninstall flow: remove files from game directory using an already extracted"
                " mod folder as the template."
            )
            un_info.setWordWrap(True)
            un_layout.addWidget(un_info)

            self.un_game_edit = self.add_path_row(un_layout, "Game Folder:")
            self.un_mod_edit = self.add_path_row(un_layout, "Extracted Mod Folder:")

            self.btn_uninstall = QPushButton("Uninstall Specific Mod Files")
            self.btn_uninstall.clicked.connect(self.start_uninstall)
            un_layout.addWidget(self.btn_uninstall)

            # Clear All Mods Tab
            clear_tab = QWidget()
            tabs.addTab(clear_tab, "Wipe (Legacy Clear)")
            cl_layout = QVBoxLayout(clear_tab)

            cl_info = QLabel(
                "Legacy clear flow: remove known mod/framework folders from game folder."
                " Use Mod Manager wipe for tracked state reset as well."
            )
            cl_info.setWordWrap(True)
            cl_layout.addWidget(cl_info)

            self.game_edit = self.add_path_row(cl_layout, "Game Folder:")
            self.btn_clear = QPushButton("Wipe All Mods")
            self.btn_clear.clicked.connect(self.start_clear)
            cl_layout.addWidget(self.btn_clear)

            # Log area
            self.log_display = QTextEdit()
            self.log_display.setReadOnly(True)
            self.log_display.setStyleSheet(
                "background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace;"
            )
            layout.addWidget(self.log_display)

        def add_path_row(self, layout, label_text):
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            edit = QLineEdit()
            row.addWidget(edit)
            btn = QPushButton("Browse")
            btn.clicked.connect(lambda: edit.setText(QFileDialog.getExistingDirectory()))
            row.addWidget(btn)
            layout.addLayout(row)
            return edit

        def start_extract(self):
            params = {"i": self.in_edit.text(), "o": self.out_edit.text(), "w": self.worker_spin.value()}
            self.run_thread("extract", params)

        def start_clear(self):
            self.run_thread("clear", {"p": self.game_edit.text()})

        def start_uninstall(self):
            self.run_thread("uninstall_template", {"p": self.un_game_edit.text(), "m": self.un_mod_edit.text()})

        def refresh_manager_lists(self):
            game = self.mgr_game_edit.text().strip()
            mods_dir = self.mgr_mods_edit.text().strip()

            self.available_list.clear()
            self.installed_list.clear()

            if mods_dir and Path(mods_dir).is_dir():
                for item in discover_available_items(mods_dir):
                    if item["type"] == "pack":
                        label = f"{item['name']} [pack, {len(item.get('archives', []))} zips]"
                    else:
                        label = f"{item['name']} [mod]"
                    lw_item = QListWidgetItem(label)
                    lw_item.setData(Qt.UserRole, item["name"])
                    self.available_list.addItem(lw_item)

            if game and Path(game).is_dir():
                state = load_state(game)
                for entry in state.get("installed", []):
                    label = f"{entry.get('id')} ({len(entry.get('files', []))} files)"
                    lw_item = QListWidgetItem(label)
                    lw_item.setData(Qt.UserRole, entry.get("id"))
                    self.installed_list.addItem(lw_item)

        def start_manager_install(self):
            game = self.mgr_game_edit.text().strip()
            mods_dir = self.mgr_mods_edit.text().strip()
            selected_available = self.available_list.currentItem()
            if selected_available:
                item_name = selected_available.data(Qt.UserRole)
                self.run_thread(
                    "manager_install",
                    {"g": game, "d": mods_dir, "item": item_name, "w": self.mgr_worker_spin.value()},
                )
                return

            selected_installed = self.installed_list.currentItem()
            if selected_installed:
                install_id = selected_installed.data(Qt.UserRole)
                self.run_thread(
                    "manager_reinstall",
                    {"g": game, "id": install_id, "w": self.mgr_worker_spin.value()},
                )
                return

            QMessageBox.warning(
                self,
                "Missing Selection",
                "Select a mod/pack from Available to install, or an entry from Installed to reinstall/repair.",
            )

        def start_manager_uninstall(self):
            game = self.mgr_game_edit.text().strip()
            selected = self.installed_list.currentItem()
            if not selected:
                QMessageBox.warning(self, "Missing Selection", "Select an installed item to uninstall.")
                return
            install_id = selected.data(Qt.UserRole)
            self.run_thread("manager_uninstall", {"g": game, "id": install_id})

        def start_manager_wipe(self):
            game = self.mgr_game_edit.text().strip()
            ans = QMessageBox.question(
                self,
                "Confirm Wipe",
                "This will remove known mod folders/files and reset mods.json tracking. Continue?",
            )
            if ans == QMessageBox.StandardButton.Yes:
                self.run_thread("manager_wipe", {"g": game})

        def run_thread(self, mode, params):
            self.log_display.clear()
            self.toggle_ui(False)
            self.thread = WorkerThread(mode, params)
            self.thread.append_log.connect(lambda msg: self.log_display.append(msg))
            self.thread.finished_sig.connect(self.on_thread_finished)
            self.thread.start()

        def on_thread_finished(self):
            self.toggle_ui(True)
            self.refresh_manager_lists()

        def toggle_ui(self, enabled):
            self.btn_extract.setEnabled(enabled)
            self.btn_clear.setEnabled(enabled)
            self.btn_uninstall.setEnabled(enabled)
            self.btn_refresh.setEnabled(enabled)
            self.btn_install_item.setEnabled(enabled)
            self.btn_uninstall_item.setEnabled(enabled)
            self.btn_manager_wipe.setEnabled(enabled)


# --- MAIN ENTRY ---

def build_parser():
    parser = argparse.ArgumentParser(description="Cyberpunk 2077 Mod Utility")
    subparsers = parser.add_subparsers(dest="command", required=False)

    # Command: ui
    subparsers.add_parser("ui", help="Run the Graphical User Interface.")
    subparsers.add_parser("gui", help="Alias for 'ui'.")

    # Command: extract
    ext_parser = subparsers.add_parser("extract", help="Extract and structure mods.")
    ext_parser.add_argument("-i", "--input", required=True)
    ext_parser.add_argument("-o", "--output", required=True)
    ext_parser.add_argument("-w", "--workers", type=int, default=3)

    # Command: clear
    clr_parser = subparsers.add_parser("clear", help="Wipe known mod folders/files from the game folder.")
    clr_parser.add_argument("-p", "--path", required=True)

    # Command: uninstall (legacy template)
    un_parser = subparsers.add_parser(
        "uninstall",
        help="Remove specific mod files using an extracted template folder.",
    )
    un_parser.add_argument("-p", "--path", required=True, help="Path to Cyberpunk 2077 game folder.")
    un_parser.add_argument("-m", "--modpack", required=True, help="Path to extracted mod pack structure.")

    # Manager commands
    lst_parser = subparsers.add_parser("manager-list", help="List installed entries and optional available items.")
    lst_parser.add_argument("-g", "--game", required=True, help="Path to Cyberpunk 2077 game folder.")
    lst_parser.add_argument("-d", "--downloads", required=False, help="Path to downloaded mods/modpacks folder.")

    ins_parser = subparsers.add_parser("manager-install", help="Install one mod zip or one mod pack directory.")
    ins_parser.add_argument("-g", "--game", required=True, help="Path to Cyberpunk 2077 game folder.")
    ins_parser.add_argument("-d", "--downloads", required=True, help="Path to downloaded mods/modpacks folder.")
    ins_parser.add_argument("-n", "--name", required=True, help="File or directory name inside downloads folder.")
    ins_parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=DEFAULT_MANAGER_WORKERS,
        help=f"Concurrent zip installers for pack installs (default: {DEFAULT_MANAGER_WORKERS}).",
    )

    uins_parser = subparsers.add_parser("manager-uninstall", help="Uninstall one tracked mod/pack by id.")
    uins_parser.add_argument("-g", "--game", required=True, help="Path to Cyberpunk 2077 game folder.")
    uins_parser.add_argument("-i", "--id", required=True, help="Install id, e.g. mod:M3 GTR-9871-1-03-1697184904.zip")

    wipe_parser = subparsers.add_parser("manager-wipe", help="Wipe all known mod files and reset mods.json.")
    wipe_parser.add_argument("-g", "--game", required=True, help="Path to Cyberpunk 2077 game folder.")

    return parser


def launch_ui():
    if not UI_AVAILABLE:
        print("[ERROR] PySide6 not found. Run 'pip install PySide6' to use the GUI.")
        return
    app = QApplication(sys.argv)
    window = CyberModUI()
    window.show()
    sys.exit(app.exec())


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command in {"ui", "gui"}:
        launch_ui()
    elif args.command == "extract":
        run_extract(args.input, args.output, args.workers)
    elif args.command == "clear":
        ans = input(f"Are you sure you want to wipe mods in {args.path}? (y/n): ")
        if ans.lower() == "y":
            run_clear(args.path)
    elif args.command == "uninstall":
        run_uninstall(args.path, args.modpack)
    elif args.command == "manager-list":
        manager_list(args.game, args.downloads)
    elif args.command == "manager-install":
        manager_install_item(args.game, args.downloads, args.name, args.workers)
    elif args.command == "manager-uninstall":
        manager_uninstall_item(args.game, args.id)
    elif args.command == "manager-wipe":
        ans = input(
            f"Are you sure you want to wipe all mods and reset '{STATE_FILE}' in {args.game}? (y/n): "
        )
        if ans.lower() == "y":
            manager_wipe_all(args.game)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
