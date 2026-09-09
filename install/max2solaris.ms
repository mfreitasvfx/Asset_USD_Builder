-- max2solaris : abre a janela de export
-- Rode com: fileIn @"C:\dev\max2solaris\install\max2solaris.ms"
python.Execute "import sys"
python.Execute "p = r'C:/dev/max2solaris/src'"
python.Execute "if p not in sys.path: sys.path.insert(0, p)"
-- recarrega a cada execucao, pra editar no VS Code sem reiniciar o Max
python.Execute "for _m in [k for k in list(sys.modules) if k.startswith('max2solaris')]: del sys.modules[_m]"
python.Execute "import max2solaris.ui.window as _w; _w.show()"
