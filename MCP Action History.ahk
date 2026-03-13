#Requires AutoHotkey v2.0
#SingleInstance Force
#Include <cJSON> ;cJSON by geekdude https://github.com/geekdude/cJSON

; MCP Action History Explorer
; Created for AutoHotkey v2 MCP Server
; Created by Xeo786 (https://github.com/Xeo786)
; Licensed under GNU GPL 3.0

global HistoryDir := A_AppData "\AutoHotkey_MCP_Server\history"
global HistoryIndex := HistoryDir "\history.json"
TraySetIcon("networkexplorer.dll", 4) 
MyGui := Gui("+Resize", "MCP Action History")
MyGui.SetFont("s10", "Segoe UI")

global StartupShortcut := A_Startup "\MCP Action History.lnk"
MyGui.Add("Text", "w600", "Action History from " HistoryIndex)
StartupCheckbox := MyGui.Add("Checkbox", "x780 yp w120 " (FileExist(StartupShortcut) ? "Checked" : ""), "Run on Startup")
StartupCheckbox.OnEvent("Click", ToggleStartup)
LV := MyGui.Add("ListView", "xm w800 h400", ["Time", "Tool", "Description", "Summary", "ID", "Workspace", "ScriptPath"])
LV.OnEvent("DoubleClick", LV_DoubleClick)

MyGui.Add("Button", "Default w100", "Refresh").OnEvent("Click", RefreshHistory)
MyGui.Add("Button", "x+10 w100", "Preview").OnEvent("Click", PreviewSelected)
MyGui.Add("Button", "x+10 w100", "Copy Code").OnEvent("Click", CopySelected)
MyGui.Add("Button", "x+10 w150", "Restore to Workspace").OnEvent("Click", RestoreSelected)
MyGui.Add("Button", "x+10 w120", "Delete Selected").OnEvent("Click", DeleteSelected)
MyGui.Add("Button", "x+10 w120", "Delete All History").OnEvent("Click", DeleteAll)

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
            LV.Add(, entry["timestamp"], entry["tool"], entry["description"], entry["summary"], entry["id"], entry.Has("workspace") ? entry["workspace"] : "", entry["script_file"])
        }
        
        LV.ModifyCol(1, "AutoHdr")
        LV.ModifyCol(2, "AutoHdr")
        LV.ModifyCol(3, "AutoHdr")
        LV.ModifyCol(4, "AutoHdr")
        LV.ModifyCol(5, 0) ; Hide ID
        LV.ModifyCol(6, "AutoHdr") ; Show Workspace
        LV.ModifyCol(7, 0) ; Hide ScriptPath
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
    
    scriptFile := LV.GetText(row, 7)
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
    
    scriptFile := LV.GetText(row, 7)
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
    
    scriptFile := LV.GetText(row, 7)
    workspacePath := LV.GetText(row, 6)
    
    if !FileExist(scriptFile)
    {
        MsgBox("Script file not found in history: " scriptFile)
        return
    }

    defaultName := "restored_" FormatTime(, "HHmmss") ".ahk"

    if (workspacePath == "")
    {
        targetPath := FileSelect("S", defaultName, "Restore Action As", "AutoHotkey Files (*.ahk)")
    }
    else if !DirExist(workspacePath)
    {
        MsgBox("Original workspace path no longer exists:`n" workspacePath "`nPlease select a new location.")
        targetPath := FileSelect("S", defaultName, "Restore Action As", "AutoHotkey Files (*.ahk)")
    }
    else
    {
        targetPath := workspacePath "\" defaultName
        if MsgBox("Restore this action to original workspace?`n`nPath: " targetPath, "Confirm Restore", "YesNo") == "No"
            targetPath := FileSelect("S", defaultName, "Restore Action As", "AutoHotkey Files (*.ahk)")
    }

    if !targetPath
        return
    
    if !RegExMatch(targetPath, "\.ahk$")
        targetPath .= ".ahk"
        
    try
    {
        FileCopy(scriptFile, targetPath, 1)
        MsgBox("Action restored to: " targetPath)
    }
    catch as e
    {
        MsgBox("Restoration failed:`n" e.Message)
    }
}

GetScriptFileFromSelected(row)
{
    return LV.GetText(row, 7)
}

DeleteSelected(*)
{
    row := 0
    selectedRows := []
    while (row := LV.GetNext(row))
        selectedRows.Push(row)
    
    if (selectedRows.Length == 0)
    {
        MsgBox("Please select one or more actions to delete.")
        return
    }
    
    if MsgBox("Are you sure you want to delete the " selectedRows.Length " selected actions?`nThis will remove the log files permanently.", "Confirm Delete", "YesNo Icon!") == "No"
        return

    try 
    {
        jsonText := FileRead(HistoryIndex, "UTF-8")
        history := JSON.Load(jsonText)
        
        idsToDelete := Map()
        for rowIdx in selectedRows
            idsToDelete[LV.GetText(rowIdx, 5)] := rowIdx

        newHistory := []
        for entry in history
        {
            if idsToDelete.Has(entry["id"])
            {
                if FileExist(entry["script_file"])
                    FileDelete(entry["script_file"])
            }
            else
            {
                newHistory.Push(entry)
            }
        }

        FileOpen(HistoryIndex, "w", "UTF-8").Write(JSON.Dump(newHistory, 4))
        RefreshHistory()
        ToolTip("Selected actions deleted.")
        SetTimer(() => ToolTip(), -2000)
    }
    catch as e
    {
        MsgBox("Failed to delete selected actions: " e.Message)
    }
}

DeleteAll(*)
{
    if MsgBox("CRITICAL: Are you sure you want to delete ALL history?`nThis will remove ALL log files and dated folders permanently.", "Confirm Delete ALL", "YesNo Icon!") == "No"
        return
    
    try 
    {
        ; Reset the index first
        FileOpen(HistoryIndex, "w", "UTF-8").Write("[]")
        
        ; Delete all subdirectories in HistoryDir (dated folders)
        Loop Files, HistoryDir "\*", "D"
        {
            DirDelete(A_LoopFileFullPath, 1)
        }
        
        ; Also delete any stray AHK files in HistoryDir
        Loop Files, HistoryDir "\*.ahk"
        {
            FileDelete(A_LoopFileFullPath)
        }

        RefreshHistory()
        MsgBox("All history has been cleared.")
    }
    catch as e
    {
        MsgBox("Failed to clear history: " e.Message)
    }
}

LV_DoubleClick(LV, RowNumber)
{
    if RowNumber
        PreviewSelected()
}


ToggleStartup(Ctrl, *)
{
    if Ctrl.Value
    {
        try
        {
            FileCreateShortcut(A_ScriptFullPath, StartupShortcut, A_ScriptDir)
            ToolTip("Added to Startup")
        }
        catch as e
        {
            MsgBox("Failed to create shortcut:`n" e.Message)
            Ctrl.Value := 0
        }
    }
    else
    {
        try
        {
            if FileExist(StartupShortcut)
                FileDelete(StartupShortcut)
            ToolTip("Removed from Startup")
        }
        catch as e
        {
            MsgBox("Failed to remove shortcut:`n" e.Message)
            Ctrl.Value := 1
        }
    }
    SetTimer(() => ToolTip(), -2000)
}

Gui_Size(thisGui, MinMax, Width, Height)
{
    if MinMax = -1
        return
    LV.Move(,, Width - 20, Height - 80)
}
