import os
import subprocess
import tempfile
import glob
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any

# Create the FastMCP server
mcp = FastMCP("AutoHotkey v2 MCP Server")

AHK_PATH = r"C:\Program Files\AutoHotkey\v2.0.21\AutoHotkey64.exe"
GLOBAL_LIB_PATH = r"C:\Users\AA\Documents\AHK\mylib"

def _create_temp_ahk(script_content: str) -> str:
    """Helper to write content to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".ahk", text=True)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(script_content)
    return path

@mcp.tool()
def validate_ahk_syntax(script_content: str) -> str:
    """
    Validates AutoHotkey v2 syntax without executing the script.
    """
    temp_path = _create_temp_ahk(script_content)
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 # SW_HIDE

        result = subprocess.run(
            [AHK_PATH, "/ErrorStdOut", "/Validate", temp_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            startupinfo=startupinfo
        )
        if result.returncode == 0:
            return "Syntax validation passed successfully. Exit code 0."
        else:
            return f"Syntax Error (Exit Code {result.returncode}):\n{result.stderr.strip()}"
    except Exception as e:
        return f"Execution Error: {str(e)}"
    finally:
        os.remove(temp_path)

@mcp.tool()
def run_ahk_script(script_content: str, timeout_seconds: int = 3) -> Dict[str, Any]:
    """
    Runs an AutoHotkey v2 script with a strictly enforced timeout.
    Returns stdout, stderr, and exit_code.
    """
    temp_path = _create_temp_ahk(script_content)
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        result = subprocess.run(
            [AHK_PATH, "/ErrorStdOut", temp_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding='utf-8',
            errors='replace',
            startupinfo=startupinfo
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode('utf-8', errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else (e.stderr or "")
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": -1,
            "error": f"Script execution timed out after {timeout_seconds} seconds."
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -2,
            "error": "Failed to execute script."
        }
    finally:
        os.remove(temp_path)

@mcp.tool()
def inspect_active_window() -> Dict[str, str]:
    """
    Returns the Title, Class, and Process Name of the currently active window.
    """
    script_content = '''#Requires AutoHotkey v2.0
#NoTrayIcon
try {
    title := WinGetTitle("A")
    cls := WinGetClass("A")
    exe := WinGetProcessName("A")
    FileAppend(title "`n" cls "`n" exe "`n", "*")
} catch as e {
    FileAppend("ERROR`n" e.Message "`n", "*")
}
'''
    result = run_ahk_script(script_content, timeout_seconds=2)
    
    if result.get("exit_code") == 0 and result.get("stdout"):
        lines = result["stdout"].strip().split('\n')
        if len(lines) >= 3 and lines[0] != "ERROR":
            return {"title": lines[0], "class": lines[1], "exe": lines[2]}
        elif lines[0] == "ERROR":
            return {"error": "AHK Error", "details": "\n".join(lines[1:])}
        else:
            return {"error": "Unexpected output format", "raw_stdout": result["stdout"]}
    else:
        return {"error": "Failed to inspect active window.", "details": str(result)}

@mcp.tool()
def search_global_library(query: str) -> str:
    """
    Searches for a string inside the global AutoHotkey library path.
    Returns a brief context of matching .ahk files (classes or functions).
    """
    if not os.path.exists(GLOBAL_LIB_PATH):
        return f"Global library path not found: {GLOBAL_LIB_PATH}"
        
    query = query.lower()
    matches = []
    
    search_pattern = os.path.join(GLOBAL_LIB_PATH, "**", "*.ahk")
    for filepath in glob.glob(search_pattern, recursive=True):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                if query in line.lower():
                    start = max(0, i - 1)
                    end = min(len(lines), i + 2)
                    context_lines = [l.rstrip() for l in lines[start:end]]
                    
                    filename = os.path.relpath(filepath, GLOBAL_LIB_PATH)
                    matches.append(f"File: {filename} (line {i+1})\n" + "\n".join(f"  {l}" for l in context_lines))
                    
                    if len(matches) >= 20:
                        matches.append("... (Too many matches, truncating results) ...")
                        return "\n\n".join(matches)
        except Exception:
            pass

    if not matches:
        return f"No matches found for '{query}' in {GLOBAL_LIB_PATH}."
        
    return "\n\n".join(matches)

if __name__ == "__main__":
    mcp.run()
