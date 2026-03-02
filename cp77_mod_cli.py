import os
import shutil
import argparse
import subprocess
import zipfile
import tempfile
import concurrent.futures
import threading
import sys
from pathlib import Path

# Try to import PySide6 for the UI component
try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QPushButton, QLabel, QLineEdit, QFileDialog, QTextEdit, QSpinBox, QTabWidget
    )
    from PySide6.QtCore import Qt, QThread, Signal
    UI_AVAILABLE = True
except ImportError:
    UI_AVAILABLE = False

# --- SETTINGS ---
SEVEN_ZIP_EXE = r"C:\Program Files\7-Zip\7z.exe"
CYBERPUNK_ROOTS = {"archive", "bin", "engine", "r6", "red4ext", "mods"}
MOD_EXTS = {".archive", ".xl"}
DOC_EXTS = {".txt", ".md", ".png", ".jpg", ".jpeg", ".pdf"}

print_lock = threading.Lock()
file_write_lock = threading.Lock()

def safe_print(message, logger=None):
    with print_lock:
        print(message)
        if logger:
            logger.append_log.emit(message)

# --- CORE LOGIC ---

def extract_archive(archive_path, extract_dir, logger=None):
    if os.path.exists(SEVEN_ZIP_EXE):
        try:
            result = subprocess.run(
                [SEVEN_ZIP_EXE, "x", f"-o{extract_dir}", str(archive_path), "-y"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
            )
            if result.returncode == 0:
                return True
        except Exception as e:
            safe_print(f"  [ERROR] 7-Zip failed for {archive_path.name}: {e}", logger)
    
    if zipfile.is_zipfile(archive_path):
        try:
            with zipfile.ZipFile(archive_path, 'r') as z:
                z.extractall(extract_dir)
            return True
        except:
            return False
    return False

def process_extracted_files(temp_dir, dest_dir, archive_name):
    temp_path, dest_path = Path(temp_dir), Path(dest_dir)
    for file_path in temp_path.rglob('*'):
        if not file_path.is_file(): continue
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
                target_path = dest_path / "other" / archive_name.rsplit('.', 1)[0] / Path(*parts)
                
        if target_path:
            with file_write_lock:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target_path)

# --- COMMAND HANDLERS ---

def run_extract(input_path, output_path, workers, logger=None):
    input_dir, dest_dir = Path(input_path), Path(output_path)
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
    except:
        return item.name, False

def run_clear(game_path, logger=None):
    gp = Path(game_path)
    targets = [
        gp / "red4ext", gp / "mods", gp / "archive" / "pc" / "mod",
        gp / "bin" / "x64" / "plugins", gp / "bin" / "x64" / "version.dll",
        gp / "bin" / "x64" / "winmm.dll", gp / "bin" / "x64" / "global.ini",
        gp / "r6" / "scripts", gp / "r6" / "tweaks", gp / "r6" / "cache" / "modded"
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
        safe_print(f"[ERROR] Invalid game or mod pack directory.", logger)
        return
        
    safe_print(f"Uninstalling specific mods from {gp}...", logger)
    
    touched_dirs = set()
    
    # Iterate through every file in the extracted mod pack
    for item in mp.rglob('*'):
        if item.is_file():
            # Get the relative path (e.g. 'archive/pc/mod/basegame_mod.archive')
            rel_path = item.relative_to(mp)
            target_file = gp / rel_path
            
            if target_file.exists():
                try:
                    target_file.unlink()
                    safe_print(f"  [DELETED] {rel_path}", logger)
                    touched_dirs.add(target_file.parent)
                except Exception as e:
                    safe_print(f"  [ERROR] Failed to delete {rel_path}: {e}", logger)

    # Clean up any folders that are now empty
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
                run_extract(self.params['i'], self.params['o'], self.params['w'], self)
            elif self.mode == "clear":
                run_clear(self.params['p'], self)
            elif self.mode == "uninstall":
                run_uninstall(self.params['p'], self.params['m'], self)
            self.finished_sig.emit()

    class CyberModUI(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Cyberpunk 2077 Mod Manager")
            self.setMinimumSize(650, 480)
            
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)

            tabs = QTabWidget()
            layout.addWidget(tabs)

            # Extract Tab
            extract_tab = QWidget()
            tabs.addTab(extract_tab, "Extract Mods")
            ex_layout = QVBoxLayout(extract_tab)

            self.in_edit = self.add_path_row(ex_layout, "Input Folder:")
            self.out_edit = self.add_path_row(ex_layout, "Output Folder:")
            
            w_layout = QHBoxLayout()
            w_layout.addWidget(QLabel("Workers:"))
            self.worker_spin = QSpinBox()
            self.worker_spin.setValue(3)
            w_layout.addWidget(self.worker_spin)
            ex_layout.addLayout(w_layout)

            self.btn_extract = QPushButton("Run Extraction")
            self.btn_extract.clicked.connect(self.start_extract)
            ex_layout.addWidget(self.btn_extract)

            # Uninstall Specific Mod Tab
            uninstall_tab = QWidget()
            tabs.addTab(uninstall_tab, "Uninstall Mod Pack")
            un_layout = QVBoxLayout(uninstall_tab)
            
            self.un_game_edit = self.add_path_row(un_layout, "Game Folder:")
            self.un_mod_edit = self.add_path_row(un_layout, "Extracted Mod Folder:")
            
            self.btn_uninstall = QPushButton("Uninstall Specific Mod Files")
            self.btn_uninstall.clicked.connect(self.start_uninstall)
            un_layout.addWidget(self.btn_uninstall)

            # Clear All Mods Tab
            clear_tab = QWidget()
            tabs.addTab(clear_tab, "Wipe All Mods")
            cl_layout = QVBoxLayout(clear_tab)
            self.game_edit = self.add_path_row(cl_layout, "Game Folder:")
            self.btn_clear = QPushButton("Wipe All Mods")
            self.btn_clear.clicked.connect(self.start_clear)
            cl_layout.addWidget(self.btn_clear)

            # Log Area
            self.log_display = QTextEdit()
            self.log_display.setReadOnly(True)
            self.log_display.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace;")
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
            params = {'i': self.in_edit.text(), 'o': self.out_edit.text(), 'w': self.worker_spin.value()}
            self.run_thread("extract", params)

        def start_clear(self):
            self.run_thread("clear", {'p': self.game_edit.text()})

        def start_uninstall(self):
            self.run_thread("uninstall", {'p': self.un_game_edit.text(), 'm': self.un_mod_edit.text()})

        def run_thread(self, mode, params):
            self.log_display.clear()
            self.toggle_ui(False)
            self.thread = WorkerThread(mode, params)
            self.thread.append_log.connect(lambda msg: self.log_display.append(msg))
            self.thread.finished_sig.connect(lambda: self.toggle_ui(True))
            self.thread.start()

        def toggle_ui(self, enabled):
            self.btn_extract.setEnabled(enabled)
            self.btn_clear.setEnabled(enabled)
            self.btn_uninstall.setEnabled(enabled)

# --- MAIN ENTRY ---

def main():
    parser = argparse.ArgumentParser(description="Cyberpunk 2077 Mod Utility")
    subparsers = parser.add_subparsers(dest="command", required=False)

    # Command: ui
    subparsers.add_parser("ui", help="Run the Graphical User Interface.")
    
    # Command: extract
    ext_parser = subparsers.add_parser("extract", help="Extract and structure mods.")
    ext_parser.add_argument("-i", "--input", required=True)
    ext_parser.add_argument("-o", "--output", required=True)
    ext_parser.add_argument("-w", "--workers", type=int, default=3)
    
    # Command: clear
    clr_parser = subparsers.add_parser("clear", help="Wipe all mods from the game folder.")
    clr_parser.add_argument("-p", "--path", required=True)

    # Command: uninstall
    un_parser = subparsers.add_parser("uninstall", help="Remove specific mod files using an extracted template.")
    un_parser.add_argument("-p", "--path", required=True, help="Path to 'Cyberpunk 2077' game folder.")
    un_parser.add_argument("-m", "--modpack", required=True, help="Path to the extracted mod pack structure.")

    args = parser.parse_args()

    if args.command == "gui":
        if not UI_AVAILABLE:
            print("[ERROR] PySide6 not found. Run 'pip install PySide6' to use the GUI.")
            return
        app = QApplication(sys.argv)
        window = CyberModUI()
        window.show()
        sys.exit(app.exec())
    elif args.command == "extract":
        run_extract(args.input, args.output, args.workers)
    elif args.command == "clear":
        # Add basic CLI confirmation
        ans = input(f"Are you sure you want to wipe mods in {args.path}? (y/n): ")
        if ans.lower() == 'y':
            run_clear(args.path)
    elif args.command == "uninstall":
        run_uninstall(args.path, args.modpack)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()