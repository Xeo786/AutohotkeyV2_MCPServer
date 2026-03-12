import os
import subprocess
import tempfile
import glob
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, List, Optional
from dbgp_client import (
    DbgpClient, DbgpError, DbgpConnectionError,
    get_active_client, set_active_client,
)
from config import (
    resolve_ahk_path, resolve_lib_path, save_config, get_config, configure_paths
)

# Create the FastMCP server
mcp = FastMCP("AutoHotkey v2 MCP Server")

AHK_PATH = resolve_ahk_path()
GLOBAL_LIB_PATH = resolve_lib_path()

def _create_temp_ahk(script_content: str) -> str:
    """Helper to write content to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".ahk", text=True)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(script_content)
    return path

@mcp.tool()
def configure_paths(
    ahk_path: Optional[str] = None, 
    lib_path: Optional[str] = None, 
    use_dialog: bool = False
) -> Dict[str, str]:
    """
    Configure the paths for AutoHotkey and the Global Library.
    Settings are persisted to the user's AppData.
    If 'use_dialog' is True, native selection dialogs will be shown on the host.
    """
    from config import prompt_path
    
    config = get_config()
    
    if use_dialog:
        if not ahk_path:
            p = prompt_path("Select AutoHotkey64.exe", is_file=True)
            if p:
                ahk_path = p
        if not lib_path:
            p = prompt_path("Select Global Library Folder", is_file=False)
            if p:
                lib_path = p

    if ahk_path:
        config["ahk_path"] = ahk_path
    if lib_path:
        config["lib_path"] = lib_path
    
    if ahk_path or lib_path:
        save_config(config)
    
    # Update current session globals
    global AHK_PATH, GLOBAL_LIB_PATH
    if ahk_path:
        AHK_PATH = ahk_path
    if lib_path:
        GLOBAL_LIB_PATH = lib_path
        
    return {
        "status": "success",
        "ahk_path": AHK_PATH,
        "lib_path": GLOBAL_LIB_PATH
    }

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
    
@mcp.tool()
def update_server_config(ahk_path: str, lib_path: str) -> Dict[str, Any]:
    """
    Updates the server configuration with new AutoHotkey and Library paths.
    """
    return configure_paths(ahk_path, lib_path)

# ==========================================================================
# DBGp Debug Tools
# ==========================================================================

DBG_DEFAULT_PORT = 9005

def _require_session() -> DbgpClient:
    """Helper: return the active client or raise a clear error."""
    client = get_active_client()
    if not client or not client.connected:
        raise RuntimeError("No active debug session. Call dbg_attach first.")
    return client


@mcp.tool()
def dbg_attach(pid: int, port: int = DBG_DEFAULT_PORT, timeout: int = 5) -> Dict[str, Any]:
    """
    Attach the debugger to a running AutoHotkey script by PID.
    Starts a TCP listener and sends AHK_ATTACH_DEBUGGER to the target process.
    """
    # Close any existing session
    old = get_active_client()
    if old:
        try:
            old.close()
        except Exception:
            pass
        set_active_client(None)

    client = DbgpClient()
    try:
        client.start_listening(port=port)
    except Exception as e:
        return {"error": f"Failed to start listener on port {port}: {e}"}

    # Use an AHK helper to send AHK_ATTACH_DEBUGGER to the target
    attach_script = f'''#Requires AutoHotkey v2.0
#NoTrayIcon
DetectHiddenWindows(true)
attach_msg := DllCall("RegisterWindowMessage", "Str", "AHK_ATTACH_DEBUGGER")
hwnds := WinGetList("ahk_class AutoHotkey ahk_pid {pid}")
if hwnds.Length = 0 {{
    FileAppend("ERROR: No AutoHotkey window found for PID {pid}`n", "*")
    ExitApp(1)
}}
sent := 0
for hwnd in hwnds {{
    try {{
        PostMessage(attach_msg, 0, {port},, hwnd)
        sent++
    }}
}}
FileAppend("SENT:" sent "`n", "*")
'''
    result = run_ahk_script(attach_script, timeout_seconds=3)

    if result.get("exit_code") != 0 or "ERROR" in result.get("stdout", ""):
        client.close()
        return {
            "error": "Failed to send AHK_ATTACH_DEBUGGER",
            "details": result.get("stdout", "") + result.get("stderr", ""),
        }

    # Wait for the script to connect back
    try:
        info = client.accept_connection(timeout=timeout)
    except DbgpConnectionError as e:
        client.close()
        return {"error": str(e)}

    set_active_client(client)

    # Configure session for AI-friendly usage
    try:
        client.feature_set("max_depth", "2")
        client.feature_set("max_data", "1024")
        client.feature_set("max_children", "64")
    except Exception:
        pass  # Non-critical

    return info


@mcp.tool()
def dbg_launch(path: str, port: int = DBG_DEFAULT_PORT, timeout: int = 5) -> Dict[str, Any]:
    """
    Launch an AutoHotkey script with the /Debug flag and connect the debugger.
    This allows catching load-time errors (like syntax errors).
    """
    # Close any existing session
    old = get_active_client()
    if old:
        try:
            old.close()
        except Exception:
            pass
        set_active_client(None)

    client = DbgpClient()
    try:
        client.start_listening(port=port)
    except Exception as e:
        return {"error": f"Failed to start listener on port {port}: {e}"}

    # Launch the script with /Debug
    # Format: AutoHotkey.exe /Debug [address:port] "script_path"
    try:
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 # SW_HIDE

        # The = is mandatory if an address is specified, or AHK thinks it's a script path
        subprocess.Popen(
            [AHK_PATH, "/ErrorStdOut", "/force", f"/Debug=127.0.0.1:{port}", path],
            startupinfo=startupinfo,
        )
    except Exception as e:
        client.close()
        return {"error": f"Failed to launch script: {e}"}

    # Wait for the script to connect back
    try:
        info = client.accept_connection(timeout=timeout)
    except DbgpConnectionError as e:
        client.close()
        return {"error": str(e)}

    set_active_client(client)

    # Configure session for AI-friendly usage
    try:
        client.feature_set("max_depth", "2")
        client.feature_set("max_data", "1024")
        client.feature_set("max_children", "64")
    except Exception:
        pass  # Non-critical

    return info


@mcp.tool()
def dbg_detach() -> Dict[str, str]:
    """
    Detach from the current debug session, letting the script continue.
    """
    client = get_active_client()
    if not client or not client.connected:
        return {"status": "no_session", "message": "No active debug session."}

    try:
        client.detach()
    except Exception:
        pass
    client.close()
    set_active_client(None)
    return {"status": "detached"}


@mcp.tool()
def dbg_status() -> Dict[str, Any]:
    """
    Get the current status of the debug session.
    """
    client = get_active_client()
    if not client or not client.connected:
        return {"status": "no_session"}
    try:
        return client.status()
    except DbgpError as e:
        return {"error": str(e)}
    except DbgpConnectionError:
        set_active_client(None)
        return {"status": "disconnected", "error": "Connection lost"}


@mcp.tool()
def dbg_break() -> Dict[str, Any]:
    """
    Pause execution of the running script (async break).
    """
    client = _require_session()
    try:
        return client.send_break()
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_continue(mode: str = "run") -> Dict[str, Any]:
    """
    Resume execution. mode: 'run', 'step_into', 'step_over', 'step_out'.
    """
    client = _require_session()
    try:
        if mode == "step_into":
            return client.step_into()
        elif mode == "step_over":
            return client.step_over()
        elif mode == "step_out":
            return client.step_out()
        else:
            return client.run()
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_stack() -> Dict[str, Any]:
    """
    Get the current call stack.
    """
    client = _require_session()
    try:
        frames = client.stack_get()
        return {"frames": [f.to_dict() for f in frames]}
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_get_vars(context: int = 0, depth: int = 0) -> Dict[str, Any]:
    """
    Get variables in a context (0=Local, 1=Global) at a given stack depth.
    """
    # AHK built-in class names that pollute global variable listings
    AHK_BUILTINS = {
        "Any", "Array", "BoundFunc", "Buffer", "Class", "ClipboardAll",
        "Closure", "ComObjArray", "ComObject", "ComValue", "ComValueRef",
        "Enumerator", "Error", "File", "Float", "Func", "Gui", "IndexError",
        "InputHook", "Integer", "KeyError", "Map", "MemberError", "Menu",
        "MenuBar", "MethodError", "Number", "OSError", "Object",
        "PropertyError", "RegExMatchInfo", "String", "TargetError",
        "TimeoutError", "TypeError", "UnsetError", "UnsetItemError",
        "ValueError", "VarRef", "ZeroDivisionError",
    }
    client = _require_session()
    try:
        variables = client.context_get(context_id=context, depth=depth)
        filtered = [
            v for v in variables
            if v.facet != "Builtin"
            and not (v.type == "object" and v.name in AHK_BUILTINS)
            and not v.name.startswith("A_")  # Built-in A_ vars unless specifically requested
        ]
        return {
            "count": len(filtered),
            "variables": [v.to_dict() for v in filtered],
        }
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_get_var(name: str, context: int = 0, depth: int = 0) -> Dict[str, Any]:
    """
    Get a single variable by name.
    """
    client = _require_session()
    try:
        var = client.property_get(name, context_id=context, depth=depth)
        return var.to_dict()
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_set_var(name: str, value: str) -> Dict[str, Any]:
    """
    Set a variable's value in the current context.
    """
    client = _require_session()
    try:
        success = client.property_set(name, value)
        return {"success": success}
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_eval(expression: str) -> Dict[str, Any]:
    """
    Evaluate an AHK expression in the current execution context.
    The script must be in a 'break' state.
    """
    client = _require_session()
    try:
        result = client.eval(expression)
        if result:
            return result.to_dict()
        return {"result": None, "message": "Expression evaluated, no return value."}
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_set_breakpoint(file: str, line: int) -> Dict[str, Any]:
    """
    Set a line breakpoint in a script file.
    """
    client = _require_session()
    try:
        return client.breakpoint_set(file=file, line=line)
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_list_breakpoints() -> Dict[str, Any]:
    """
    List all active breakpoints.
    """
    client = _require_session()
    try:
        bps = client.breakpoint_list()
        return {"count": len(bps), "breakpoints": bps}
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_remove_breakpoint(breakpoint_id: str) -> Dict[str, Any]:
    """
    Remove a breakpoint by its ID.
    """
    client = _require_session()
    try:
        client.breakpoint_remove(breakpoint_id)
        return {"success": True, "removed_id": breakpoint_id}
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_get_source(file: str = "", begin_line: int = 0, end_line: int = 0) -> Dict[str, Any]:
    """
    Retrieve source code from the debugged script.
    If file is empty, gets the current file.
    """
    client = _require_session()
    try:
        src = client.source(
            file=file if file else None,
            begin_line=begin_line,
            end_line=end_line,
        )
        return {"source": src}
    except DbgpError as e:
        return {"error": str(e)}


@mcp.tool()
def dbg_stdout(mode: int = 1) -> Dict[str, Any]:
    """
    Set stdout redirection for the debugged script.
    0=disable, 1=copy to debugger, 2=redirect to debugger only.
    """
    client = _require_session()
    try:
        success = client.stdout(mode)
        return {"success": success, "mode": mode}
    except DbgpError as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
