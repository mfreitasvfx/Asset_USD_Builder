"""Construtores de material por renderer, para dentro de um materiallibrary.

A base e' o par de conversores da Rebelway (KB3D_converter / texture_from_disk)
que o Matheus forneceu: Karma (MaterialX) e Arnold no MESMO material via um
no `collect` -- e' assim que "todos os renderizadores" convivem num USD so'.

DESVIOS CONSCIENTES DA RECEITA REBELWAY
  * Eles poem roughness/metalness em "ACES/ACEScg" no Arnold. Mapa de DADO
    nao e' cor: aqui vai "Raw", como os proprios mapas de normal/opacity
    deles. Se um render A/B mostrar diferenca, e' um toggle num lugar so'.
  * Glossiness (Maxtree/Megascans antigos): eles nao tratam; aqui inverte
    (mtlxinvert no Karma, arnold::range 1->0 no Arnold).
  * Planta (gatilho `translucency`, ideia do Matheus): thin_walled +
    subsurface com o mapa de translucency como subsurface_color -- o
    equivalente standard_surface do thin-walled+SSS que fizemos no V-Ray.

Papeis esperados em `maps`: os de naming.SUFFIX_ROLE (basecolor, roughness,
glossiness, metalness, normal, displacement, opacity, emission, translucency,
refraction, ao...).
"""

# -- tabelas: papel -> input do standard_surface -------------------------
# (mesmos nomes nas duas implementacoes, que seguem a spec standard_surface)
_DIRETO = {
    "basecolor": "base_color",
    "metalness": "metalness",
    "roughness": "specular_roughness",
    "opacity": "opacity",
    "refraction": "transmission",
    "emission": "emission_color",
}

# colorspace por papel
_COR = {"basecolor", "emission"}          # sRGB texture
# todo o resto e' dado (Raw)


class _W(object):
    """Coletor de avisos + set/connect tolerantes (padrao dos outros modulos)."""

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


# ==========================================================================
# Karma / MaterialX
# ==========================================================================

def build_karma(parent, name, maps, plant=False, disp_scale=0.01, w=None):
    """mtlxstandard_surface + mtlximage por mapa. Devolve (surface, disp)."""
    w = w or _W()
    surf = parent.createNode("mtlxstandard_surface", name + "_mtlx")
    disp = None

    def image(role, path, signature):
        img = parent.createNode("mtlximage", "%s_%s_km" % (name, role))
        w.set(img, "signature", signature)
        w.set(img, "file", path)
        return img

    for role, inp in _DIRETO.items():
        if role not in maps:
            continue
        sig = "color3" if role in _COR else "default"
        img = image(role, maps[role], sig)
        w.connect(surf, inp, img, "out")
        if role == "emission":
            w.set(surf, "emission", 1)

    if "glossiness" in maps and "roughness" not in maps:
        img = image("glossiness", maps["glossiness"], "default")
        inv = parent.createNode("mtlxinvert", name + "_gloss2rough_km")
        w.set(inv, "signature", "float")
        w.connect(inv, "in", img, "out")
        w.connect(surf, "specular_roughness", inv, "out")

    if "normal" in maps:
        img = image("normal", maps["normal"], "vector3")
        nm = parent.createNode("mtlxnormalmap", name + "_nrm_km")
        w.connect(nm, "in", img, "out")
        w.connect(surf, "normal", nm, "out")

    if "displacement" in maps:
        img = image("displacement", maps["displacement"], "default")
        disp = parent.createNode("mtlxdisplacement", name + "_disp_km")
        w.set(disp, "scale", disp_scale)
        w.connect(disp, "displacement", img, "out")

    if plant and "translucency" in maps:
        img = image("translucency", maps["translucency"], "color3")
        w.set(surf, "thin_walled", 1)
        w.set(surf, "subsurface", 1.0)
        w.connect(surf, "subsurface_color", img, "out")

    return surf, disp


# ==========================================================================
# Arnold (HtoA) -- receita Rebelway, com os desvios documentados no topo
# ==========================================================================

def arnold_available():
    import hou
    return any("htoa" in x.lower() for x in hou.houdiniPath())


def build_arnold(parent, name, maps, plant=False, disp_scale=0.01, w=None):
    """arnold_materialbuilder completo. Devolve o builder (ou None)."""
    w = w or _W()
    try:
        ar = parent.createNode("arnold_materialbuilder", name + "_arnold")
    except Exception as e:
        w.warn("arnold_materialbuilder indisponivel: %s" % e)
        return None

    out = ar.node("OUT_material")
    surf = ar.createNode("standard_surface")
    out.setInput(0, surf, 0)

    def image(role, path, cor):
        img = ar.createNode("image", "%s_%s_ar" % (name, role))
        w.set(img, "filename", path)
        w.set(img, "color_family", "Utility")
        w.set(img, "color_space", "sRGB - Texture" if cor else "Raw")
        if not cor:
            w.set(img, "single_channel", 1)
        return img

    for role, inp in _DIRETO.items():
        if role not in maps:
            continue
        cor = role in _COR
        img = image(role, maps[role], cor)
        w.connect(surf, inp, img, "rgba" if cor else "r")
        if role == "emission":
            w.set(surf, "emission", 1)

    if "glossiness" in maps and "roughness" not in maps:
        img = image("glossiness", maps["glossiness"], False)
        rng = ar.createNode("arnold::range", name + "_gloss2rough_ar")
        w.set(rng, "output_min", 1.0)   # 1->0: inverte
        w.set(rng, "output_max", 0.0)
        w.connect(rng, "input", img, "rgba")
        w.connect(surf, "specular_roughness", rng, "r")

    if "normal" in maps:
        img = ar.createNode("image", "%s_normal_ar" % name)
        w.set(img, "filename", maps["normal"])
        w.set(img, "color_family", "Utility")
        w.set(img, "color_space", "Raw")
        nm = ar.createNode("normal_map")
        w.connect(nm, "input", img, "rgba")
        w.connect(surf, "normal", nm, "vector")

    if "displacement" in maps:
        img = image("displacement", maps["displacement"], False)
        mult = ar.createNode("arnold::multiply", name + "_dispamt_ar")
        for c in ("input2r", "input2g", "input2b"):
            w.set(mult, c, disp_scale)
        w.connect(mult, "input1", img, "rgba")
        w.connect(out, "displacement", mult, "rgb")

    if plant and "translucency" in maps:
        img = image("translucency", maps["translucency"], True)
        w.set(surf, "thin_walled", 1)
        w.set(surf, "subsurface", 1.0)
        w.connect(surf, "subsurface_color", img, "rgba")

    ar.layoutChildren()
    ar.setMaterialFlag(False)
    return ar


# ==========================================================================
# o material completo: collect juntando os renderers disponiveis
# ==========================================================================

def build_material(parent, name, maps, renderers=("karma", "arnold"),
                   plant=False, disp_scale=0.01):
    """Cria o material `name` no materiallibrary `parent`.

    Devolve (no_final, avisos). O no final leva o NOME EXATO da parte --
    e' ele que o componentmaterial referencia, entao o nome e' o contrato.
    """
    w = _W()
    terminais = []      # (node, out_index)

    ar = None
    if "arnold" in renderers:
        if arnold_available():
            ar = build_arnold(parent, name, maps, plant, disp_scale, w)
        else:
            w.warn("HtoA nao esta no HOUDINI_PATH desta sessao; material "
                   "'%s' sai sem Arnold" % name)
    if ar is not None:
        terminais.append((ar, 0))

    km_surf, km_disp = (None, None)
    if "karma" in renderers:
        km_surf, km_disp = build_karma(parent, name, maps, plant,
                                       disp_scale, w)

    if not terminais and km_surf is not None:
        # so' Karma: o proprio surface (e disp) publicam direto
        if km_disp is None:
            km_surf.setName(name, unique_name=True)
            return km_surf, w.avisos

    col = parent.createNode("collect", name)
    i = 0
    for node, outidx in terminais:
        col.setInput(i, node, outidx)
        i += 1
    if km_surf is not None:
        col.setInput(i, km_surf, 0)
        i += 1
    if km_disp is not None:
        col.setInput(i, km_disp, 0)
        i += 1
    return col, w.avisos
