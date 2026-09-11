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
        self.variant_set = None    # "mtl" quando o build saiu com variantes
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
                renderers=("karma", "arnold", "renderman", "vray"), parent=None,
                lod=None, write=True, disp_scale=0.01,
                geo_path=None, parts=None, variants=None,
                tex_dir=None, cleanup=False, settings=None, thumb=False):
    """Monta um componente para `asset` e (opcionalmente) escreve o USD.

    asset_name: para pacotes `asset_grain == "object"` (KitBash), o nome do
    objeto a extrair do arquivo; None em pacotes pasta-e-asset.

    geo_path / parts: overrides para sets multi-FBX com atlas compartilhado
    (Post Apocalypse): o lote passa cada .fbx e o material montado do atlas,
    em vez do que o scan da pasta deduziu.

    variants: [(nome, parts_dict), ...] -- esquema do KB3D_Converter_2.0:
    cada entrada vira um componentmaterial encadeado com variantname, e o
    USD sai com VARIANTES de material (dark/light no mesmo asset), em vez
    de um build por variante.

    tex_dir: modo de TEXTURA COMPARTILHADA. Copia cada mapa UMA vez para
    esta pasta e desliga o `localize` do componentoutput. Sem isso um set
    de atlas unico (Post Apocalypse) copia o atlas por asset -- 119 MB x
    819 pastas = 100 GB, medido. Os materiais apontam para a copia unica.

    cleanup: destroi a rede depois de escrever o USD (lote: 800+ redes
    acumuladas numa sessao terminaram em segfault, medido).

    settings: dict com os ajustes do Asset_USD_Builder (basecolor_gamma,
    normal_scale, subsurface, remap_disp) -- ver materials.DEFAULTS.
    """
    res = Result()
    nome = asset_name or asset.name
    res.asset_name = nome
    partes_asset = parts if parts is not None else asset.parts

    if tex_dir:
        partes_asset = _share_textures(partes_asset, tex_dir, res)
        if variants:
            variants = [(v, _share_textures(p, tex_dir, res))
                        for v, p in variants]

    stage = parent or hou.node("/stage")
    net = stage.createNode("subnet",
                           "USD_Builder_Asset_" + _fbx.material_key(nome))
    net.moveToGoodPosition()
    # padrao de cores do Asset_USD_Builder (lido do PythonModule dele):
    # planta verde-oliva, objeto azul, variante laranja; geo amarelo-palha,
    # matlib verde-claro (vermelho sem textura), output verde.
    if profile.plant_workflow and asset.plant:
        net.setColor(hou.Color(0.5, 0.7, 0.3))      # NodeColorPlant
    elif variants:
        net.setColor(hou.Color(1.0, 0.6, 0.0))      # NodeColorObjVar
    else:
        net.setColor(hou.Color(0.29, 0.56, 0.89))   # NodeColorObj

    # -- geometria -------------------------------------------------------
    if geo_path is None:
        lods = profile.lods_for(asset)
        lod = lod or (lods[0] if lods else None)
        geo_path = asset.geometry.get(lod) if lod else asset.default_geo
    if not geo_path:
        res.warn("asset sem geometria; nada a montar")
        return res

    cg = net.createNode("componentgeometry", "geo")
    cg.setColor(hou.Color(1.0, 1.0, 0.5))           # cor do HDA p/ geo
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

        # nome hierarquico ('X_grp/X_Main') vira nome de peca limpo
        wr = sop.createNode("attribwrangle", "clean_piece_names")
        wr.setInput(0, tail)
        wr.parm("class").set(1)
        wr.parm("snippet").set(
            'string p[] = split(s@name, "/"); s@name = p[len(p)-1];')
        tail = wr

    # ---- padrao Rebelway do component builder -------------------------
    # (RBL_Component_Builder_Template: default + proxy + simproxy)
    # Ordem a pedido do Matheus: centralizar PRIMEIRO, converter a escala
    # depois. (Geometricamente da' no mesmo -- escala na origem preserva
    # centro e chao -- mas a rede fica na ordem que se le.)
    if getattr(profile, "center", False):
        # peca de catalogo senta na origem: centra XZ, apoia no chao (min Y).
        # doscale fica 0 -- centralizar nunca pode reescalar o asset.
        ms = sop.createNode("matchsize", "center_to_origin")
        ms.setInput(0, tail)
        ms.parm("justify_x").set(2)   # center   (menu medido)
        ms.parm("justify_y").set(1)   # min = chao
        ms.parm("justify_z").set(2)
        tail = ms

    escala = float(getattr(profile, "unit_scale", 1.0) or 1.0)
    if escala != 1.0:
        # o "convert the units" do video: fonte em cm -> USD em metros
        xf = sop.createNode("xform", "convert_units")
        xf.setInput(0, tail)
        xf.parm("scale").set(escala)
        tail = xf

    sop.node("default").setInput(0, tail)

    if getattr(profile, "proxy", False):
        # proxy leve p/ GL. O template usa VDB->remesh->polyreduce; aqui e'
        # polyreduce direto (medido) -- pra hard-surface o resultado serve e
        # evita dois nos com parms nao medidos. Trocar por VDB se faltar.
        pr = sop.createNode("polyreduce::2.0", "proxy_reduce")
        pr.setInput(0, tail)
        pr.parm("percentage").set(6.0)
        sop.node("proxy").setInput(0, pr)

    if getattr(profile, "simproxy", False):
        # convex hull p/ os LOPs de fisica (Edit/Drop). O template faz por
        # peca via foreach; v1 e' um hull do objeto inteiro -- suficiente
        # pra prop de kitbash, e sem block begin/end programatico.
        sw = sop.createNode("shrinkwrap::2.0", "simproxy_hull")
        sw.setInput(0, tail)
        sop.node("simproxy").setInput(0, sw)
    cg.parm("partitionattribs").set("shop_materialpath")
    cg.parm("prefixpartitionsubsets").set(0)
    res.nodes["componentgeometry"] = cg

    # -- que subsets existem de fato? ------------------------------------
    # Cozinhamos o stage e lemos, em vez de confiar que toda parte das
    # texturas aparece na malha (no Maxtree metade dos IDs nao aparece).
    subsets = _subset_names(cg, res)

    # -- variantes de material (esquema KB3D_Converter_2.0) ---------------
    if variants:
        res.variant_set = "mtl"    # p/ a Asset Gallery abrir um tile por variante
        tail_lop = cg
        for var_nome, var_parts in variants:
            ml_v, ligadas = _matlib(net, var_nome, var_parts, subsets,
                                    profile, asset, renderers, disp_scale,
                                    res, settings=settings)
            cm_v = net.createNode("componentmaterial", "assign_" + var_nome)
            cm_v.setInput(0, tail_lop)
            cm_v.setInput(1, ml_v)
            cm_v.parm("variantname").set(var_nome)
            _bind_parts(cm_v, ligadas, single=len(var_parts) == 1)
            res.parts_bound.extend("%s:%s" % (var_nome, p) for p in ligadas)
            tail_lop = cm_v
        cm = tail_lop
        res.nodes["componentmaterial"] = cm
        prim = _naming.usd_prim_name(nome)
        co = net.createNode("componentoutput", prim)
        co.setColor(hou.Color(0.0, 1.0, 0.0))   # cor do HDA p/ output
        co.setInput(0, cm)
        co.parm("rootprim").set("/" + prim)
        if tex_dir:
            co.parm("localize").set(0)
        if out_dir:
            usd = "%s/%s/%s.usd" % (str(out_dir).replace(chr(92), "/").rstrip("/"),
                                    nome, nome)
            co.parm("lopoutput").set(usd)
            res.usd_path = usd
        res.nodes["componentoutput"] = co
        _liga_output0(net, co)
        net.layoutChildren()
        if write and out_dir:
            try:
                co.parm("execute").pressButton()
            except Exception as e:
                res.warn("execute do componentoutput falhou: %s" % e)
            if res.usd_path and not os.path.isfile(res.usd_path):
                res.warn("componentoutput rodou mas o USD nao existe")
            elif thumb:
                from .. import gallery as _gallery
                if _gallery.thumbnail(res.usd_path) is None:
                    res.warn("thumbnail nao foi gerado")
            if cleanup:
                res.nodes = {}
                net.destroy()
        return res

    # -- materiais --------------------------------------------------------
    ml = net.createNode("materiallibrary", "mtl")
    ml.parm("matpathprefix").set("/ASSET/mtl/")

    plant = profile.plant_workflow and asset.plant
    finais = []

    # Asset de material UNICO (Megascans): a malha costuma vir com
    # shop_materialpath generico ('default_material'), entao casar por nome
    # nao faz sentido -- o unico material vai no /ASSET/geo inteiro.
    single = (len(partes_asset) == 1)
    alvo_partes = list(partes_asset) if single else subsets

    for parte in alvo_partes:
        mapas = partes_asset.get(parte)
        if not mapas:
            res.parts_missing.append(parte)
            res.warn("subset '%s' sem jogo de texturas -- sem material "
                     "(vira cinza no render)" % parte)
            continue
        node, avisos = _mats.build_material(
            ml, _naming.usd_prim_name(parte), mapas, renderers=renderers,
            plant=plant, disp_scale=disp_scale, settings=settings)
        res.avisos.extend(avisos)
        res.parts_bound.append(_naming.usd_prim_name(parte))
        finais.append(node)
    ml.layoutChildren()
    # cor do HDA: verde-claro com material, vermelho sem textura nenhuma
    ml.setColor(hou.Color(0.5, 1.0, 0.5) if finais else hou.Color(1, 0, 0))
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
    co.setColor(hou.Color(0.0, 1.0, 0.0))   # cor do HDA p/ output
    co.setInput(0, cm)
    co.parm("rootprim").set("/" + prim)
    if tex_dir:
        co.parm("localize").set(0)
    if out_dir:
        usd = "%s/%s/%s.usd" % (str(out_dir).replace("\\", "/").rstrip("/"),
                                nome, nome)
        co.parm("lopoutput").set(usd)
        res.usd_path = usd
    res.nodes["componentoutput"] = co
    _liga_output0(net, co)
    net.layoutChildren()

    if write and out_dir:
        try:
            co.parm("execute").pressButton()
        except Exception as e:
            res.warn("execute do componentoutput falhou: %s" % e)
        if res.usd_path and not os.path.isfile(res.usd_path):
            res.warn("componentoutput rodou mas o USD nao existe")
        elif thumb:
            from .. import gallery as _gallery
            if _gallery.thumbnail(res.usd_path) is None:
                res.warn("thumbnail nao foi gerado")
        if cleanup:
            res.nodes = {}
            net.destroy()

    return res


def _liga_output0(net, co):
    """Religa o output0 QUE O SUBNET JA TEM no componentoutput.

    Criar um output novo dava um segundo no ('output1') e deixava o
    output0 default pendurado no Input Stage -- apontado pelo Matheus.
    Religar o existente tambem desliga o fio do input.
    """
    outp = net.node("output0")
    if outp is None:
        outp = net.createNode("output", "output0")
    outp.setInput(0, co)


def _share_textures(parts_dict, tex_dir, res):
    """Copia cada mapa UMA vez para `tex_dir` e devolve o dict apontando la'.

    E' o contorno dos 100 GB: com atlas compartilhado, o localize do
    componentoutput copiava o mesmo atlas para dentro de CADA asset.
    """
    import shutil
    tex_dir = str(tex_dir).replace("\\", "/").rstrip("/")
    if not os.path.isdir(tex_dir):
        os.makedirs(tex_dir)
    novo = {}
    for parte, mapas in parts_dict.items():
        m2 = {}
        for papel, caminho in mapas.items():
            alvo = tex_dir + "/" + os.path.basename(str(caminho))
            if not os.path.isfile(alvo):
                try:
                    # temp + replace: com --jobs, dois workers podem copiar
                    # o mesmo mapa ao mesmo tempo; replace e' atomico
                    tmp = "%s.tmp%d" % (alvo, os.getpid())
                    shutil.copy2(str(caminho), tmp)
                    try:
                        os.replace(tmp, alvo)
                    except OSError:
                        os.remove(tmp)
                except Exception as e:
                    res.warn("copia de textura falhou (%s); usando a origem"
                             % e)
                    m2[papel] = caminho
                    continue
            m2[papel] = alvo
        novo[parte] = m2
    return novo


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
    obj = hou.node("/obj").createNode("geo", "usdba_scan")
    try:
        f = obj.createNode("file")
        f.parm("file").set(str(geo_path).replace("\\", "/"))
        geo = f.geometry()
        info = _fbx.read_geo(geo)
        return sorted(info["assets"])
    finally:
        obj.destroy()


def cache_bgeo(geo_path, cache_dir):
    """Converte um arquivo de geometria para .bgeo.sc uma unica vez.

    O passo GenerateBGEO do video do Arcanacom: um FBX de props com dezenas
    de objetos seria recarregado uma vez POR PROP no lote; o cache derruba
    isso para uma leitura. Reusa o cache se ja existir.
    """
    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir)
    base = os.path.splitext(os.path.basename(str(geo_path)))[0]
    alvo = os.path.join(cache_dir, base + ".bgeo.sc").replace(chr(92), "/")
    if os.path.isfile(alvo):
        return alvo
    obj = hou.node("/obj").createNode("geo", "usdba_cache")
    try:
        f = obj.createNode("file")
        f.parm("file").set(str(geo_path).replace(chr(92), "/"))
        rop = obj.createNode("rop_geometry")
        rop.setInput(0, f)
        rop.parm("sopoutput").set(alvo)
        rop.parm("execute").pressButton()
    finally:
        obj.destroy()
    if not os.path.isfile(alvo):
        raise RuntimeError("bgeo nao foi escrito: %s" % alvo)
    return alvo


def _matlib(net, sufixo, partes_dict, subsets, profile, asset, renderers,
            disp_scale, res, settings=None):
    """materiallibrary com lista explicita para um conjunto de partes.

    Devolve (node, [partes que ganharam material]).
    """
    ml = net.createNode("materiallibrary", "mtl_" + _fbx.material_key(sufixo))
    ml.parm("matpathprefix").set("/ASSET/mtl/")
    plant = profile.plant_workflow and asset.plant
    single = (len(partes_dict) == 1)
    alvo = list(partes_dict) if single else subsets

    finais, ligadas = [], []
    for parte in alvo:
        mapas = partes_dict.get(parte)
        if not mapas:
            res.warn("variante '%s': subset '%s' sem texturas" % (sufixo, parte))
            continue
        node, avisos = _mats.build_material(
            ml, _naming.usd_prim_name(parte), mapas, renderers=renderers,
            plant=plant, disp_scale=disp_scale, settings=settings)
        res.avisos.extend(avisos)
        finais.append(node)
        ligadas.append(_naming.usd_prim_name(parte))
    ml.layoutChildren()
    ml.setColor(hou.Color(0.5, 1.0, 0.5) if finais else hou.Color(1, 0, 0))
    ml.parm("materials").set(len(finais))
    for i, node in enumerate(finais, start=1):
        ml.parm("matnode%d" % i).set(node.name())
        ml.parm("matpath%d" % i).set(node.name())
        if ml.parm("assign%d" % i) is not None:
            ml.parm("assign%d" % i).set(0)
    return ml, ligadas


def _bind_parts(cm, ligadas, single):
    cm.parm("nummaterials").set(len(ligadas))
    for i, parte in enumerate(ligadas, start=1):
        padrao = "/ASSET/geo" if single else "/ASSET/geo/*/%s" % parte
        cm.parm("primpattern%d" % i).set(padrao)
        cm.parm("matspecpath%d" % i).set("/ASSET/mtl/%s" % parte)
