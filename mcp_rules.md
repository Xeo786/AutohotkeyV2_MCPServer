## AI Core Operating Rules (mcp_rules.md)

When an AI is leveraging this MCP Server to write or automate AutoHotkey scripts, it **MUST** strict abide by the following operational procedures:

### Rule 1: Window Interrogation & Control Extraction (`WinGetControls`)
Before attempting to click a button, type in a field, or automate a GUI, the AI must fully map the application's interface:
1. Use `run_ahk_script` to execute `WinGetList("Target Title")` or `WinGetList("ahk_exe target.exe")`.
2. **If multiple windows are found:** The AI MUST halt and ask the user to clarify or select which HWND/Window Title is the correct target. (Do not guess on window handles).
3. **Once the exact window is confirmed:** Use `WinGetControls()` to loop through the HWND and extract the ClassNN of every control.
4. Extract the properties (`ControlGetText`, `ControlGetEnabled`, `ControlGetChecked`) of each control to build a map. Use this map to construct flawless `ControlClick` or `ControlSend` commands.

### Rule 2: AHK Debugging — DBGp Live Debugger (Primary) & PostMessage (Fallback)
If the user asks "what is this script doing?", "debug this script", or "why is it stuck?":

#### A. DBGp Protocol Debugging (Preferred)
When you need **deep, interactive debugging** (inspect variables, evaluate expressions, set breakpoints, step through code), use the DBGp debug tools:
1. **Attach:** Call `dbg_attach(pid=<TargetPID>)` to connect to the running script via the DBGp protocol. This sends an `AHK_ATTACH_DEBUGGER` window message and establishes a TCP debug session.
2. **Inspect State:** Use `dbg_get_vars(context=1)` to inspect global variables, `dbg_get_vars(context=0)` for local variables at the current stack frame.
3. **Pause & Step:** Use `dbg_break()` to pause execution, then `dbg_continue(mode="step_over")` or `dbg_continue(mode="step_into")` to step through code line-by-line.
4. **Evaluate:** Use `dbg_eval(expression)` to evaluate any AHK expression in the current context. **Note:** `eval` only works when paused inside a function — if paused between timer ticks, set a breakpoint first.
5. **Breakpoints:** Use `dbg_set_breakpoint(file, line)` to set breakpoints, `dbg_list_breakpoints()` to list them.
6. **Source:** Use `dbg_get_source()` to retrieve the script's source code.
7. **Finish:** Always call `dbg_detach()` when done to let the script resume normally.

**Important constraints:**
- The target script must NOT already have a debugger attached (VS Code, SciTE, etc.).
- Cannot cross UAC boundaries (non-admin → admin process).
- Only one debug session at a time.

#### B. PostMessage Fallback (Quick Peek)
For a **fast, lightweight snapshot** of a script's state (no interactive stepping needed):
1. Locate the target script's hidden main window via `WinGetList("ahk_class AutoHotkey ahk_pid [TargetPID]")`.
2. Send `PostMessage(0x111, 65406, 0,, mainWindowHwnd)` to trigger `View > Lines most recently executed`.
3. Send `PostMessage(0x111, 65407, 0,, mainWindowHwnd)` to trigger `View > Variables and their contents`.
4. Read the output using `ControlGetText("Edit1", mainWindowHwnd)` and analyze.

### Rule 3: Native Environment & Limitations
1. Acknowledge what standard AHK `ControlGet` can and cannot see.
2. If `WinGetControls` returns only `DesktopWindowXamlSource`, `ApplicationFrameInputSinkWindow`, or `Windows.UI.Core.CoreWindow`, immediately inform the user that the target is a Universal Windows Platform (UWP/WinUI) application. 
3. Because Win32 commands cannot peer inside UWP XAML canvases, the AI must pivot and offer solutions using standard `Send`/`Click` coordinates, or explicitly request permission to use UIAutomation (UIA) libraries.

### Rule 4: Recognizing Power Scope & Proactive Suggestions
AutoHotkey is a highly capable systems tool, not just a macro engine. The AI must recognize this execution power and actively suggest optimal paths:
1. **`DllCall`:** If the user is trying to accomplish system-level changes (e.g., memory address reading, display topology, low-level mouse hooks, GDI+ rendering), proactively suggest bypassing the UI and using direct Win32 API `DllCall` implementations.
2. **`ComObject`:** If the user is attempting to read Microsoft Office files, interact with WMI (hardware info), WebView2, or standard accessibility nodes, proactively suggest using Component Object Model (`ComObject`) instead of trying to automate clicks on screen.
3. **Pre-built Library Leverage:** When pivoting to these advanced topics, search the user's local `mylib` via `search_global_library` first. If a `class cJSON` or `class UIA` or `class WebView2` already exists, use their established interface rather than rewriting lower-level code.
