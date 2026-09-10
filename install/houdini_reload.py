"""Cole isto no Python Shell do Houdini (ou num botao de shelf).

Abre a JANELA do usd_builder_asset. Rode de novo a vontade: recarrega os modulos
editados no VS Code e reabre -- sem reiniciar o Houdini.
"""
import sys

p = r"C:/dev/USD_Builder_Asset/src"
if p not in sys.path:
    sys.path.insert(0, p)
for m in [k for k in list(sys.modules) if k.startswith("usd_builder_asset")]:
    del sys.modules[m]

from usd_builder_asset.ui import houdini_panel
houdini_panel.show()
