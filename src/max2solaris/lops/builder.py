"""O builder em LOPs: Asset (do scanner) -> componente USD no Solaris.

    componentgeometry  (File SOP + particao por shop_materialpath)
        -> componentmaterial  (materiallibrary em /ASSET/mtl + bind por parte)
            -> componentoutput (rootprim = nome do asset)

TRES FATOS MEDIDOS SUSTENTAM ISSO (probe_component.py, probe_fbx.py):

1. `partitionattribs="shop_materialpath"` + `prefixpartitionsubsets=0` faz o
   componentgeometry criar um GeomSubset por material, com o NOME LIMPO do
   material -- e o atributo `name` vira um Mesh por peca.
2. Os nomes de material do FBX batem 100% com as partes que o scanner tira
   das texturas (6/6 Maxtree, 28/28 KitBash). Entao subset e material se
   encontram por nome, sem tabela.
3. O componentmaterial NAO casa por nome sozinho (medido; e o hip do video
   usa so' um Default). O casamento aqui e' explicito: uma entrada de
   multiparm por parte. Deterministico e conferivel -- e da' aviso quando
   uma parte nao tem material.

O bind e' o do max2lama repetido em outro contexto: explicito > magico.
"""
import os

import hou

from .. import fbx as _fbx
from .. import naming as _naming
from . import materials as _mats


class Result(object):
    def __init__(self):
        self.asset_name = None
        self.nodes = {}
        self.parts_bound = []
        self.parts_missing = []
        self.usd_path = None
        self.avisos = []

    def warn(self, msg):
        self.avisos.append(msg)

    def resumo(self):
        linhas = ["%s:" % self.asset_name,
                  "   partes ligadas : %d" % len(self.parts_bound)]
        if self.parts_missing:
            linhas.append("   sem material   : %s" % self.parts_missing)
        if self.usd_path:
            ok = os.path.isfile(self.usd_path)
            linhas.append("   usd            : %s (%s)"
                          % (self.usd_path, "escrito" if ok else "NAO escrito"))
        for a in self.avisos:
            linhas.append("   ! %s" % a)
        return "\n".join(linhas)


def build_asset(asset, profile, out_dir=None, asset_name=None,
                renderers=("karma", "arnold"), parent=None,
                lod=None, write=True, disp_scale=0.01):
    """Monta um componente para `asset` e (opcionalmente) escreve o USD.

    asset_name: para pacotes `asset_grain == "object"` (KitBash), o nome do
    objeto a extrair do arquivo; None em pacotes pasta-e-asset.
    """
    res = Result()
    nome = asset_name or asset.name
    res.asset_name = nome

    stage = parent or hou.node("/stage")
    net = stage.createNode("subnet", "m2s_" + _fbx.material_key(nome))
    net.moveToGoodPosition()

    # -- geometria -------------------------------------------------------
    lods = profile.lods_for(asset)
    lod = lod or (lods[0] if lods else None)
    geo_path = asset.geometry.get(lod) if lod else asset.default_geo
    if not geo_path:
        res.warn("asset sem geometria; nada a montar")
        return res

    cg = net.createNode("componentgeometry", "geo")
    sop = cg.node("sopnet/geo")
    fnode = _fbx.load_sop(sop, geo_path)
    tail = fnode

    if asset_name is not None:
        # so' as prims deste objeto (KitBash: varios assets no arquivo)
        blast = sop.createNode("blast", "keep_" + _fbx.material_key(nome))
        blast.setInput(0, fnode)
        blast.parm("group").set("@name=%s*" % asset_name)
        blast.parm("grouptype").set(4)      # primitives
        blast.parm("negate").set(1)         # manter, nao deletar
        tail = blast

    sop.node("default").setInput(0, tail)
    cg.parm("partitionattribs").set("shop_materialpath")
    cg.parm("prefixpartitionsubsets").set(0)
    res.nodes["componentgeometry"] = cg

    # -- que subsets existem de fato? ------------------------------------
    # Cozinhamos o stage e lemos, em vez de confiar que toda parte das
    # texturas aparece na malha (no Maxtree metade dos IDs nao aparece).
    subsets = _subset_names(cg, res)

    # -- materiais --------------------------------------------------------
    ml = net.createNode("materiallibrary", "mtl")
    ml.parm("matpathprefix").set("/ASSET/mtl/")

    plant = profile.plant_workflow and asset.plant
    finais = []

    # Asset de material UNICO (Megascans): a malha costuma vir com
    # shop_materialpath generico ('default_material'), entao casar por nome
    # nao faz sentido -- o unico material vai no /ASSET/geo inteiro.
    single = (len(asset.parts) == 1)
    alvo_partes = list(asset.parts) if single else subsets

    for parte in alvo_partes:
        mapas = asset.parts.get(parte)
        if not mapas:
            res.parts_missing.append(parte)
            res.warn("subset '%s' sem jogo de texturas -- sem material "
                     "(vira cinza no render)" % parte)
            continue
        node, avisos = _mats.build_material(
            ml, _naming.usd_prim_name(parte), mapas, renderers=renderers,
            plant=plant, disp_scale=disp_scale)
        res.avisos.extend(avisos)
        res.parts_bound.append(_naming.usd_prim_name(parte))
        finais.append(node)
    ml.layoutChildren()
    # lista EXPLICITA: so' o no final de cada parte vira prim Material.
    # Sem isso o auto-fill publicava tambem o subnet karma e o displacement
    # soltos, poluindo /ASSET/mtl com prims que nada binda.
    ml.parm("materials").set(len(finais))
    for i, node in enumerate(finais, start=1):
        ml.parm("matnode%d" % i).set(node.name())
        ml.parm("matpath%d" % i).set(node.name())
        if ml.parm("assign%d" % i) is not None:
            ml.parm("assign%d" % i).set(0)
    res.nodes["materiallibrary"] = ml

    # -- componentmaterial: bind explicito por parte ----------------------
    cm = net.createNode("componentmaterial", "assign")
    cm.setInput(0, cg)
    cm.setInput(1, ml)
    cm.parm("nummaterials").set(len(res.parts_bound))
    for i, parte in enumerate(res.parts_bound, start=1):
        # material unico: o asset inteiro; senao o subset com o mesmo nome
        # (caminho medido: /ASSET/geo/<mesh>/<parte>)
        padrao = "/ASSET/geo" if single else "/ASSET/geo/*/%s" % parte
        cm.parm("primpattern%d" % i).set(padrao)
        cm.parm("matspecpath%d" % i).set("/ASSET/mtl/%s" % parte)
    res.nodes["componentmaterial"] = cm

    # -- saida ------------------------------------------------------------
    prim = _naming.usd_prim_name(nome)
    co = net.createNode("componentoutput", prim)
    co.setInput(0, cm)
    co.parm("rootprim").set("/" + prim)
    if out_dir:
        usd = "%s/%s/%s.usd" % (str(out_dir).replace("\\", "/").rstrip("/"),
                                nome, nome)
        co.parm("lopoutput").set(usd)
        res.usd_path = usd
    res.nodes["componentoutput"] = co
    net.layoutChildren()

    if write and out_dir:
        try:
            co.parm("execute").pressButton()
        except Exception as e:
            res.warn("execute do componentoutput falhou: %s" % e)
        if res.usd_path and not os.path.isfile(res.usd_path):
            res.warn("componentoutput rodou mas o USD nao existe")

    return res


def _subset_names(cg, res):
    try:
        st = cg.stage()
    except Exception as e:
        res.warn("nao consegui cozinhar o componentgeometry: %s" % e)
        return []
    nomes = []
    for p in st.Traverse():
        if p.GetTypeName() == "GeomSubset":
            n = p.GetName()
            if n not in nomes:
                nomes.append(n)
    if not nomes:
        res.warn("nenhum GeomSubset -- a malha nao tem shop_materialpath?")
    return nomes


def list_assets_in_file(geo_path):
    """Os assets dentro de um arquivo (KitBash). Le num SOP temporario."""
    obj = hou.node("/obj").createNode("geo", "m2s_scan")
    try:
        f = obj.createNode("file")
        f.parm("file").set(str(geo_path).replace("\\", "/"))
        geo = f.geometry()
        info = _fbx.read_geo(geo)
        return sorted(info["assets"])
    finally:
        obj.destroy()
