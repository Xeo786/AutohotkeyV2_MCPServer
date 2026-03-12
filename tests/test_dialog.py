import sys
import os

# Add parent directory to path so we can import server
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server import configure_paths

print("Popping dialogs... Please check your taskbar!")
# This will call the tool which will call prompt_path
result = configure_paths(use_dialog=True)

print(f"Result: {result}")
