' Enfestos Charth v2.3.2 — Inicializador
' Corrigido: busca python.exe via registro do Windows (independe do PATH do sistema)

Dim oShell, oFSO, oHTTP, strDir, bRodando

Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")
strDir = oFSO.GetParentFolderName(WScript.ScriptFullName)
oShell.CurrentDirectory = strDir

' ── 1. Servidor já está rodando? ──────────────────────────────────────────────
bRodando = False
On Error Resume Next
Set oHTTP = CreateObject("MSXML2.XMLHTTP")
oHTTP.Open "GET", "http://localhost:5050/versao", False
oHTTP.Send
If Err.Number = 0 Then
    If oHTTP.Status = 200 Then bRodando = True
End If
Set oHTTP = Nothing
On Error GoTo 0

If bRodando Then
    oShell.Run "http://localhost:5050", 1, False
    WScript.Quit
End If

' ── 2. Encontrar python.exe via registro do Windows ───────────────────────────
' WScript.Shell usa PATH do sistema; Python "install for current user" fica em
' %LOCALAPPDATA% e nao entra no PATH do sistema. O registro tem o caminho exato.
Dim strPython
strPython = ""

Dim versoes(7)
versoes(0) = "3.14"
versoes(1) = "3.13"
versoes(2) = "3.12"
versoes(3) = "3.11"
versoes(4) = "3.10"
versoes(5) = "3.9"
versoes(6) = "3.8"
versoes(7) = "3.7"

Dim v, candidato
For Each v In versoes
    If strPython = "" Then
        On Error Resume Next
        ' HKCU = instalacao do usuario atual (sem admin)
        candidato = oShell.RegRead("HKCU\Software\Python\PythonCore\" & v & "\InstallPath\ExecutablePath")
        If Err.Number = 0 And candidato <> "" Then
            If oFSO.FileExists(candidato) Then strPython = candidato
        End If
        Err.Clear
        If strPython = "" Then
            ' HKLM = instalacao global (com admin)
            candidato = oShell.RegRead("HKLM\Software\Python\PythonCore\" & v & "\InstallPath\ExecutablePath")
            If Err.Number = 0 And candidato <> "" Then
                If oFSO.FileExists(candidato) Then strPython = candidato
            End If
        End If
        On Error GoTo 0
    End If
Next

' ── 3. Fallback: perguntar ao PowerShell onde esta o python ───────────────────
If strPython = "" Then
    On Error Resume Next
    Dim oExec, strPS
    Set oExec = oShell.Exec("powershell -NoProfile -Command ""(Get-Command python -ErrorAction SilentlyContinue).Source""")
    If Err.Number = 0 Then
        strPS = Trim(oExec.StdOut.ReadAll())
        If strPS <> "" And oFSO.FileExists(strPS) Then
            ' Ignorar o stub da Windows Store (nao funciona headless)
            If InStr(LCase(strPS), "windowsapps") = 0 Then
                strPython = strPS
            End If
        End If
    End If
    On Error GoTo 0
End If

If strPython = "" Then
    MsgBox "Python nao encontrado." & vbCrLf & vbCrLf & _
           "Instale o Python via python.org (marque 'Add to PATH')" & vbCrLf & _
           "ou execute INSTALAR.bat.", _
           vbExclamation, "Enfestos Charth"
    WScript.Quit
End If

' ── 4. Iniciar via CMD ────────────────────────────────────────────────────────
' Regra cmd /c com caminhos com espacos: usar aspas duplas externas.
' cmd /c ""c:\caminho com espaco\python.exe" "c:\dir\main.py""
' CMD remove o par externo de aspas, deixando o comando corretamente aspado.
Dim Q, strCmd
Q = Chr(34)
' Chama launcher.py: aplica auto-update via GitHub Releases e depois sobe o main.py.
strCmd = "cmd /c " & Q & Q & strPython & Q & " " & Q & strDir & "\launcher.py" & Q & Q
oShell.Run strCmd, 0, False

' ── 5. Aguardar servidor subir (ate 30 tentativas x 1s) ──────────────────────
Dim i, bPronto
bPronto = False
For i = 1 To 30
    WScript.Sleep 1000
    On Error Resume Next
    Set oHTTP = CreateObject("MSXML2.XMLHTTP")
    oHTTP.Open "GET", "http://localhost:5050/versao", False
    oHTTP.Send
    If Err.Number = 0 Then
        If oHTTP.Status = 200 Then bPronto = True
    End If
    Set oHTTP = Nothing
    On Error GoTo 0
    If bPronto Then Exit For
Next

If Not bPronto Then
    MsgBox "Nao foi possivel iniciar o servidor." & vbCrLf & vbCrLf & _
           "Python encontrado em: " & strPython & vbCrLf & vbCrLf & _
           "Tente abrir 'iniciar_visivel.bat' para ver o erro.", _
           vbExclamation, "Enfestos Charth"
    WScript.Quit
End If

' ── 6. Abrir navegador ────────────────────────────────────────────────────────
oShell.Run "http://localhost:5050", 1, False

Set oShell = Nothing
Set oFSO   = Nothing
