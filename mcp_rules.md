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
