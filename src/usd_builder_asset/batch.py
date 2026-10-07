"""Lote: varios arquivos .max -> um FBX por arquivo, no padrao do HDA.

Feito para as bibliotecas em que cada .max e' um asset (Maxtree: 132 .max
numa pasta, cada um com o .jpg de preview ao lado). Abre um arquivo por vez
na sessao do Max, roda o mesmo `exporter.export` da janela e passa para o
proximo. Erro num arquivo nao para o lote: fica no relatorio.

Sem PySide aqui, pelo mesmo motivo do exporter: roda pelo 3dsmaxbatch.
"""
import json
import os
import time

from pymxs import runtime as rt

from . import exporter, naming

RELATORIO = "_usd_builder_asset_lote.json"


def list_max_files(pasta):
    """Os .max da pasta (sem recursao), em ordem de nome."""
    pasta = str(pasta or "").strip()
    if not os.path.isdir(pasta):
        return []
    out = []
    for nome in sorted(os.listdir(pasta), key=str.lower):
        if nome.lower().endswith(".max") and not nome.startswith("~"):
            out.append(os.path.join(pasta, nome).replace("\\", "/"))
    return out


def preview_of(max_path):
    """O .jpg/.png de mesmo nome ao lado do .max, se existir."""
    base = os.path.splitext(max_path)[0]
    for ext in (".jpg", ".jpeg", ".png"):
        if os.path.isfile(base + ext):
            return base + ext
    return None


def asset_name_of(max_path):
    return naming.sanitize(os.path.splitext(os.path.basename(max_path))[0])


def target_of(max_path, settings):
    """Onde o FBX deste arquivo vai cair -- para mostrar antes de escrever."""
    asset = asset_name_of(max_path)
    return "%s/%s" % (naming.asset_dir(settings.target_dir, asset),
                      naming.geo_filename(asset, lod=settings.lod_token))


def _settings_para_lote(settings):
    """Copia dos settings com o que o lote exige: cena inteira, um asset por
    arquivo, nome vindo do arquivo."""
    s = settings.__class__.from_dict(settings.to_dict())
    s.selection_only = False
    s.one_asset_per_object = False
    s.asset_name = ""
    return s


def _abrir(max_path):
    # quiet: sem dialogo de arquivo faltando / unidades diferentes.
    # useFileUnits: a cena fica nas unidades do arquivo; quem converte para
    # a saida e' o ConvertUnit do FBX, ja' setado pelo exporter.
    ok = rt.loadMaxFile(max_path, useFileUnits=True, quiet=True)
    if ok is False:
        raise exporter.ExportError("nao consegui abrir: %s" % max_path)


def export_files(paths, settings, on_progress=None):
    """Exporta cada .max de `paths`. Devolve o relatorio (dict).

    on_progress(i, total, max_path, item) e' chamado depois de cada arquivo;
    `item` e' o dict daquele arquivo (ok/erro/avisos). A UI usa para
    atualizar a barra sem esta funcao saber que existe UI.
    """
    s = _settings_para_lote(settings)
    problemas = s.problems()
    if problemas:
        raise exporter.ExportError("; ".join(problemas))

    itens = []
    inicio = time.time()
    total = len(paths)
    for i, p in enumerate(paths):
        item = {"max": p, "ok": False, "arquivos": [], "avisos": []}
        t0 = time.time()
        try:
            _abrir(p)
            res = exporter.export(s)
            item["ok"] = True
            item["arquivos"] = res["arquivos"]
            item["avisos"] = res["avisos"]
            if res.get("texturas") is not None:
                item["texturas"] = res["texturas"]
        except Exception as e:
            item["erro"] = str(e)
        item["segundos"] = round(time.time() - t0, 1)
        itens.append(item)
        if on_progress:
            on_progress(i + 1, total, p, item)

    rel = {
        "pasta_destino": s.target_dir,
        "total": total,
        "ok": sum(1 for it in itens if it["ok"]),
        "falhas": [it["max"] for it in itens if not it["ok"]],
        "segundos": round(time.time() - inicio, 1),
        "settings": s.to_dict(),
        "itens": itens,
    }
    _escrever_relatorio(rel)
    return rel


def _escrever_relatorio(rel):
    # O 3dsmaxbatch nao captura o stdout do Python; o .json na pasta
    # destino e' o que sobra para ver o que aconteceu.
    try:
        d = rel["pasta_destino"]
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(os.path.join(d, RELATORIO), "w", encoding="utf-8") as fh:
            json.dump(rel, fh, indent=1, ensure_ascii=False)
    except Exception as e:
        rel.setdefault("avisos", []).append(
            "nao consegui escrever o relatorio do lote: %s" % e)


def report_lines(rel):
    """Resumo curto para o Listener e para a janela."""
    linhas = ["%d de %d exportado(s) em %ss" % (rel["ok"], rel["total"],
                                                 rel["segundos"])]
    for it in rel["itens"]:
        nome = os.path.basename(it["max"])
        if it["ok"]:
            aviso = ("  (%d aviso(s))" % len(it["avisos"])) if it["avisos"] else ""
            linhas.append("   ok   %s%s" % (nome, aviso))
        else:
            linhas.append("   ERRO %s: %s" % (nome, it.get("erro", "?")))
    linhas.append("relatorio: %s" % os.path.join(rel["pasta_destino"], RELATORIO))
    return linhas
