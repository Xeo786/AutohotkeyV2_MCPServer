import sys
import os

# Add parent directory to path so we can import server
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server import validate_ahk_syntax, run_ahk_script, inspect_active_window, search_global_library

print("=== Testing validate_ahk_syntax (valid) ===")
print(validate_ahk_syntax("MsgBox 'Hello World'"))

print("\n=== Testing validate_ahk_syntax (invalid) ===")
print(validate_ahk_syntax("MsgBox 'Hello World"))

print("\n=== Testing run_ahk_script ===")
print(run_ahk_script("FileAppend 'Testing Run\\n', '*'"))

print("\n=== Testing run_ahk_script timeout ===")
print(run_ahk_script("Loop { \n Sleep 100 \n }", timeout_seconds=1))

print("\n=== Testing inspect_active_window ===")
print(inspect_active_window())

print("\n=== Testing search_global_library ===")
print(search_global_library("Gui")[:200] + "...")
