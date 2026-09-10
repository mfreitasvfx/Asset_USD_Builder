"""Export FBX do 3ds Max no padrao que o Asset_USD_Builder consome.

Sem PySide aqui de proposito: assim o export inteiro roda pelo 3dsmaxbatch,
sem interface, e da' pra testar sem clicar em nada.
"""
import json
import os

from pymxs import runtime as rt

from . import naming


class ExportError(RuntimeError):
    pass


# Parametros do FBX Exporter. Setados um a um e tolerando ausencia: os nomes
# mudam entre versoes do plugin FBX, e falhar o export inteiro porque uma
# flag sumiu seria pior do que exportar sem ela e avisar.
def _fbx_params(s):
    return [
        ("Animation", bool(s.animation)),
        ("Cameras", bool(s.cameras)),
        ("Lights", bool(s.lights)),
        ("Shape", True),                 # morphs
        ("Skin", True),
        ("SmoothingGroups", bool(s.smoothing_groups)),
        ("SmoothMeshExport", bool(s.smooth_mesh)),
        ("TangentSpaceExport", bool(s.tangents)),
        ("Preserveinstances", bool(s.preserve_instances)),
        ("Triangulate", bool(s.triangulate)),
        ("EmbedTextures", bool(s.embed_textures)),
        ("GeomAsBone", False),
        ("PointCache", False),
        ("SelectionSetExport", False),
        ("ShowWarnings", False),
        ("GenerateLog", False),
        ("ASCII", bool(s.ascii)),
        # Os dois que mais causam asset deitado ou 100x fora de escala:
        ("UpAxis", str(s.up_axis)),
        ("ConvertUnit", str(s.units)),
        ("AxisConversionMethod", "Animation"),
        ("FileVersion", str(s.fbx_version)),
    ]


def _apply_fbx_params(s, avisos):
    try:
        rt.FBXExporterSetParam(rt.Name("ResetExport"))
    except Exception:
        avisos.append("FBXExporterSetParam ResetExport falhou; as opcoes "
                      "anteriores do FBX podem estar valendo.")
    for nome, valor in _fbx_params(s):
        try:
            rt.FBXExporterSetParam(rt.Name(nome), valor)
        except Exception:
            avisos.append("opcao FBX ignorada (nao existe nesta versao): %s"
                          % nome)


# --------------------------------------------------------------------------

def scene_asset_name():
    base = str(rt.maxFileName) or ""
    return naming.sanitize(os.path.splitext(base)[0]) if base else "untitled"


def _top_level_nodes(selection_only):
    nodes = list(rt.selection) if selection_only else list(rt.objects)
    out = []
    for o in nodes:
        try:
            if o.parent is None:
                out.append(o)
        except Exception:
            out.append(o)
    return out or nodes


def _select(nodes):
    rt.clearSelection()
    if nodes:
        rt.select(nodes)


def _export_fbx(path, avisos):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    ok = rt.exportFile(path, rt.Name("noPrompt"), selectedOnly=True,
                       using=rt.FBXEXP)
    if ok is False or not os.path.isfile(path):
        raise ExportError("o FBX nao foi escrito: %s" % path)
    return path


# --------------------------------------------------------------------------

def export(settings):
    """Roda o export. Devolve um dict com o resultado."""
    s = settings
    problemas = s.problems()
    if problemas:
        raise ExportError("; ".join(problemas))

    avisos = []
    _apply_fbx_params(s, avisos)

    root = str(s.target_dir).replace("\\", "/").rstrip("/")
    nome_cena = naming.sanitize(s.asset_name) if str(s.asset_name).strip() \
        else scene_asset_name()

    selecao_original = list(rt.selection)
    escritos = []
    try:
        if s.one_asset_per_object:
            alvos = _top_level_nodes(s.selection_only)
            if not alvos:
                raise ExportError("Nada para exportar (selecao vazia?).")
            for o in alvos:
                asset = naming.sanitize(str(o.name))
                arq = naming.geo_filename(asset, lod=s.lod_token)
                caminho = "%s/%s" % (naming.asset_dir(root, asset), arq)
                _select([o])
                escritos.append(_export_fbx(caminho, avisos))
        else:
            alvos = (list(rt.selection) if s.selection_only
                     else list(rt.objects))
            if not alvos:
                raise ExportError("Nada para exportar (selecao vazia?).")
            arq = naming.geo_filename(nome_cena, lod=s.lod_token)
            caminho = "%s/%s" % (naming.asset_dir(root, nome_cena), arq)
            _select(alvos)
            escritos.append(_export_fbx(caminho, avisos))
    finally:
        _select(selecao_original)

    resultado = {
        "arquivos": escritos,
        "avisos": avisos,
        "settings": s.to_dict(),
        "cena": str(rt.maxFilePath) + str(rt.maxFileName),
    }

    if s.collect_textures:
        from . import textures
        movidas, faltando = textures.collect(root, escritos)
        resultado["texturas"] = len(movidas)
        avisos.extend("textura nao encontrada: %s" % m for m in faltando)
    else:
        # A pasta do asset sem textura faz o Asset_USD_Builder achar o FBX
        # mas nao construir material nenhum. Melhor dizer do que deixar o
        # usuario descobrir no Houdini.
        avisos.append("Texturas nao foram copiadas (opcao desligada). O "
                      "Asset_USD_Builder vai achar a geometria, mas nao tera "
                      "mapas para montar o material.")

    if s.write_report:
        for caminho in escritos:
            rel = os.path.join(os.path.dirname(caminho), "_usd_builder_asset.json")
            try:
                with open(rel, "w", encoding="utf-8") as fh:
                    json.dump(resultado, fh, indent=1, ensure_ascii=False)
            except Exception as e:
                avisos.append("nao consegui escrever o relatorio: %s" % e)

    return resultado


def report_lines(resultado):
    """Texto curto para o Listener e para a janela."""
    linhas = ["%d arquivo(s):" % len(resultado["arquivos"])]
    linhas += ["   " + a for a in resultado["arquivos"]]
    if resultado.get("texturas") is not None:
        linhas.append("texturas copiadas: %s" % resultado["texturas"])
    if resultado["avisos"]:
        linhas.append("")
        linhas.append("avisos (%d):" % len(resultado["avisos"]))
        linhas += ["   " + a for a in resultado["avisos"]]
    return linhas
