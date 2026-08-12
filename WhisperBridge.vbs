' WhisperBridge — launcher silencioso (sem janela preta de terminal)
' Duplo clique neste arquivo ou use o atalho da Area de Trabalho.

Option Explicit
Dim sh, fso, root, ps1, cmd, rc

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
ps1  = root & "\WhisperBridge.ps1"

If Not fso.FileExists(ps1) Then
  MsgBox "Nao encontrei WhisperBridge.ps1 em:" & vbCrLf & root, vbCritical, "WhisperBridge"
  WScript.Quit 1
End If

' 0 = janela oculta; False = nao esperar (o .ps1 espera a UI e limpa ao fechar)
' -WindowStyle Hidden evita console; ExecutionPolicy Bypass so para este script
cmd = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """"

rc = sh.Run(cmd, 0, False)
WScript.Quit 0
