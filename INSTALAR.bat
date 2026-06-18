@echo off
setlocal EnableDelayedExpansion
title Instalador — Enfestos Charth
color 0F
cls

:: ============================================================
::  ENFESTOS CHARTH — INSTALADOR
:: ============================================================

echo.
echo  ============================================================
echo   ENFESTOS CHARTH — Instalador
echo  ============================================================
echo.
echo   Este instalador vai configurar tudo automaticamente.
echo   Aguarde cada etapa concluir antes de fechar esta janela.
echo.
echo  ============================================================
echo.

:: Definir pasta do programa
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"
set "VBS=%APP_DIR%\PCP_Enfestos.vbs"
set "DESKTOP=%USERPROFILE%\Desktop"
set "ATALHO=%DESKTOP%\Enfestos Charth.lnk"

:: ============================================================
:: PRE-INSTALACAO — Encerrar processo anterior se estiver rodando
:: ============================================================
echo   Verificando se ha versao anterior em execucao...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1
timeout /t 1 /nobreak >nul

:: ============================================================
:: ETAPA 1 — Verificar Python
:: ============================================================
echo   [1/4]  Verificando Python...

set "PYTHON="

:: Tentar comandos diretos
for %%C in (python python3 py) do (
    if not defined PYTHON (
        %%C --version >nul 2>&1
        if !errorlevel! equ 0 (
            for /f "delims=" %%V in ('%%C --version 2^>^&1') do (
                echo         %%V encontrado.
                set "PYTHON=%%C"
            )
        )
    )
)

:: Buscar em locais comuns se não encontrou
if not defined PYTHON (
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
        "C:\Python310\python.exe"
        "%PROGRAMFILES%\Python312\python.exe"
        "%PROGRAMFILES%\Python311\python.exe"
    ) do (
        if not defined PYTHON (
            if exist %%P (
                set "PYTHON=%%P"
                echo         Python encontrado em %%P
            )
        )
    )
)

if defined PYTHON (
    echo         OK - Python disponivel.
    goto instalar_pip
)

:: ============================================================
:: Python nao encontrado — instalar automaticamente
:: ============================================================
echo.
echo   [1/4]  Python nao encontrado. Instalando automaticamente...
echo.

:: Tentar via winget (Windows 10/11)
echo         Tentando instalar via Windows Package Manager...
winget install -e --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements >nul 2>&1

:: Aguardar e verificar
timeout /t 5 /nobreak >nul
for %%C in (python python3 py) do (
    if not defined PYTHON (
        %%C --version >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON=%%C"
    )
)

if defined PYTHON (
    echo         OK - Python instalado via winget.
    goto instalar_pip
)

:: Tentar download direto
echo         Baixando Python do python.org...
echo         (pode demorar 1-2 minutos dependendo da internet)
echo.

set "PY_URL=https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
set "PY_TMP=%TEMP%\python_setup.exe"

powershell -NoProfile -Command "try { (New-Object Net.WebClient).DownloadFile('%PY_URL%', '%PY_TMP%'); Write-Host '        Download concluido.' } catch { Write-Host '        Erro no download: ' + $_.Exception.Message; exit 1 }"
if !errorlevel! neq 0 goto erro_download

echo         Instalando Python (aguarde)...
"%PY_TMP%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
del /f /q "%PY_TMP%" 2>nul

:: Atualizar PATH da sessao atual
for /f "tokens=*" %%P in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"PATH\",\"User\")"') do set "PATH=%%P;%PATH%"

:: Verificar novamente
for %%C in (python python3 py) do (
    if not defined PYTHON (
        %%C --version >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON=%%C"
    )
)
:: Buscar em locais conhecidos apos instalacao
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) do (
    if not defined PYTHON (
        if exist %%P set "PYTHON=%%P"
    )
)

if not defined PYTHON goto erro_python
echo         OK - Python instalado com sucesso.

:: ============================================================
:instalar_pip
:: ETAPA 2 — Instalar bibliotecas Python
:: ============================================================
echo.
echo   [2/4]  Instalando bibliotecas necessarias...

:: --- openpyxl (exportar planilhas Excel) ---
%PYTHON% -c "import openpyxl" >nul 2>&1
if !errorlevel! equ 0 (
    echo         openpyxl ja instalado. OK.
) else (
    echo         Instalando openpyxl...
    %PYTHON% -m pip install --upgrade pip --quiet >nul 2>&1
    %PYTHON% -m pip install openpyxl --quiet --no-warn-script-location
    %PYTHON% -c "import openpyxl" >nul 2>&1
    if !errorlevel! neq 0 goto erro_openpyxl
    echo         OK - openpyxl instalado.
)

:: --- pdfplumber (importar rolos do ERP via PDF) ---
%PYTHON% -c "import pdfplumber" >nul 2>&1
if !errorlevel! equ 0 (
    echo         pdfplumber ja instalado. OK.
) else (
    echo         Instalando pdfplumber...
    %PYTHON% -m pip install pdfplumber --quiet --no-warn-script-location
    %PYTHON% -c "import pdfplumber" >nul 2>&1
    if !errorlevel! neq 0 (
        echo         Aviso: pdfplumber nao instalado. Import de PDF do ERP ficara indisponivel.
        echo         Para instalar manualmente: pip install pdfplumber
    ) else (
        echo         OK - pdfplumber instalado.
    )
)

:: ============================================================
:criar_atalho
:: ETAPA 3 — Criar atalho na area de trabalho
:: ============================================================
echo.
echo   [3/4]  Criando atalho "Enfestos Charth" na Area de Trabalho...

powershell -NoProfile -Command ^
    "$s = New-Object -ComObject WScript.Shell; " ^
    "$sc = $s.CreateShortcut('%ATALHO%'); " ^
    "$sc.TargetPath = 'wscript.exe'; " ^
    "$sc.Arguments = '\"%VBS%\"'; " ^
    "$sc.WorkingDirectory = '%APP_DIR%'; " ^
    "$sc.Description = 'Enfestos Charth — Sistema de Otimizacao de Corte'; " ^
    "$sc.WindowStyle = 1; " ^
    "$sc.Save()" >nul 2>&1

if exist "%ATALHO%" (
    echo         OK - Atalho criado na Area de Trabalho.
) else (
    echo         Aviso: atalho nao foi criado, mas o programa funciona normalmente.
    echo         Para abrir, dê duplo clique em PCP_Enfestos.vbs
)

:: ============================================================
:testar
:: ETAPA 4 — Testar instalacao
:: ============================================================
echo.
echo   [4/4]  Testando instalacao...

%PYTHON% -c "import openpyxl; print('OK')" >nul 2>&1
if !errorlevel! neq 0 goto erro_openpyxl

if not exist "%VBS%" (
    echo         Aviso: PCP_Enfestos.vbs nao encontrado em %APP_DIR%
    echo         Verifique se o zip foi extraido corretamente.
)

:: ============================================================
:sucesso
:: ============================================================
echo.
echo  ============================================================
echo.
echo   INSTALACAO CONCLUIDA COM SUCESSO!
echo.
echo   Para abrir o programa:
echo.
echo   1. Dê duplo clique em "Enfestos Charth" na Area de Trabalho
echo   2. Ou dê duplo clique em PCP_Enfestos.vbs nesta pasta
echo.
echo   O navegador abrira automaticamente.
echo.
echo  ============================================================
echo.

set /p "ABRIR=   Deseja abrir o programa agora? (S/N): "
if /i "!ABRIR!"=="S" (
    echo.
    echo   Abrindo Enfestos Charth...
    start "" wscript.exe "%VBS%"
    timeout /t 2 /nobreak >nul
)

echo.
echo   Pressione qualquer tecla para fechar.
pause >nul
exit /b 0

:: ============================================================
:erro_download
echo.
echo  ============================================================
echo   ATENCAO — Sem conexao com a internet
echo  ============================================================
echo.
echo   Nao foi possivel baixar o Python automaticamente.
echo.
echo   SOLUCAO MANUAL:
echo   1. Acesse:  https://www.python.org/downloads/
echo   2. Clique em "Download Python" e execute o arquivo baixado
echo   3. IMPORTANTE: marque a opcao "Add Python to PATH"
echo   4. Apos instalar, execute este instalador novamente
echo.
pause
exit /b 1

:erro_python
echo.
echo  ============================================================
echo   ATENCAO — Python nao foi instalado
echo  ============================================================
echo.
echo   SOLUCAO MANUAL:
echo   1. Acesse:  https://www.python.org/downloads/
echo   2. Clique em "Download Python" e execute o arquivo baixado  
echo   3. IMPORTANTE: marque "Add Python to PATH" durante a instalacao
echo   4. Apos instalar, execute este instalador novamente
echo.
pause
exit /b 1

:erro_openpyxl
echo.
echo  ============================================================
echo   ATENCAO — Erro ao instalar bibliotecas
echo  ============================================================
echo.
echo   SOLUCAO MANUAL:
echo   1. Abra o Prompt de Comando (CMD)
echo   2. Digite:  pip install openpyxl pdfplumber
echo   3. Aguarde concluir
echo   4. Tente abrir o programa com duplo clique em PCP_Enfestos.vbs
echo.
pause
exit /b 1
