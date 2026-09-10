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
    """Subnet de material MaterialX com o minimo que faz publicar certo.

    rendercontext 'mtlx' (medido) + forcechildren (receita Rebelway).
    """
    sub = parent.createNode("subnet", nome)
    g = sub.parmTemplateGroup()
    f = hou.FolderParmTemplate("folder1", "Material Builder",
                               folder_type=hou.folderType.Collapsible,
                               tags={"sidefx::shader_isparm": "0"})
    rc = hou.properties.parmTemplate("vopui", "shader_rendercontextname")
    rc.setDefaultValue(["mtlx"])
    f.addParmTemplate(rc)
    fc = hou.ToggleParmTemplate("shader_forcechildren",
                                "Force Translation of Children",
                                default_value=True)
    fc.setTags({"sidefx::shader_isparm": "0", "spare_category": "Shader"})
    f.addParmTemplate(fc)
    g.append(f)
    sub.setParmTemplateGroup(g)
    sub.setMaterialFlag(True)
    return sub


def build_karma(parent, name, maps, plant=False, disp_scale=0.01, w=None):
    """Subnet 'karma_<name>' completo. Devolve o subnet."""
    w = w or _W()
    sub = _karma_subnet(parent, "karma_" + name)
    out = sub.node("suboutput1")
    surf = sub.createNode("mtlxstandard_surface", "surface")
    out.setInput(0, surf, 0)
    w.set(out, "name1", "surface")
    disp = None

    def image(role, path, signature):
        img = sub.createNode("mtlximage", role)
        w.set(img, "signature", signature)
        w.set(img, "file", path)
        return img

    for role, inp in _DIRETO.items():
        if role not in maps:
            continue
        img = image(role, maps[role], "color3" if role in _COR else "default")
        w.connect(surf, inp, img, "out")
        if role == "emission":
            w.set(surf, "emission", 1)

    if "glossiness" in maps and "roughness" not in maps:
        img = image("glossiness", maps["glossiness"], "default")
        inv = sub.createNode("mtlxinvert", "invert")
        w.set(inv, "signature", "float")
        w.connect(inv, "in", img, "out")
        w.connect(surf, "specular_roughness", inv, "out")

    if "normal" in maps:
        img = image("normal", maps["normal"], "vector3")
        nm = sub.createNode("mtlxnormalmap", "normal_map")
        w.connect(nm, "in", img, "out")
        w.connect(surf, "normal", nm, "out")

    if "displacement" in maps:
        img = image("height", maps["displacement"], "default")
        disp = sub.createNode("mtlxdisplacement", "displacement")
        w.set(disp, "scale", disp_scale)
        w.connect(disp, "displacement", img, "out")
        out.setInput(1, disp, 0)
        w.set(out, "name2", "displacement")

    if plant and "translucency" in maps:
        img = image("translucency", maps["translucency"], "color3")
        w.set(surf, "thin_walled", 1)
        w.set(surf, "subsurface", 1.0)
        w.connect(surf, "subsurface_color", img, "out")

    sub.layoutChildren()
    return sub


def arnold_available():
    return any("htoa" in x.lower() for x in hou.houdiniPath())


def build_arnold(parent, name, maps, plant=False, disp_scale=0.01, w=None):
    """arnold_materialbuilder 'arnold_<name>'. Devolve o builder (ou None)."""
    w = w or _W()
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
        w.connect(nm, "input", img, "rgba")
        w.connect(surf, "normal", nm, "vector")

    if "displacement" in maps:
        img = image("height", maps["displacement"], False)
        mult = ar.createNode("arnold::multiply", "displacement_amount")
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


def build_material(parent, name, maps, renderers=("karma", "arnold"),
                   plant=False, disp_scale=0.01):
    """Cria o material `name`. Devolve (no_final, avisos).

    O no final leva o NOME EXATO da parte -- e' o contrato com o
    componentmaterial e com o shop_materialpath do FBX.
    """
    w = _W()

    ar = None
    if "arnold" in renderers:
        if arnold_available():
            ar = build_arnold(parent, name, maps, plant, disp_scale, w)
        else:
            w.warn("HtoA nao esta nesta sessao; '%s' sai sem Arnold" % name)

    km = build_karma(parent, name, maps, plant, disp_scale, w) \
        if "karma" in renderers else None

    if ar is None and km is not None:
        km.setName(name, unique_name=True)
        return km, w.avisos

    col = parent.createNode("collect", name)
    i = 0
    if ar is not None:
        col.setInput(i, ar, 0)
        i += 1
    if km is not None:
        for oidx in range(len(km.outputNames())):
            col.setInput(i, km, oidx)
            i += 1
    return col, w.avisos
