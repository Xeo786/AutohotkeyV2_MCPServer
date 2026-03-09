# AutoHotkey v2 MCP Server

## What is it?
This is a custom **Model Context Protocol (MCP)** server built in Python, designed specifically to bridge the gap between AI coding assistants and the AutoHotkey v2 ecosystem on Windows. 

MCP is an open standard that enables AI models to connect securely to local data sources and tools. This server exposes four powerful, specialized tools to the AI, granting it the context and execution capabilities needed to write perfect AHK scripts.

## Why was it created?
AutoHotkey v2 introduced strict object-oriented syntax, removing graceful failures and silent errors that existed in v1. When an AI tries to write AHK code blindly, it often:
1. Mixes up v1 and v2 syntax.
2. Cannot tell if the target window title or class is correct.
3. Cannot verify if the script even launches without crashing.
4. Doesn't know what custom libraries the user already has installed.

This server solves **all** of these problems by giving the AI eyes (inspect active window), knowledge (search library), and hands (validate and run).

---

## How does it help the AI? (Features)

The server exposes four tools to the AI:

### 1. `validate_ahk_syntax`
- **What it does:** Runs external AHK code through AutoHotkey's `/Validate` switch, sending syntax errors to `/ErrorStdOut`.
- **How it helps:** The AI can verify that the code it just wrote is syntactically sound, catching missing braces, undefined variables, or v1 legacy commands *before* handing the script to the user.

### 2. `run_ahk_script`
- **What it does:** Executes a temporary script and forcefully captures standard output (`FileAppend(text, "*")`) and runtime errors, strictly enforcing a timeout (e.g., 3 seconds) to prevent infinite loops.
- **How it helps:** The AI can test logical behavior (e.g., "Does this Regex expression actually math correctly in AHK?"). Fast feedback loops mean fewer broken scripts.

### 3. `inspect_active_window`
- **What it does:** Runs a tiny script returning the Title, Class (`ahk_class`), and Executable (`ahk_exe`) of whatever window the user currently has focused.
- **How it helps:** Finding correct window hooks is tedious. The user can just focus an app, ask the AI to "write a script for my active window," and the AI can pull the exact selectors needed for `WinActivate` or `ControlSend`.

### 4. `search_global_library`
- **What it does:** Performs a text search through the user’s master AHK library folder (`C:\Users\AA\Documents\AHK\mylib`).
- **How it helps:** Instead of reinventing the wheel (like creating a new WebSocket class), the AI can search the user's local drive, read the existing custom wrappers, and write code that utilizes the user's preferred ecosystem. 

---

## Example Workflow

Here is how an interaction with the AI works when this server is running:

**User:** "Write a script that closes my active window and logs it using my `MyLogger.ahk` library."

**AI Process (Under the hood):**
1. **AI calls `inspect_active_window`** -> Finds out the user is in "Notepad" (`ahk_class Notepad`).
2. **AI calls `search_global_library("MyLogger")`** -> Discovers it needs to use `Logger.Info("Closed")`.
3. **AI writes the draft script.**
4. **AI calls `validate_ahk_syntax`** -> Realizes it forgot a closing brace.
5. **AI fixes the code and gives the user a guaranteed-to-work script.**

---

## How to Install and Use It

1. **Prerequisites:** Ensure you have Python installed and AutoHotkey v2 installed at `C:\Program Files\AutoHotkey\v2.0.21\AutoHotkey64.exe`.
2. **Install MCP Package:** Open a terminal in this directory and run:
   ```cmd
   pip install -r requirements.txt
   ```
3. **Configure your AI IDE:** Open your AI IDE's `mcp_config.json` (or equivalent MCP settings file) and add the following block:
   ```json
   {
     "mcpServers": {
       "ahkv2-mcp": {
         "command": "python",
         "args": [
           "s:\\lib\\AutohotkeyV2_MCPServer\\server.py"
         ],
         "env": {}
       }
     }
   }
   ```
4. **Restart:** Restart your IDE. The tools (`validate_ahk_syntax`, `run_ahk_script`, `inspect_active_window`, `search_global_library`) will now be available in the context of your chats!
## AI Core Operating Rules (mcp_rules.md)

When an AI is leveraging this MCP Server to write or automate AutoHotkey scripts, it **MUST** strict abide by the following operational procedures:

### Rule 1: Window Interrogation & Control Extraction (`WinGetControls`)
Before attempting to click a button, type in a field, or automate a GUI, the AI must fully map the application's interface:
1. Use `run_ahk_script` to execute `WinGetList("Target Title")` or `WinGetList("ahk_exe target.exe")`.
2. **If multiple windows are found:** The AI MUST halt and ask the user to clarify or select which HWND/Window Title is the correct target. (Do not guess on window handles).
3. **Once the exact window is confirmed:** Use `WinGetControls()` to loop through the HWND and extract the ClassNN of every control.
4. Extract the properties (`ControlGetText`, `ControlGetEnabled`, `ControlGetChecked`) of each control to build a map. Use this map to construct flawless `ControlClick` or `ControlSend` commands.

### Rule 2: AHK Debugging via PostMessage (`ListLines` / `ListVars`)
If the user asks "what is this script doing?" or "why is it stuck?":
1. **Never guess.** Connect directly to the script like a debugger.
2. Locate the target script's hidden main window. Since AHK scripts hide their primary command window, you must execute:
   `WinGetList("ahk_class AutoHotkey ahk_pid [TargetPID]")`
3. Unmask the state of the script using `PostMessage`:
   - Send `PostMessage(0x111, 65406, 0,, mainWindowHwnd)` to trigger `View > Lines most recently executed`.
   - Send `PostMessage(0x111, 65407, 0,, mainWindowHwnd)` to trigger `View > Variables and their contents`.
4. Read the output using `ControlGetText("Edit1", mainWindowHwnd)` and analyze the execution flow or variable states to explain the problem to the user.

### Rule 3: Native Environment & Limitations
1. Acknowledge what standard AHK `ControlGet` can and cannot see.
2. If `WinGetControls` returns only `DesktopWindowXamlSource`, `ApplicationFrameInputSinkWindow`, or `Windows.UI.Core.CoreWindow`, immediately inform the user that the target is a Universal Windows Platform (UWP/WinUI) application. 
3. Because Win32 commands cannot peer inside UWP XAML canvases, the AI must pivot and offer solutions using standard `Send`/`Click` coordinates, or explicitly request permission to use UIAutomation (UIA) libraries.
