from server import run_ahk_script

script = '''
#Requires AutoHotkey v2.0
SetTitleMatchMode(3)
DetectHiddenWindows(true)

try {
    guiHwnd := WinGetID("Window Snipping - Preferences ahk_class AutoHotkeyGUI")
    pid := WinGetPID(guiHwnd)
    
    mainHwnds := WinGetList("ahk_class AutoHotkey ahk_pid " pid)
    if mainHwnds.Length == 0 {
        FileAppend("Could not find main hidden window.`n", "*")
        ExitApp()
    }
    
    mainHwnd := mainHwnds[1]
    title := WinGetTitle(mainHwnd)
    
    ; PostMessage to trigger ListVars (65407)
    PostMessage(0x111, 65407, 0,, mainHwnd)
    Sleep(500) ; Wait for theEdit control to populate
    
    text := ControlGetText("Edit1", mainHwnd)
    
    FileAppend("SCRIPT PATH: " title "`n", "*")
    FileAppend("--- VARIABLES ---`n", "*")
    FileAppend(text, "*")
    
} catch as e {
    FileAppend("Error: " e.Message, "*")
}
'''

res = run_ahk_script(script, timeout_seconds=4)
print(res['stdout'])
if res['stderr']:
    print("ERRORS:", res['stderr'])
