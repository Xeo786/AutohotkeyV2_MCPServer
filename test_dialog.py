import sys
import os

# Add the server directory to path
sys.path.insert(0, r"S:\lib\AutohotkeyV2_MCPServer")

from server import configure_paths

print("Popping dialogs... Please check your taskbar!")
# This will call the tool which will call prompt_path
result = configure_paths(use_dialog=True)

print(f"Result: {result}")
