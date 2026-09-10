"""Cole isto no Python Shell do Houdini (ou num botao de shelf).

Abre a JANELA do max2solaris. Rode de novo a vontade: recarrega os modulos
editados no VS Code e reabre -- sem reiniciar o Houdini.
"""
import sys

p = r"C:/dev/max2solaris/src"
if p not in sys.path:
    sys.path.insert(0, p)
for m in [k for k in list(sys.modules) if k.startswith("max2solaris")]:
    del sys.modules[m]

from max2solaris.ui import houdini_panel
houdini_panel.show()
