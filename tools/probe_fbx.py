"""O que um FBX entrega quando entra no Houdini.

    hython tools/probe_fbx.py <arquivo.fbx> [saida.json]

Responde as perguntas que decidem o builder:
  - quantos objetos vem, e com que nomes
  - como vem a atribuicao de material (atributo? grupo? subset?)
  - os nomes de material batem com os nomes de parte que o scanner extrai
    das texturas?

Esse ultimo e' o que importa: se baterem, o bind e' direto; se nao, precisa
de uma tabela de traducao por biblioteca.
"""
import json
import os
import sys

import hou

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))  # Linux/Windows
from usd_builder_asset import library  # noqa: E402


def sop_import(caminho):
    """Le o FBX num File SOP. E' o caminho mais simples e o que o builder
    usaria dentro de um componentgeometry."""
    geo = hou.node("/obj").createNode("geo", "probe")
    f = geo.createNode("file", "in")
    f.parm("file").set(caminho.replace("\\", "/"))
    f.setDisplayFlag(True)
    return f


def descreve(node):
    g = node.geometry()
    out = {
        "pontos": len(g.points()),
        "prims": len(g.prims()),
        "attr_prim": sorted(a.name() for a in g.primAttribs()),
        "attr_point": sorted(a.name() for a in g.pointAttribs()),
        "attr_detail": sorted(a.name() for a in g.globalAttribs()),
        "grupos_prim": sorted(x.name() for x in g.primGroups())[:40],
        "n_grupos_prim": len(g.primGroups()),
    }

    # nomes de objeto e de material, os dois candidatos a "parte"
    for attr in ("name", "path", "shop_materialpath", "material_override",
                 "usdmaterialpath"):
        a = g.findPrimAttrib(attr)
        if a is None:
            continue
        try:
            valores = sorted(set(a.strings())) if a.dataType() == \
                hou.attribData.String else []
        except Exception:
            valores = []
        out["valores_" + attr] = valores[:40]
        out["n_" + attr] = len(valores)
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    fbx = sys.argv[1]
    saida = sys.argv[2] if len(sys.argv) > 2 else \
        os.path.splitext(fbx)[0] + "_fbxprobe.json"

    res = {"fbx": fbx, "existe": os.path.isfile(fbx)}
    if not res["existe"]:
        _grava(saida, res)
        return 1

    try:
        node = sop_import(fbx)
        node.cook(force=True)
        res["geo"] = descreve(node)
        res["erros_cook"] = list(node.errors())
    except Exception as e:
        import traceback
        res["erro"] = "%s\n%s" % (e, traceback.format_exc())
        _grava(saida, res)
        return 1

    # o scanner ve as mesmas "partes" que o FBX traz como material?
    a = library.scan(os.path.dirname(fbx))
    res["scanner"] = {"library": a.library, "partes": sorted(a.parts)}

    mats = res["geo"].get("valores_shop_materialpath") or []
    partes = set(a.parts)
    mats_curtos = {m.rsplit("/", 1)[-1] for m in mats}
    res["cruzamento"] = {
        "materiais_no_fbx": sorted(mats_curtos)[:40],
        "batem_exato": sorted(mats_curtos & partes),
        "so_no_fbx": sorted(mats_curtos - partes)[:20],
        "so_nas_texturas": sorted(partes - mats_curtos)[:20],
    }
    _grava(saida, res)
    return 0


def _grava(caminho, dados):
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
