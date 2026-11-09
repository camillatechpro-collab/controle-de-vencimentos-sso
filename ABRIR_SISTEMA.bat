@echo off
cd /d "%~dp0"
title Controle de Vencimentos SST - NAO FECHE ESTA JANELA
echo.
echo  Abrindo o sistema... aguarde. O navegador vai abrir sozinho.
echo  Para DESLIGAR o sistema, feche esta janela.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py
echo.
echo  O sistema parou. Tire um print desta tela se apareceu algum erro.
pause
