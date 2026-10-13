' launch_hidden.vbs - starts the launcher with NO console window.
' Used as the shortcut target so double-clicking never flashes a console.
' Works on Windows 7 and Windows 10+. No dependencies.
Dim fso, shell, appDir, pyw, py, p

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Prefer the portable runtime pythonw.exe, then python.exe, then PATH.
pyw = appDir & "\runtime\pythonw.exe"
py  = appDir & "\runtime\python.exe"

If fso.FileExists(pyw) Then
    p = pyw
ElseIf fso.FileExists(py) Then
    p = py
Else
    p = "pythonw.exe"
    If Not IsNull(shell.Environment("PROCESS").Item("PATH")) Then
        ' fall through: shell.Run resolves pythonw.exe from PATH if present
    End If
End If

' 0 = hidden window, False = do not wait.
shell.Run """" & p & """ """ & appDir & "\launcher.py""", 0, False
