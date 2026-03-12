import os
import json
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("APPDATA", "~")) / "AutoHotkey_MCP_Server"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_AHK_PATH = r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"
DEFAULT_LIB_PATH = str(Path.home() / "Documents" / "AutoHotkey" / "Lib")

def get_config():
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def prompt_path(title, initialdir=None, is_file=True):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if is_file:
            path = filedialog.askopenfilename(
                title=title, 
                initialdir=initialdir, 
                filetypes=[("AutoHotkey Executable", "AutoHotkey*.exe"), ("Executables", "*.exe"), ("All Files", "*.*")]
            )
        else:
            path = filedialog.askdirectory(title=title, initialdir=initialdir)
        root.destroy()
        return path if path else None
    except Exception as e:
        print(f"Failed to show dialog: {e}")
        return None

def resolve_ahk_path():
    # 1. Environment Variable
    env_path = os.environ.get("AHK_PATH")
    if env_path:
        return env_path
    
    # 2. Config File
    config = get_config()
    if "ahk_path" in config:
        return config["ahk_path"]
    
    # 3. Default Location
    return DEFAULT_AHK_PATH

def resolve_lib_path():
    # 1. Environment Variable
    env_path = os.environ.get("GLOBAL_LIB_PATH")
    if env_path:
        return env_path
    
    # 2. Config File
    config = get_config()
    if "lib_path" in config:
        return config["lib_path"]
    
    # 3. Default Location
    return DEFAULT_LIB_PATH

def configure_paths(ahk_path, lib_path):
    config = get_config()
    config["ahk_path"] = ahk_path
    config["lib_path"] = lib_path
    save_config(config)
    return {"status": "success", "ahk_path": ahk_path, "lib_path": lib_path}
