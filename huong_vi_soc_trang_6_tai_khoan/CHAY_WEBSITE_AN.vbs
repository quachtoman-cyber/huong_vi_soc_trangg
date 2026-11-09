Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

folder = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = folder

batPath = FSO.BuildPath(folder, "BAT_DAU_WEBSITE.bat")
If Not FSO.FileExists(batPath) Then
    MsgBox "Khong tim thay BAT_DAU_WEBSITE.bat. Hay de file VBS cung thu muc voi file BAT.", vbExclamation, "Thieu file khoi dong"
    WScript.Quit
End If

WshShell.Run """" & batPath & """", 0, False
WScript.Sleep 2500
WshShell.Run "http://127.0.0.1:8000", 1, False
