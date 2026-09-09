"""Teste do export sem interface, via 3dsmaxbatch.

    3dsmaxbatch.exe tools/headless_export.py -sceneFile "<arquivo.max>"

Le a pasta destino de MAX2SOLARIS_OUT (ou usa um default), roda o export e
imprime o relatorio. Existe para que o caminho de export seja testavel sem
clicar em nada -- a janela nao pode ser o unico jeito de rodar.
"""
import os
import sys

sys.path.insert(0, r"C:/dev/max2solaris/src")

from max2solaris.settings import Settings          # noqa: E402
from max2solaris import exporter                   # noqa: E402

out = os.environ.get("MAX2SOLARIS_OUT",
                     r"C:/Users/Matheus/Downloads/MaxToLama/Testes/solaris")

s = Settings(target_dir=out, selection_only=False, one_asset_per_object=False,
             collect_textures=False)
print("=" * 60)
print("max2solaris headless -> %s" % out)
print("=" * 60)
try:
    res = exporter.export(s)
    for linha in exporter.report_lines(res):
        print(linha)
except Exception as e:
    print("FALHOU: %s" % e)
    import traceback
    traceback.print_exc()
