@echo off
rem Atualiza o USD_Builder_Asset no Windows (C:\dev\USD_Builder_Asset) a partir do GitHub.
rem Dois cliques e pronto. Descarta so diferencas de quebra de linha (CRLF) antes do pull.
set REPO=C:\dev\USD_Builder_Asset
set URL=https://github.com/mfreitasvfx/Asset_USD_Builder.git
if not exist "%REPO%\.git" (
    echo Pasta nao encontrada, clonando em %REPO% ...
    git clone "%URL%" "%REPO%" || goto erro
)
cd /d "%REPO%" || goto erro
git config core.autocrlf true
git checkout -- .
git pull || goto erro
echo.
echo Atualizado. Versao atual:
git log --oneline -1
echo.
echo No Houdini: clique de novo no botao da shelf (ou rode install/houdini_reload.py) para recarregar.
pause
exit /b 0
:erro
echo.
echo Deu erro. Confira se o git esta instalado e logado no GitHub (gh auth login ou credencial salva).
pause
exit /b 1
