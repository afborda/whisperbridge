' WhisperBridge — launcher silencioso (sem janela preta de terminal)
' Duplo clique neste arquivo ou use o atalho da Area de Trabalho.

Option Explicit
Dim sh, fso, root, ps1, cmd

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
ps1  = root & "\scripts\windows\launcher.ps1"

If Not fso.FileExists(ps1) Then
  MsgBox "Nao encontrei scripts\windows\launcher.ps1 em:" & vbCrLf & root, vbCritical, "WhisperBridge"
  WScript.Quit 1
End If

cmd = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """"
sh.Run cmd, 0, False
WScript.Quit 0
