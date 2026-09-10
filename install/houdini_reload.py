"""Cole isto no Python Shell do Houdini (ou num botao de shelf).

Recarrega o max2solaris editado no VS Code e monta o asset da pasta --
SEM reiniciar o Houdini. Ajuste `PASTA`/`SAIDA` e rode de novo a vontade.
"""
import sys

PASTA = r"M:/Megascans_Library/Downloaded/3d/3d_historical_wjuvdeyqx"
SAIDA = r"C:/Users/Matheus/Downloads/MaxToLama/Testes/lops"

p = r"C:/dev/max2solaris/src"
if p not in sys.path:
    sys.path.insert(0, p)
for m in [k for k in list(sys.modules) if k.startswith("max2solaris")]:
    del sys.modules[m]

from max2solaris import library, profiles
from max2solaris.lops import builder

a = library.scan(PASTA)
perfil, _etapas, _avisos = profiles.plan(a)
print(a.resumo())
res = builder.build_asset(a, perfil, out_dir=SAIDA, write=False)
print(res.resumo())
