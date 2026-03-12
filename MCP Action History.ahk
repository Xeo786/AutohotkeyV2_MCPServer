#Requires AutoHotkey v2.0
#SingleInstance Force
#Include <cJSON> ; by geekdude https://github.com/geekdude/cJSON

; MCP Action History Explorer
; Created for AutoHotkey v2 MCP Server

global HistoryDir := A_AppData "\AutoHotkey_MCP_Server\history"
global HistoryIndex := HistoryDir "\history.json"

MyGui := Gui("+Resize", "MCP Action History")
MyGui.SetFont("s10", "Segoe UI")

MyGui.Add("Text", "w600", "Action History from " HistoryIndex)
LV := MyGui.Add("ListView", "xm w800 h400", ["Time", "Tool", "Description", "Summary", "ID"])
LV.OnEvent("DoubleClick", LV_DoubleClick)

MyGui.Add("Button", "Default w100", "Refresh").OnEvent("Click", RefreshHistory)
MyGui.Add("Button", "x+10 w100", "Preview").OnEvent("Click", PreviewSelected)
MyGui.Add("Button", "x+10 w100", "Copy Code").OnEvent("Click", CopySelected)
MyGui.Add("Button", "x+10 w150", "Restore to Workspace").OnEvent("Click", RestoreSelected)

MyGui.OnEvent("Close", (*) => ExitApp())
MyGui.OnEvent("Size", Gui_Size)

RefreshHistory()
MyGui.Show()

RefreshHistory(*)
{
    LV.Delete()
    if !FileExist(HistoryIndex)
    {
        MsgBox("History index not found at:`n" HistoryIndex)
        return
    }

    try 
    {
        jsonText := FileRead(HistoryIndex, "UTF-8")
        history := JSON.Load(jsonText)
        
        for entry in history
        {
            LV.Add(, entry["timestamp"], entry["tool"], entry["description"], entry["summary"], entry["id"])
        LV.ModifyCol(1, "AutoHdr")
        LV.ModifyCol(2, "AutoHdr")
        LV.ModifyCol(3, "AutoHdr")
        LV.ModifyCol(4, 400)
        LV.ModifyCol(5, 0) ; Hide ID
        }
    }
    catch as e
    {
        MsgBox("Failed to load history: " e.Message)
    }
}

PreviewSelected(*)
{
    row := LV.GetNext()
    if !row
        return
    
    scriptFile := GetScriptFileFromSelected(row)
    if !FileExist(scriptFile)
    {
        MsgBox("Script file not found: " scriptFile)
        return
    }

    code := FileRead(scriptFile, "UTF-8")
    
    PreviewGui := Gui("+Owner" MyGui.Hwnd " +Resize", "Preview Action - " LV.GetText(row, 3))
    PreviewGui.SetFont("s10", "Consolas")
    EditCtrl := PreviewGui.Add("Edit", "w700 h500 ReadOnly", code)
    PreviewGui.Show()
}

CopySelected(*)
{
    row := LV.GetNext()
    if !row
        return
    
    scriptFile := GetScriptFileFromSelected(row)
    if !FileExist(scriptFile)
    {
        MsgBox("Script file not found: " scriptFile)
        return
    }

    A_Clipboard := FileRead(scriptFile, "UTF-8")
    ToolTip("Code copied to clipboard!")
    SetTimer(() => ToolTip(), -2000)
}

RestoreSelected(*)
{
    row := LV.GetNext()
    if !row
        return
    
    scriptFile := GetScriptFileFromSelected(row)
    if !FileExist(scriptFile)
    {
        MsgBox("Script file not found: " scriptFile)
        return
    }

    targetPath := FileSelect("S", "restored_action.ahk", "Restore Action As", "AutoHotkey Files (*.ahk)")
    if !targetPath
        return
    
    if !RegExMatch(targetPath, "\.ahk$")
        targetPath .= ".ahk"
        
    FileCopy(scriptFile, targetPath, 1)
    MsgBox("Action restored to: " targetPath)
}

GetScriptFileFromSelected(row)
{
    actionId := LV.GetText(row, 5)
    
    ; We need to find the entry in JSON to get the full path, 
    ; or we could have stored it in a hidden column.
    ; For efficiency, let's just re-read the JSON or store it.
    ; Storing it in ListView as a hidden column 6 is better.
    ; But for now, I'll just find it in the index.
    
    jsonText := FileRead(HistoryIndex, "UTF-8")
    history := JSON.Load(jsonText)
    for entry in history
    {
        if (entry["id"] == actionId)
            return entry["script_file"]
    }
    return ""
}

LV_DoubleClick(LV, RowNumber)
{
    if RowNumber
        PreviewSelected()
}

Gui_Size(thisGui, MinMax, Width, Height)
{
    if MinMax = -1
        return
    LV.Move(,, Width - 20, Height - 80)
}
