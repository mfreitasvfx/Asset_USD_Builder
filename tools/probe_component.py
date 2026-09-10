"""Mede os nos do Component Builder antes de o builder usa-los.

    hython tools/probe_component.py

Perguntas que respondem o desenho:
  1. quais parms componentgeometry / componentmaterial / componentoutput tem
  2. o componentgeometry cria GeomSubsets a partir de shop_materialpath?
  3. o componentmaterial casa material com subset pelo NOME sozinho?
     (e' o que o Matheus apontou: "o shopmaterial casa automaticamente
     pelos comp material")
"""
import json
import os
import sys

import hou

SAIDA = os.environ.get(
    "PROBE_OUT",
    r"C:/dev/USD_Builder_Asset/tools/component_schema.json")

res = {"houdini": hou.applicationVersionString()}

stage = hou.node("/stage")
cg = stage.createNode("componentgeometry", "cgeo")
cm = stage.createNode("componentmaterial", "cmat")
co = stage.createNode("componentoutput", "cout")

for rot, n in (("componentgeometry", cg), ("componentmaterial", cm),
               ("componentoutput", co)):
    res[rot] = {
        "type": n.type().name(),
        "parms": [p.name() for p in n.parms()],
        "inputs": list(n.inputNames()),
    }

# dentro do componentgeometry: o sopnet e seus outputs
sop = cg.node("sopnet/geo")
res["componentgeometry"]["sopnet"] = sop.path() if sop else None
if sop:
    res["componentgeometry"]["sop_children"] = [
        (c.name(), c.type().name()) for c in sop.children()]

# geometria de teste: 2 quads com shop_materialpath diferentes
if sop:
    import hou as _h
    wr = sop.createNode("attribwrangle", "fake")
    grid = sop.createNode("grid")
    grid.parm("rows").set(3)
    grid.parm("cols").set(3)   # 3x3 pontos = 4 prims
    wr.setInput(0, grid)
    wr.parm("class").set(1)  # primitives
    wr.parm("snippet").set(
        's@shop_materialpath = @primnum % 2 == 0 ? "MatA" : "MatB";\n'
        's@name = "Piece_" + itoa(@primnum);')
    out_def = sop.node("default")
    if out_def:
        out_def.setInput(0, wr)

# particionar por shop_materialpath -- o parm que faz subset
cg.parm("partitionattribs").set("shop_materialpath")
# sem prefixo: o subset chama "MatA", que e' o que casa com o material
cg.parm("prefixpartitionsubsets").set(0)

# os dois parms de bind do proprio componentgeometry
for nome in ("bindmaterials", "materialbindsubsets"):
    pp = cg.parm(nome)
    if pp is not None:
        t = pp.parmTemplate()
        res.setdefault("parms_bind", {})[nome] = {
            "tipo": type(t).__name__, "default": pp.eval(),
            "menu": list(t.menuItems()) if hasattr(t, "menuItems") else None,
            "labels": list(t.menuLabels()) if hasattr(t, "menuLabels") else None}
cg.parm("bindmaterials").set("*")   # padrao de subsets a bindar

# o stage do componentgeometry: virou subset?
try:
    st = cg.stage()
    prims = []
    for p in st.Traverse():
        prims.append("%s [%s]" % (p.GetPath(), p.GetTypeName()))
    res["stage_componentgeometry"] = prims
except Exception as e:
    res["stage_componentgeometry"] = "ERRO: %s" % e

# materiallibrary com MatA/MatB + componentmaterial: casa sozinho?
ml = stage.createNode("materiallibrary", "mats")
# o componentmaterial procura materiais sob a raiz do componente -- e' o
# /ASSET/mtl/ que os scripts da Rebelway tambem usam
ml.parm("matpathprefix").set("/ASSET/mtl/")
for nm in ("MatA", "MatB"):
    s = ml.createNode("mtlxstandard_surface", nm)
cm.setInput(0, cg)
cm.setInput(1, ml)
try:
    st2 = cm.stage()
    binds = []
    from pxr import UsdShade
    for p in st2.Traverse():
        rel = UsdShade.MaterialBindingAPI(p).GetDirectBindingRel()
        tg = rel.GetTargets() if rel else []
        if tg:
            binds.append("%s -> %s" % (p.GetPath(), tg[0]))
    res["binds_componentmaterial"] = binds
except Exception as e:
    res["binds_componentmaterial"] = "ERRO: %s" % e

with open(SAIDA, "w", encoding="utf-8") as fh:
    json.dump(res, fh, indent=1, ensure_ascii=False)
print("escrito:", SAIDA)
