"""Construtores de material por renderer, para dentro de um materiallibrary.

Base: os conversores da Rebelway (KB3D_converter / texture_from_disk) --
Karma (MaterialX) e Arnold no MESMO material via um no `collect`.

ESTRUTURA E NOMES (pedido do Matheus: nomes basicos)
    <parte>                collect (so' quando ha' mais de um renderer)
    karma_<parte>          subnet MaterialX, rendercontext 'mtlx'
        surface            mtlxstandard_surface
        basecolor, roughness, glossiness, metalness, normal, height,
        opacity, emission, translucency, refraction   (mtlximage por papel)
        invert, normal_map, displacement
    arnold_<parte>         arnold_materialbuilder
        (mesmos nomes basicos por papel, image/normal_map/range/multiply)

    O contexto 'mtlx' no subnet foi MEDIDO: publica outputs:mtlx:surface +
    outputs:surface (preview) -- identico ao caminho que ja bindou e
    escreveu USD. 'kma' publicaria outputs:kma:surface, que so' o Karma le.

DESVIOS CONSCIENTES DA RECEITA REBELWAY
  * Mapa de dado (roughness/metalness/...) em Raw no Arnold, nao ACEScg.
  * Glossiness inverte (mtlxinvert / arnold::range 1->0).
  * Planta: thin_walled + subsurface com o mapa de translucency como
    subsurface_color -- a regra do Matheus, nos dois renderers.
"""
import hou

_DIRETO = {
    "basecolor": "base_color",
    "metalness": "metalness",
    "roughness": "specular_roughness",
    "opacity": "opacity",
    "refraction": "transmission",
    "emission": "emission_color",
}
_COR = {"basecolor", "emission", "translucency"}

# Os ajustes do Asset_USD_Builder (aba IMG SETTINGS), com os defaults DELE
# onde nao conflitam com o que ja medimos. remap_disp e' o "Remap
# Displacement" (in_low, in_high, out_low, out_high): altura 0..1 vira
# -0.5..0.5, centrada no zero -- None desliga.
DEFAULTS = {
    "basecolor_gamma": 1.0,
    "normal_scale": 1.0,
    "subsurface": 0.25,     # Jonas Noell E o HDA usam 0.25 ("nunca perto de 1")
    "remap_disp": None,     # ex.: (0.0, 1.0, -0.5, 0.5)
    "tex_renderman": False,  # etapa .tex ACEScg do HDA (texconv.py)
}


def _cfg(settings):
    s = dict(DEFAULTS)
    s.update(settings or {})
    return s


# tipo da parte pelo NOME -- decide cor do no e o fallback de folha
_TOKENS_FOLHA = ("leaf", "leaves", "folha")
_TOKENS_TRONCO = ("trunk", "tronco", "bark", "branch")


def eh_folha(nome):
    low = nome.lower()
    return any(t in low for t in _TOKENS_FOLHA)


def cor_da_parte(nome):
    """Verde p/ folha, marrom p/ tronco, None p/ o resto (Matheus)."""
    low = nome.lower()
    if any(t in low for t in _TOKENS_FOLHA):
        return hou.Color(0.5, 0.7, 0.3)
    if any(t in low for t in _TOKENS_TRONCO):
        return hou.Color(0.45, 0.3, 0.15)
    return None


class _W(object):
    """Coletor de avisos + set/connect tolerantes."""

    def __init__(self):
        self.avisos = []

    def warn(self, msg):
        self.avisos.append(msg)

    def set(self, node, parm, valor):
        if node is None:
            return False
        p = node.parm(parm) or node.parmTuple(parm)
        if p is None:
            self.warn("parm inexistente: %s.%s" % (node.name(), parm))
            return False
        try:
            p.set(valor)
            return True
        except Exception as e:
            self.warn("set %s.%s=%r: %s" % (node.name(), parm, valor, e))
            return False

    def connect(self, dst, inp, src, out):
        try:
            dst.setNamedInput(inp, src, out)
            return True
        except Exception as e:
            self.warn("connect %s.%s <- %s.%s: %s"
                      % (dst.name(), inp, src.name(), out, e))
            return False


def _karma_subnet(parent, nome):
    """Builder OFICIAL do Karma (voptoolutils, o mesmo da shelf tool).

    A licao do V-Ray vale aqui: usar a forma que o proprio renderer
    monta. Sai o 'karmamaterial' do print do Matheus: contexto 'kma',
    outputs surface/displacement/properties (+ preview automatico), com
    mtlxstandard_surface, mtlxdisplacement e kma_material_properties ja
    dentro e ligados. (O subnet manual com ctx 'mtlx' tambem renderizava
    -- medido -- mas o oficial e' o padrao e traz o properties.)
    """
    # MEDIDO: o _setupMtlXBuilderSubnet custa ~0.47s por material (parm
    # templates); num asset de 12 materiais eram ~5.6s so' de Karma
    # ("por que ta demorando quando marca o karma?" -- Matheus). O tool
    # roda UMA vez num template e os demais sao COPIA (rapida).
    import voptoolutils
    tpl = parent.node("karma_TEMPLATE")
    if tpl is None:
        tpl = parent.createNode("subnet", "karma_TEMPLATE")
        voptoolutils._setupMtlXBuilderSubnet(
            subnet_node=tpl, name="karma_TEMPLATE",
            mask=voptoolutils.KARMAMTLX_TAB_MASK,
            folder_label="Karma Material Builder", render_context="kma")
    sub = hou.copyNodesTo([tpl], parent)[0]
    sub.setName(nome, unique_name=True)
    return sub


def build_karma(parent, name, maps, plant=False, disp_scale=0.01, w=None,
                settings=None):
    """Subnet 'karma_<name>' completo. Devolve o subnet."""
    w = w or _W()
    s = _cfg(settings)
    sub = _karma_subnet(parent, "karma_" + name)
    # o builder oficial ja traz surface/displacement ligados no output
    surf = sub.node("mtlxstandard_surface")
    surf.setName("surface")            # nomes basicos, como o Matheus pediu

    def image(role, path, signature):
        img = sub.createNode("mtlximage", role)
        w.set(img, "signature", signature)
        w.set(img, "file", path)
        return img

    # cada mapa ganha um no de ajuste NEUTRO no caminho -- colorcorrect na
    # cor (com o BaseColor Gamma no basecolor), range no dado. E' o "se eu
    # quiser alterar valor" do Matheus: abre o subnet e mexe.
    base_cc = None
    for role, inp in _DIRETO.items():
        if role not in maps:
            continue
        img = image(role, maps[role], "color3" if role in _COR else "default")
        if role in _COR:
            cc = sub.createNode("mtlxcolorcorrect", role + "_cc")
            if role == "basecolor":
                w.set(cc, "gamma", s["basecolor_gamma"])
            w.connect(cc, "in", img, "out")
            img = cc
            if role == "basecolor":
                base_cc = cc
        else:
            rng = sub.createNode("mtlxrange", role + "_remap")
            w.set(rng, "signature", "float")
            w.connect(rng, "in", img, "out")
            img = rng
        w.connect(surf, inp, img, "out")
        if role == "emission":
            w.set(surf, "emission", 1)

    if "back_basecolor" in maps:
        # frente/verso do video das folhas: twosided chaveia a COR por
        # facing (front = basecolor, back = textura de verso)
        imgb = image("back_basecolor", maps["back_basecolor"], "color3")
        ccb = sub.createNode("mtlxcolorcorrect", "back_basecolor_cc")
        w.connect(ccb, "in", imgb, "out")
        ts = sub.createNode("twosided::2.0", "twosided")
        if base_cc is not None:
            w.connect(ts, "front", base_cc, "out")
        w.connect(ts, "back", ccb, "out")
        w.connect(surf, "base_color", ts, "color")

    if "glossiness" in maps and "roughness" not in maps:
        img = image("glossiness", maps["glossiness"], "default")
        inv = sub.createNode("mtlxinvert", "invert")
        w.set(inv, "signature", "float")
        w.connect(inv, "in", img, "out")
        w.connect(surf, "specular_roughness", inv, "out")

    if "normal" in maps:
        img = image("normal", maps["normal"], "vector3")
        nm = sub.createNode("mtlxnormalmap", "normal_map")
        if s["normal_scale"] != 1.0:
            w.set(nm, "scale", s["normal_scale"])
        w.connect(nm, "in", img, "out")
        w.connect(surf, "normal", nm, "out")

    disp = sub.node("mtlxdisplacement")   # ja vem ligado no output oficial
    if "displacement" in maps:
        img = image("height", maps["displacement"], "default")
        # o remap fica SEMPRE no caminho (neutro sem remap_disp) -- e' a
        # alavanca de ajuste manual da altura
        rm = sub.createNode("mtlxremap", "remap_height")
        w.set(rm, "signature", "float")
        if s["remap_disp"]:
            il, ih, ol, oh = s["remap_disp"]
            w.set(rm, "inlow", il)
            w.set(rm, "inhigh", ih)
            w.set(rm, "outlow", ol)
            w.set(rm, "outhigh", oh)
        w.connect(rm, "in", img, "out")
        if disp is not None:
            disp.setName("displacement")
            w.set(disp, "scale", disp_scale)
            w.connect(disp, "displacement", rm, "out")
    elif disp is not None:
        disp.destroy()                    # sem mapa, sem galho morto

    # setup de folha: com mapa de translucency, OU quando o NOME diz que e'
    # folha ("ele nao pegou as folhas" -- Maxtree nao entrega translucency
    # p/ toda folha; ai o SSS puxa do basecolor)
    if plant and ("translucency" in maps or eh_folha(name)):
        w.set(surf, "thin_walled", 1)
        w.set(surf, "subsurface", s["subsurface"])
        if "translucency" in maps:
            img = image("translucency", maps["translucency"], "color3")
            cc = sub.createNode("mtlxcolorcorrect", "translucency_cc")
            w.connect(cc, "in", img, "out")
            w.connect(surf, "subsurface_color", cc, "out")
        elif base_cc is not None:
            w.connect(surf, "subsurface_color", base_cc, "out")

    sub.layoutChildren()
    return sub


def arnold_available():
    # o teste honesto e' o TIPO DE NO existir (medido: no hython o htoa
    # registra os shaders mas o HDA arnold_materialbuilder nao carrega;
    # na GUI carrega). O check antigo por houdiniPath mentia nos dois
    # sentidos.
    return "arnold_materialbuilder" in hou.vopNodeTypeCategory().nodeTypes()


def build_arnold(parent, name, maps, plant=False, disp_scale=0.01, w=None,
                 settings=None):
    """arnold_materialbuilder 'arnold_<name>'. Devolve o builder (ou None)."""
    w = w or _W()
    s = _cfg(settings)
    try:
        ar = parent.createNode("arnold_materialbuilder", "arnold_" + name)
    except Exception as e:
        w.warn("arnold_materialbuilder indisponivel: %s" % e)
        return None

    out = ar.node("OUT_material")
    surf = ar.createNode("standard_surface", "surface")
    out.setInput(0, surf, 0)

    def image(role, path, cor, single=True):
        img = ar.createNode("image", role)
        w.set(img, "filename", path)
        w.set(img, "color_family", "Utility")
        w.set(img, "color_space", "sRGB - Texture" if cor else "Raw")
        if not cor and single:
            w.set(img, "single_channel", 1)
        return img

    for role, inp in _DIRETO.items():
        if role not in maps:
            continue
        cor = role in _COR
        img = image(role, maps[role], cor)
        if role == "basecolor" and s["basecolor_gamma"] != 1.0:
            cc = ar.createNode("arnold::color_correct", "basecolor_gamma")
            w.set(cc, "gamma", s["basecolor_gamma"])
            w.connect(cc, "input", img, "rgba")
            w.connect(surf, inp, cc, "rgba")
            continue
        w.connect(surf, inp, img, "rgba" if cor else "r")
        if role == "emission":
            w.set(surf, "emission", 1)

    if "glossiness" in maps and "roughness" not in maps:
        img = image("glossiness", maps["glossiness"], False)
        rng = ar.createNode("arnold::range", "invert")
        w.set(rng, "output_min", 1.0)
        w.set(rng, "output_max", 0.0)
        w.connect(rng, "input", img, "rgba")
        w.connect(surf, "specular_roughness", rng, "r")

    if "normal" in maps:
        img = image("normal", maps["normal"], False, single=False)
        nm = ar.createNode("normal_map", "normal_map")
        if s["normal_scale"] != 1.0:
            w.set(nm, "strength", s["normal_scale"])
        w.connect(nm, "input", img, "rgba")
        w.connect(surf, "normal", nm, "vector")

    if "displacement" in maps:
        img = image("height", maps["displacement"], False)
        src, out_name = img, "rgba"
        if s["remap_disp"]:
            il, ih, ol, oh = s["remap_disp"]
            rm = ar.createNode("arnold::range", "remap_height")
            w.set(rm, "input_min", il)
            w.set(rm, "input_max", ih)
            w.set(rm, "output_min", ol)
            w.set(rm, "output_max", oh)
            w.connect(rm, "input", img, "rgba")
            src, out_name = rm, "rgb"
        mult = ar.createNode("arnold::multiply", "displacement_amount")
        for c in ("input2r", "input2g", "input2b"):
            w.set(mult, c, disp_scale)
        w.connect(mult, "input1", src, out_name)
        w.connect(out, "displacement", mult, "rgb")

    if "back_basecolor" in maps:
        # frente/verso: dois standard_surface num arnold::two_sided
        # (in: front/back, out: shader -- medido no H22)
        surf_b = ar.createNode("standard_surface", "surface_back")
        imgb = image("back_basecolor", maps["back_basecolor"], True)
        w.connect(surf_b, "base_color", imgb, "rgba")
        ts = ar.createNode("arnold::two_sided", "two_sided")
        w.connect(ts, "front", surf, "surface")
        w.connect(ts, "back", surf_b, "surface")
        out.setInput(0, ts, 0)

    if plant and "translucency" in maps:
        img = image("translucency", maps["translucency"], True)
        w.set(surf, "thin_walled", 1)
        w.set(surf, "subsurface", s["subsurface"])
        w.connect(surf, "subsurface_color", img, "rgba")

    ar.layoutChildren()
    ar.setMaterialFlag(False)
    return ar


def build_preview(parent, name, maps, w):
    """UsdPreviewSurface explicito -- o esquema do Asset_USD_Builder.

    E' o shader que o GL/hydra le SEM renderer nenhum: sem ele, so' build
    com Karma/MtlX mostrava textura na cena (pedido do Matheus). Copia do
    MatLib do HDA: UsdUVTexture de cor (sRGB) + de opacity -> preview.
    """
    from .mat_extra import ctx_subnet
    sub = ctx_subnet(parent, "preview_" + name, "")
    out = sub.node("suboutput1")
    ps = sub.createNode("usdpreviewsurface", "usdpreviewsurface")
    out.setInput(0, ps, 0)
    w.set(out, "name1", "surface")

    cat = hou.vopNodeTypeCategory()
    tipo_tex = ("usduvtexture::2.0"
                if cat.nodeType("usduvtexture::2.0") is not None
                else "usduvtexture")

    def tex(rotulo, path, srgb):
        t = sub.createNode(tipo_tex, rotulo)
        w.set(t, "file", path)
        # st desconectado le a primvar 'st' sozinho (igual ao HDA)
        w.set(t, "sourceColorSpace", "sRGB" if srgb else "raw")
        return t

    if "basecolor" in maps:
        w.connect(ps, "diffuseColor",
                  tex("UsdPrevColor", maps["basecolor"], True), "rgb")
    if "opacity" in maps:
        w.connect(ps, "opacity",
                  tex("UsdPrevOpacity", maps["opacity"], False), "r")
    sub.layoutChildren()
    return sub


def build_material(parent, name, maps, renderers=("karma", "arnold"),
                   plant=False, disp_scale=0.01, settings=None):
    """Cria o material `name`. Devolve (no_final, avisos).

    O no final leva o NOME EXATO da parte -- e' o contrato com o
    componentmaterial e com o shop_materialpath do FBX.
    """
    w = _W()

    # PRESET primeiro (a fase de LOOK): se o usuario salvou um preset
    # para (renderer, tipo da parte), ele manda -- so' as texturas sao
    # re-apontadas por papel. Sem preset, a receita de codigo.
    from .. import presets as _presets

    def _ou_preset(prefixo, construir):
        node = _presets.carregar(parent, prefixo, name)
        if node is not None:
            w.avisos.extend(_presets.aplicar_texturas(node, maps))
            return node
        return construir()

    ar = None
    if "arnold" in renderers:
        if arnold_available():
            ar = _ou_preset("arnold",
                            lambda: build_arnold(parent, name, maps, plant,
                                                 disp_scale, w, settings))
        else:
            w.warn("HtoA nao esta nesta sessao; '%s' sai sem Arnold" % name)

    km = None
    if "karma" in renderers:
        km = _ou_preset("karma",
                        lambda: build_karma(parent, name, maps, plant,
                                            disp_scale, w, settings))

    from . import mat_extra
    rman = None
    if "renderman" in renderers:
        if mat_extra.renderman_available():
            rman = _ou_preset(
                "renderman",
                lambda: mat_extra.build_renderman(parent, name, maps, plant,
                                                  disp_scale, w, settings))
        else:
            w.warn("RenderMan nao esta nesta sessao; '%s' sai sem" % name)
    vr = None
    if "vray" in renderers:
        if mat_extra.vray_available():
            vr = _ou_preset(
                "vray",
                lambda: mat_extra.build_vray(parent, name, maps, plant,
                                             disp_scale, w, settings))
        else:
            w.warn("V-Ray nao esta nesta sessao; '%s' sai sem" % name)

    # preview SEMPRE: o GL le este shader com qualquer combinacao de
    # renderers marcada (sem ele, so' o caminho MtlX aparecia na cena)
    pv = build_preview(parent, name, maps, w)

    # folha verde, tronco marrom (pedido do Matheus) -- nos builders e no
    # collect, para se achar de longe na materiallibrary
    cor = cor_da_parte(name)
    if cor is not None:
        for n in (ar, km, rman, vr, pv):
            if n is not None:
                n.setColor(cor)

    extras = [n for n in (ar, rman, vr, pv) if n is not None]

    col = parent.createNode("collect", name)
    if cor is not None:
        col.setColor(cor)
    i = 0
    for n in extras:
        # builder oficial do V-Ray expoe surface/displacement/volume, mas
        # so' a surface e' usada (displacement no V-Ray e' da geometria)
        n_outs = 1 if n.type().name() == "vray_vop_builder" \
            else len(n.outputNames())
        for oidx in range(n_outs):
            col.setInput(i, n, oidx)
            i += 1
    if km is not None:
        for oidx, oname in enumerate(km.outputNames()):
            # MEDIDO: ligar a saida 'properties' do builder oficial do
            # Karma no collect DERRUBA o terminal ri do RenderMan no
            # Material (bisseccao 2026-09-11). So' surface/displacement.
            if oname == "properties":
                continue
            col.setInput(i, km, oidx)
            i += 1
    return col, w.avisos
