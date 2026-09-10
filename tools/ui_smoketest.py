"""Constroi a janela sem interface e exercita os caminhos que nao envolvem
clique. Roda dentro do 3dsmaxbatch, com Qt em modo offscreen.

    set QT_QPA_PLATFORM=offscreen
    3dsmaxbatch.exe tools/ui_smoketest.py -sceneFile "<qualquer.max>"

Nao substitui abrir a janela de verdade -- layout e usabilidade so' se veem
olhando. Serve para pegar erro de API do PySide e de nome de widget antes de
o usuario descobrir com a janela na cara.

Escreve o resultado num .json, porque o 3dsmaxbatch nao captura o stdout do
Python.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, r"C:/dev/USD_Builder_Asset/src")

RESULT = os.environ.get(
    "MAX2SOLARIS_SMOKE",
    r"C:/Users/Matheus/Downloads/MaxToLama/Testes/solaris/_smoketest.json")

res = {"passos": [], "erros": []}


def passo(nome, fn):
    try:
        valor = fn()
        res["passos"].append({"passo": nome, "ok": True, "valor": repr(valor)[:200]})
        return valor
    except Exception as e:
        res["passos"].append({"passo": nome, "ok": False, "erro": str(e)})
        res["erros"].append("%s: %s\n%s" % (nome, e, traceback.format_exc()))
        return None


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    QtWidgets = passo("importar PySide6",
                      lambda: __import__("PySide6.QtWidgets", fromlist=["QtWidgets"]))
    if QtWidgets is None:
        return

    app = passo("QApplication",
                lambda: QtWidgets.QApplication.instance()
                or QtWidgets.QApplication([]))
    if app is None:
        return

    win_mod = passo("importar usd_builder_asset.ui.window",
                    lambda: __import__("usd_builder_asset.ui.window",
                                       fromlist=["window"]))
    if win_mod is None:
        return

    w = passo("construir ExportWindow", lambda: win_mod.ExportWindow())
    if w is None:
        return

    # settings -> widgets -> settings tem que dar a volta sem perder nada
    def roundtrip():
        w.edDir.setText("C:/tmp/alvo")
        w.edNome.setText("MeuAsset")
        w.edLod.setText("LOD0")
        w.ckSel.setChecked(False)
        w.ckPorObj.setChecked(True)
        w.cbUp.setCurrentText("Z")
        s = w._para_settings()
        assert s.target_dir == "C:/tmp/alvo", s.target_dir
        assert s.asset_name == "MeuAsset", s.asset_name
        assert s.lod_token == "LOD0", s.lod_token
        assert s.selection_only is False
        assert s.one_asset_per_object is True
        assert s.up_axis == "Z", s.up_axis
        return s.to_dict()

    passo("roundtrip settings<->widgets", roundtrip)

    # o preview nao pode escrever nada nem estourar com a cena carregada
    def preview():
        w.edDir.setText("C:/tmp/alvo")
        w.ckPorObj.setChecked(False)
        w._prever()
        return w.log.toPlainText()

    passo("botao 'Ver o que vai sair'", preview)

    # validacao tem que reclamar de destino vazio
    def validacao():
        w.edDir.setText("")
        s = w._para_settings()
        p = s.problems()
        assert p, "destino vazio deveria dar problema"
        return p

    passo("validacao de destino vazio", validacao)

    passo("contagem de widgets",
          lambda: len(w.findChildren(QtWidgets.QWidget)))


try:
    main()
except Exception as e:
    res["erros"].append("fatal: %s\n%s" % (e, traceback.format_exc()))

d = os.path.dirname(RESULT)
if d and not os.path.isdir(d):
    os.makedirs(d)
with open(RESULT, "w", encoding="utf-8") as fh:
    json.dump(res, fh, indent=1, ensure_ascii=False)
