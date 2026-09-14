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
        self.matlibs = []          # [(materiallibrary, [(nome, mapas, plant)])]
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


def _tipo_sop(nome_tipo):
    """O node type, ou None -- p/ HDAs que podem faltar noutra maquina."""
    return hou.sopNodeTypeCategory().nodeType(nome_tipo)


def _branches_planta(sop, tail, nome_prim, quer_proxy, quer_sim):
    """Proxy/simproxy p/ plantas -- COPIA do setup do Matheus.

    Medido do hip dele ('asst builder.hiplc', Zea, 2026-09-12), no e parm:
      proxy   : delete_small_parts (Labs, 2.39% da maior peca) ->
                lowres_geo (HDA dele, 2%) -> asset_name na prim ->
                Color 'Random from Attribute' -> Cd promovido a DETAIL
                (inclass=1 prim, outclass=0 detail -- medido): UMA cor
                aleatoria por asset, p/ enxergar o set no GL
      simproxy: lowres_geo -> assemble -> convexdecomposition
      cada output (default incluso) fecha com Add 'Remove Unused Points'
    """
    add1 = sop.createNode("add", "add1")
    add1.parm("remove").set(1)             # Remove Unused Points (medido)
    add1.setInput(0, tail)
    sop.node("default").setInput(0, add1)

    base = tail
    if _tipo_sop("labs::delete_small_parts::1.0") is not None:
        dsp = sop.createNode("labs::delete_small_parts::1.0",
                             "delete_small_parts1")
        dsp.setInput(0, base)
        dsp.parm("mode").set(0)
        dsp.parm("threshold").set(2.39)
        base = dsp

    if _tipo_sop("lowres_geo::1.1.1") is not None:
        low = sop.createNode("lowres_geo::1.1.1", "lowres_geo1")
    else:
        # sem o HDA do Matheus (outra maquina): polyreduce chega perto
        low = sop.createNode("polyreduce::2.0", "lowres_geo1")
    low.parm("percentage").set(2.0)
    low.setInput(0, base)

    if quer_proxy:
        wr = sop.createNode("attribwrangle", "set_color_data")
        wr.setInput(0, low)
        wr.parm("class").set(1)
        wr.parm("snippet").set('s@asset_name = chs("asset_name");')
        ptg = wr.parmTemplateGroup()
        ptg.append(hou.StringParmTemplate("asset_name", "Asset Name", 1))
        wr.setParmTemplateGroup(ptg)
        wr.parm("asset_name").set("/" + nome_prim)

        cor = sop.createNode("color", "color1")
        cor.setInput(0, wr)
        cor.parm("class").set(1)           # Primitive
        cor.parm("colortype").set(4)       # Random from Attribute
        cor.parm("seed").set(0.97)
        cor.parm("rampattribute").set("asset_name")

        # o hash do Color distribui bem entre nomes parecidos (medido:
        # 01_04/01_05/Building todos diferentes; VEX random_shash COLIDE),
        # mas devolve RGB arbitrario e metade sai escuro/lamacento
        # (Building deu quase preto -- o "nao funciona" do Matheus).
        # Normaliza em HSV: matiz fica, saturacao/brilho ganham piso alto.
        nc = sop.createNode("attribwrangle", "nice_color")
        nc.setInput(0, cor)
        nc.parm("class").set(1)
        nc.parm("snippet").set(
            "vector hsv = rgbtohsv(v@Cd);\n"
            "v@Cd = hsvtorgb(set(hsv.x, fit(hsv.y, 0, 1, 0.55, 0.95),\n"
            "                    fit(hsv.z, 0, 1, 0.60, 0.95)));")

        promo = sop.createNode("attribpromote", "attribpromote1")
        promo.setInput(0, nc)
        promo.parm("inname").set("Cd")
        promo.parm("inclass").set(1)
        promo.parm("outclass").set(0)

        adel = sop.createNode("attribdelete", "attribdelete1")
        adel.setInput(0, promo)
        adel.parm("primdel").set("asset_name")

        add2 = sop.createNode("add", "add2")
        add2.parm("remove").set(1)
        add2.setInput(0, adel)
        sop.node("proxy").setInput(0, add2)

    if quer_sim:
        asm = sop.createNode("assemble", "assemble1")
        asm.setInput(0, low)
        cvx = sop.createNode("convexdecomposition", "convexdecomposition1")
        cvx.setInput(0, asm)
        adel2 = sop.createNode("attribdelete", "attribdelete2")
        adel2.setInput(0, cvx)
        adel2.parm("primdel").set("class")  # convexdecomposition escreve
        add3 = sop.createNode("add", "add3")
        add3.parm("remove").set(1)
        add3.setInput(0, adel2)
        sop.node("simproxy").setInput(0, add3)


def build_asset(asset, profile, out_dir=None, asset_name=None,
                renderers=("karma", "arnold", "renderman", "vray"), parent=None,
                lod=None, write=True, disp_scale=0.01,
                geo_path=None, parts=None, variants=None,
                tex_dir=None, cleanup=False, settings=None, thumb=False,
                two_sided=False,
                thumb_cfg=None):
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

    thumb_cfg: config do thumbnail do componentoutput (a secao Thumbnail
    do proprio no): {"mode": 1 GL / 2 Render, "res": 512, "spin": 0,
    "pitch": 0, "dist": 0}. Liga o autothumbnail (Re-Generate on Export)
    -- na UI o GL gera na hora do export, sem render externo.
    """
    res = Result()
    nome = asset_name or asset.name
    res.asset_name = nome
    partes_asset = parts if parts is not None else asset.parts

    if two_sided:
        # opt-in do Matheus: so funde <Nome>_Back quando o box esta ligado
        partes_asset = _funde_verso(partes_asset)
        if variants:
            variants = [(v, _funde_verso(p)) for v, p in variants]
    if tex_dir:
        partes_asset = _share_textures(partes_asset, tex_dir, res)
        if variants:
            variants = [(v, _share_textures(p, tex_dir, res))
                        for v, p in variants]

    # -- geometria: resolvida ANTES do subnet (o nome dele vem do fbx e
    # asset sem geometria nao deixa subnet vazio para tras) --------------
    if geo_path is None:
        lods = profile.lods_for(asset)
        lod = lod or (lods[0] if lods else None)
        geo_path = asset.geometry.get(lod) if lod else asset.default_geo
    if not geo_path:
        res.warn("asset sem geometria; nada a montar")
        return res

    stage = parent or hou.node("/stage")
    # o subnet leva o NOME DO FBX importado (pedido do Matheus); no
    # KitBash o arquivo e' um so' ("1.fbx") com varios assets, entao la'
    # vale o nome do OBJETO. Dedup explicito com _N: o auto-rename do
    # Houdini INCREMENTA o digito final e um rebuild do Zea_01_04
    # viraria "Zea_01_05" -- nome de OUTRO asset real (medido).
    if asset_name is not None:
        base_nome = _fbx.material_key(asset_name)
    else:
        base_nome = _fbx.material_key(
            os.path.splitext(os.path.basename(str(geo_path)))[0])
    alvo, i = base_nome, 0
    while stage.node(alvo) is not None:
        i += 1
        alvo = "%s_%d" % (base_nome, i)
    net = stage.createNode("subnet", alvo)
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
    # center_to_origin e convert_units ficam SEMPRE na rede ("todos devem
    # ter, ate porque a escala vem diferente" -- Matheus): o perfil so'
    # define os VALORES; neutros (justify None / scale 1) quando o perfil
    # nao pede, prontos para ajustar a mao.
    # Ordem: centralizar primeiro, escala depois (escala na origem
    # preserva centro e chao).
    ms = sop.createNode("matchsize", "center_to_origin")
    ms.setInput(0, tail)
    if getattr(profile, "center", False):
        # peca de catalogo senta na origem: centra XZ, apoia no chao (min
        # Y). doscale=0 -- centralizar nunca pode reescalar o asset.
        ms.parm("justify_x").set(2)   # center   (menu medido)
        ms.parm("justify_y").set(1)   # min = chao
        ms.parm("justify_z").set(2)
    else:
        for eixo in ("justify_x", "justify_y", "justify_z"):
            ms.parm(eixo).set(0)      # None = neutro
    tail = ms

    escala = float(getattr(profile, "unit_scale", 1.0) or 1.0)
    xf = sop.createNode("xform", "convert_units")
    xf.setInput(0, tail)
    xf.parm("scale").set(escala)      # 1.0 = neutro
    tail = xf

    sop.node("default").setInput(0, tail)

    quer_proxy = getattr(profile, "proxy", False)
    quer_sim = getattr(profile, "simproxy", False)
    if getattr(profile, "proxy_style", "reduce") == "plant" \
            and (quer_proxy or quer_sim):
        # setup do Matheus p/ plantas (copiado do hip dele; ver funcao)
        _branches_planta(sop, tail, _naming.usd_prim_name(nome),
                         quer_proxy, quer_sim)
    else:
        if quer_proxy:
            # proxy leve p/ GL. O template usa VDB->remesh->polyreduce; aqui
            # e' polyreduce direto (medido) -- pra hard-surface o resultado
            # serve e evita dois nos com parms nao medidos.
            pr = sop.createNode("polyreduce::2.0", "proxy_reduce")
            pr.setInput(0, tail)
            pr.parm("percentage").set(6.0)
            sop.node("proxy").setInput(0, pr)

        if quer_sim:
            # convex hull p/ os LOPs de fisica (Edit/Drop). O template faz
            # por peca via foreach; v1 e' um hull do objeto inteiro --
            # suficiente pra prop de kitbash.
            sw = sop.createNode("shrinkwrap::2.0", "simproxy_hull")
            sw.setInput(0, tail)
            sop.node("simproxy").setInput(0, sw)
    # nos criados por codigo nascem empilhados; arruma como na GUI
    sop.layoutChildren()
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
        _config_thumb(co, thumb_cfg)
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

    # TODAS as partes das texturas viram material ("se pegar por albedo da
    # pra ver que tem 12, assim como o Max" -- Matheus). O BIND fica so'
    # nas que tem subset na malha; as demais moram em /ASSET/mtl prontas
    # (outras variacoes da mesma planta usam).
    subsets_usd = {_naming.usd_prim_name(s) for s in subsets}
    itens = []
    for parte in partes_asset:
        mapas = partes_asset.get(parte)
        nome_p = _naming.usd_prim_name(parte)
        node, avisos = _mats.build_material(
            ml, nome_p, mapas, renderers=renderers,
            plant=plant, disp_scale=disp_scale, settings=settings)
        res.avisos.extend(avisos)
        if single or nome_p in subsets_usd:
            res.parts_bound.append(nome_p)
        itens.append((nome_p, mapas, plant))
        finais.append(node)
    for s in subsets:
        if _naming.usd_prim_name(s) not in {_naming.usd_prim_name(p)
                                            for p in partes_asset} \
                and not single:
            res.parts_missing.append(s)
            res.warn("subset '%s' sem jogo de texturas -- sem material "
                     "(vira cinza no render)" % s)
    res.matlibs.append((ml, itens))
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
    # o componentmaterial SEMPRE autora o bind dentro de uma variante
    # (medido: variantname VAZIO perde o bind -- render cinza, o bug que o
    # Matheus pegou). Sem toggle para desligar, o nome vira 'default'
    # em vez do nome do no ('assign').
    cm.parm("variantname").set("default")
    # padroes em _bind_parts (unico lugar): cobrem malha plana E aninhada
    # em /geo/render quando ha branches de proxy/simproxy
    _bind_parts(cm, res.parts_bound, single)
    res.nodes["componentmaterial"] = cm

    # -- saida ------------------------------------------------------------
    prim = _naming.usd_prim_name(nome)
    co = net.createNode("componentoutput", prim)
    co.setColor(hou.Color(0.0, 1.0, 0.0))   # cor do HDA p/ output
    _config_thumb(co, thumb_cfg)
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


def _config_thumb(co, cfg):
    """Aplica a secao Thumbnail do componentoutput (parms medidos:
    thumbnailmode, autothumbnail, res1/res2, spin/pitch/dist)."""
    if not cfg:
        return
    co.parm("thumbnailmode").set(int(cfg.get("mode", 1)))   # 1 = Houdini GL
    co.parm("autothumbnail").set(1)      # Re-Generate Thumbnail on Export
    r = int(cfg.get("res", 512))
    co.parm("res1").set(r)
    co.parm("res2").set(r)
    for parm in ("spin", "pitch", "dist"):
        if cfg.get(parm) is not None:
            co.parm(parm).set(float(cfg[parm]))


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


def _funde_verso(partes):
    """Com o box Two-Sided ligado, garante papeis back_* nas partes.

    Duas fontes, na ordem do video das folhas do Jonas Noell:
    1. o pacote TRAZ textura de verso ('<Parte>_Back' vira back_* dentro
       de '<Parte>');
    2. parte de folha SEM verso proprio usa a MESMA textura dos dois
       lados (back_basecolor = basecolor) -- e' o que o Jonas faz no
       video, e sem isso marcar o box num Maxtree (que nao tem _Back
       nenhum) nao criava nada (reportado pelo Matheus, 2026-09-12).
    Os builders ligam o two-sided de cada renderer quando veem
    back_basecolor.
    """
    out, versos = {}, {}
    for p, m in partes.items():
        if p.lower().endswith("_back"):
            versos[p[:-5]] = m
        else:
            out[p] = dict(m)
    for base, m in versos.items():
        alvo = None
        for k in out:
            if k.lower() == base.lower():
                alvo = out[k]
                break
        if alvo is None:
            out[base + "_Back"] = m     # verso sem frente: fica como era
        else:
            for papel, arq in m.items():
                alvo["back_" + papel] = arq
    for nome, m in out.items():
        # mesmo criterio de folha do caminho V-Ray (folha por nome, ou
        # organico fino com mapa de translucency); tronco/props ficam
        # de um lado so' -- two-sided neles so' pesaria o shader
        if "back_basecolor" not in m and "basecolor" in m \
                and (_mats.eh_folha(nome) or "translucency" in m):
            m["back_basecolor"] = m["basecolor"]
    return out


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


def medir_usd(usd_path):
    """Tamanho do asset exportado, em METROS. None se nao der para ler.

    Sai do extent que o proprio USD ja' gravou (nao cozinha nada), entao
    custa quase zero e serve de conferencia de escala depois do export:
    um carro que sai com 0.05 m denuncia um convert_units errado.
    """
    try:
        from pxr import Usd, UsdGeom
        st = Usd.Stage.Open(str(usd_path))
        if st is None:
            return None
        mpu = UsdGeom.GetStageMetersPerUnit(st) or 1.0
        prim = st.GetDefaultPrim() or st.GetPseudoRoot()
        cache = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(),
            [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
        faixa = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        if faixa.IsEmpty():
            return None
        t = faixa.GetSize()
        return (t[0] * mpu, t[1] * mpu, t[2] * mpu)
    except Exception:
        return None


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
    subsets_usd = {_naming.usd_prim_name(s) for s in subsets}

    finais, ligadas, itens = [], [], []
    for parte in partes_dict:            # TODAS as partes viram material
        mapas = partes_dict[parte]
        nome_p = _naming.usd_prim_name(parte)
        node, avisos = _mats.build_material(
            ml, nome_p, mapas, renderers=renderers,
            plant=plant, disp_scale=disp_scale, settings=settings)
        res.avisos.extend(avisos)
        finais.append(node)
        itens.append((nome_p, mapas, plant))
        if single or nome_p in subsets_usd:
            ligadas.append(nome_p)       # bind so' com subset na malha
    res.matlibs.append((ml, itens))
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
        # dois padroes (lista separada por espaco): sem branches a malha
        # fica em /geo/<mesh>/<subset>; com proxy/simproxy o
        # componentgeometry aninha em /geo/render/<mesh>/<subset> --
        # MEDIDO no A/B (Zea): so' com /geo/*/ o USD saia com ZERO binds
        # ("nao mostra o shader no render"); `**` no meio nao casa.
        padrao = ("/ASSET/geo" if single
                  else "/ASSET/geo/*/{p} /ASSET/geo/render/*/{p}".format(
                      p=parte))
        cm.parm("primpattern%d" % i).set(padrao)
        cm.parm("matspecpath%d" % i).set("/ASSET/mtl/%s" % parte)


def rebuild_materials(res, renderers, disp_scale=0.01, settings=None):
    """Reconstroi SO' os materiais de um build (o UPDATE MATERIALS).

    A geometria, os binds e o componentoutput ficam como estao; cada
    materiallibrary e' esvaziada e remontada com os mesmos mapas e os
    settings NOVOS. Devolve quantos materiais saíram.
    """
    total = 0
    for ml, itens in res.matlibs:
        try:
            ml.path()
        except hou.ObjectWasDeleted:
            res.warn("materiallibrary sumiu; pulei (rode o BUILD de novo)")
            continue
        for c in list(ml.children()):
            c.destroy()
        finais = []
        for nome, mapas, plant in itens:
            node, avisos = _mats.build_material(
                ml, nome, mapas, renderers=renderers, plant=plant,
                disp_scale=disp_scale, settings=settings)
            res.avisos.extend(avisos)
            finais.append(node)
        ml.layoutChildren()
        ml.setColor(hou.Color(0.5, 1.0, 0.5) if finais else hou.Color(1, 0, 0))
        ml.parm("materials").set(len(finais))
        for i, node in enumerate(finais, start=1):
            ml.parm("matnode%d" % i).set(node.name())
            ml.parm("matpath%d" % i).set(node.name())
            if ml.parm("assign%d" % i) is not None:
                ml.parm("assign%d" % i).set(0)
        total += len(finais)
    return total
