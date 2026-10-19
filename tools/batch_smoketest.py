"""Exercita o lote sem clicar: lista a pasta, constroi a janela offscreen e
exporta os N primeiros .max de verdade. Roda dentro do 3dsmaxbatch.

    set QT_QPA_PLATFORM=offscreen
    3dsmaxbatch.exe tools/batch_smoketest.py -sceneFile "<qualquer.max>"

Variaveis:
    MAX2SOLARIS_LOTE_ORIGEM   pasta com os .max (default: Maxtree Vol 93)
    MAX2SOLARIS_LOTE_OUT      pasta destino
    MAX2SOLARIS_LOTE_N        quantos arquivos exportar (default 2)

Escreve o resultado num .json, porque o 3dsmaxbatch nao captura o stdout do
Python.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))  # Linux/Windows

ORIGEM = os.environ.get(
    "MAX2SOLARIS_LOTE_ORIGEM",
    r"C:/Users/Matheus/Downloads/Maxtree - Plants Models Vol. 93/"
    r"MT_PM_V93_Forest_Pack_Mesh_VRay/MT_PM_V93")
OUT = os.environ.get(
    "MAX2SOLARIS_LOTE_OUT",
    r"C:/Users/Matheus/Downloads/MaxToLama/Testes/solaris/_lote_smoke")
N = int(os.environ.get("MAX2SOLARIS_LOTE_N", "2"))
RESULT = os.path.join(OUT, "_smoketest.json")

res = {"passos": [], "erros": []}


def passo(nome, fn):
    try:
        valor = fn()
        res["passos"].append({"passo": nome, "ok": True, "valor": repr(valor)[:300]})
        return valor
    except Exception as e:
        res["passos"].append({"passo": nome, "ok": False, "erro": str(e)})
        res["erros"].append("%s: %s\n%s" % (nome, e, traceback.format_exc()))
        return None


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    batch = passo("importar usd_builder_asset.batch",
                  lambda: __import__("usd_builder_asset.batch", fromlist=["batch"]))
    if batch is None:
        return

    arquivos = passo("list_max_files", lambda: batch.list_max_files(ORIGEM))
    if not arquivos:
        res["erros"].append("nenhum .max em %s" % ORIGEM)
        return
    passo("preview_of do primeiro", lambda: batch.preview_of(arquivos[0]))

    # --- janela offscreen ---
    QtWidgets = passo("importar PySide6",
                      lambda: __import__("PySide6.QtWidgets", fromlist=["QtWidgets"]))
    app = passo("QApplication",
                lambda: QtWidgets.QApplication.instance()
                or QtWidgets.QApplication([]))
    win_mod = passo("importar ui.batch_window",
                    lambda: __import__("usd_builder_asset.ui.batch_window",
                                       fromlist=["batch_window"]))
    if win_mod is not None and app is not None:
        w = passo("construir BatchWindow", lambda: win_mod.BatchWindow())
        if w is not None:
            def listar():
                w.edOrigem.setText(ORIGEM)
                w._listar()
                assert w.lista.count() == len(arquivos), (w.lista.count(), len(arquivos))
                assert len(w._marcados()) == len(arquivos)
                return w.lista.count()
            passo("lista carregada com todos marcados", listar)

            def filtro():
                w.edFiltro.setText("allium")
                vis = [it for it in w._itens(so_visiveis=True)]
                assert vis and all("allium" in it.text().lower() for it in vis)
                w._marcar(False)            # so' os visiveis
                n = len(w._marcados())
                assert n == len(arquivos) - len(vis), (n, len(arquivos), len(vis))
                w.edFiltro.setText("")
                w._marcar(True)
                return len(vis)
            passo("filtro + Nenhum agem so' no visivel", filtro)

            def prever():
                w.edDest.setText(OUT)
                w._prever()
                txt = w.log.toPlainText()
                assert "_High.fbx" in txt, txt[:200]
                return txt.splitlines()[:3]
            passo("botao 'Ver o que vai sair'", prever)

    # --- export de verdade ---
    from usd_builder_asset.settings import Settings
    s = Settings.load()
    s.target_dir = OUT
    alvo = arquivos[:N]
    progresso = []
    rel = passo("export_files(%d arquivos)" % len(alvo),
                lambda: batch.export_files(
                    alvo, s,
                    on_progress=lambda i, t, p, it: progresso.append(
                        (i, t, os.path.basename(p), it["ok"]))))
    res["progresso"] = progresso
    if rel is not None:
        res["relatorio"] = rel
        res["linhas"] = batch.report_lines(rel)
        for it in rel["itens"]:
            for a in it["arquivos"]:
                res["passos"].append({"passo": "existe " + a,
                                      "ok": os.path.isfile(a),
                                      "valor": os.path.getsize(a) if os.path.isfile(a) else 0})


try:
    main()
except Exception as e:
    res["erros"].append("fatal: %s\n%s" % (e, traceback.format_exc()))

if not os.path.isdir(OUT):
    os.makedirs(OUT)
with open(RESULT, "w", encoding="utf-8") as fh:
    json.dump(res, fh, indent=1, ensure_ascii=False)
