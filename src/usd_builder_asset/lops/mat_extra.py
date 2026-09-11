"""Materiais RenderMan (PxrSurface) e V-Ray para o collect.

RENDERMAN -- a receita do Asset_USD_Builder, sem a etapa .tex:
    roughness via PxrToFloat -> specularRoughness; specular no
    specularEdgeColor; opacity no presence; normal via PxrNormalMap no
    bumpNormal; displacement via PxrDispTransform + PxrDisplace; PLANT liga
    diffuseDoubleSided + diffuseTransmitGain com o mapa de translucency.
    Metalness: o HDA cria o mapa e NAO liga (PxrSurface nao tem input de
    metallic; conferido no proprio codigo dele, NodeOutput=False) -- fazemos
    igual, com aviso. LAMA fica pra depois, como o Matheus pediu.

V-RAY -- a tabela medida no max2lama, agora no collect:
    roughness usa option_use_roughness='1'; normal entra no bump_map com
    bump_type='1'; enums do V-Ray sao parms STRING. Displacement no V-Ray
    nao mora no material (VRayGeomDisplacedMesh) -- fica de fora, com aviso.
    No V-Ray do 21.0 `translucency_color` nao aceita mapa (medido); o que
    conecta e' `translucency_amount`.

    MEDIDO (2026-09-10): o subnet generico com rendercontext 'vray'
    publicava MtlSingleBRDF com terminal `outputs:material` dentro de um
    NodeGraph -- forma que o delegate Hydra do V-Ray NAO resolve (material
    cinza no viewport). O builder OFICIAL (`vray_vop_builder`, com o
    vray_material_output dentro) publica `outputs:surface ->
    BRDFVRayMtl.outputs:brdf` direto -- a forma que o tradutor do proprio
    V-Ray emite. Usamos o oficial.

    BitmapBuffer: transfer_function default e' sRGB (3). Mapa de DADO
    (roughness/normal/metalness/opacity...) precisa ser linear ('0').

RenderMan publica via subnet com rendercontext 'ri' -- o mesmo mecanismo
medido do subnet mtlx: o contexto vira o namespace do output
(outputs:ri:surface).
"""
import hou


def ctx_subnet(parent, nome, ctx):
    sub = parent.createNode("subnet", nome)
    g = sub.parmTemplateGroup()
    f = hou.FolderParmTemplate("folder1", "Material Builder",
                               folder_type=hou.folderType.Collapsible,
                               tags={"sidefx::shader_isparm": "0"})
    rc = hou.properties.parmTemplate("vopui", "shader_rendercontextname")
    rc.setDefaultValue([ctx])
    f.addParmTemplate(rc)
    fc = hou.ToggleParmTemplate("shader_forcechildren", "Force Children",
                                default_value=True)
    fc.setTags({"sidefx::shader_isparm": "0", "spare_category": "Shader"})
    f.addParmTemplate(fc)
    g.append(f)
    sub.setParmTemplateGroup(g)
    sub.setMaterialFlag(True)
    return sub


def renderman_available():
    return "pxrsurface" in hou.vopNodeTypeCategory().nodeTypes()


def vray_available():
    return "VRayNodeBRDFVRayMtl" in hou.vopNodeTypeCategory().nodeTypes()


def build_renderman(parent, name, maps, plant=False, disp_scale=0.01,
                    w=None, settings=None):
    from .materials import _cfg
    s = _cfg(settings)
    sub = ctx_subnet(parent, "renderman_" + name, "ri")
    out = sub.node("suboutput1")
    surf = sub.createNode("pxrsurface", "surface")
    out.setInput(0, surf, 0)
    w.set(out, "name1", "surface")

    def image(role, path, cor):
        if s.get("tex_renderman"):
            # a etapa .tex ACEScg do Asset_USD_Builder (texconv.py)
            from .. import texconv
            path = texconv.tex(path, role, avisos=w.avisos)
        img = sub.createNode("pxrtexture", role)
        w.set(img, "filename", path)
        # linearize DESLIGADO -- medido pelo Matheus no viewport: o color
        # manager do RfH (e o .tex ACEScg) ja entregam linear; com
        # linearize=1 a cor corrigia duas vezes
        w.set(img, "linearize", 0)
        return img

    def tofloat(role, src):
        tf = sub.createNode("pxrtofloat", role + "_f")
        w.connect(tf, "input", src, "resultRGB")
        return tf

    def cc(role, src):
        # colorcorrect neutro no caminho de toda COR ("se eu quiser
        # alterar valor" -- pedido do Matheus)
        n = sub.createNode("pxrcolorcorrect::3.0", role + "_cc")
        w.connect(n, "inputRGB", src, "resultRGB")
        return n

    def remap(role, src):
        # remap neutro no caminho de todo DADO
        n = sub.createNode("pxrremap::3.0", role + "_remap")
        w.connect(n, "inputRGB", src, "resultRGB")
        return n

    base = None
    if "basecolor" in maps:
        img = image("basecolor", maps["basecolor"], True)
        base = cc("basecolor", img)
        g = s["basecolor_gamma"]
        w.set(base, "gamma", (g, g, g))

    # metallic via PxrMetallicWorkflow (achado do Matheus: e' assim que o
    # material builder liga metal no PxrSurface)
    mw = None
    if "metalness" in maps:
        mimg = image("metalness", maps["metalness"], False)
        mrm = remap("metalness", mimg)
        mw = sub.createNode("pxrmetallicworkflow::3.0", "metallic_workflow")
        if base is not None:
            w.connect(mw, "baseColor", base, "resultRGB")
        w.connect(mw, "metallic", mrm, "resultR")
        w.connect(surf, "diffuseColor", mw, "resultDiffuseRGB")
        w.connect(surf, "specularEdgeColor", mw, "resultSpecularEdgeRGB")
        w.connect(surf, "specularFaceColor", mw, "resultSpecularFaceRGB")
    elif base is not None:
        w.connect(surf, "diffuseColor", base, "resultRGB")

    if "roughness" in maps:
        img = image("roughness", maps["roughness"], False)
        w.connect(surf, "specularRoughness",
                  tofloat("roughness", remap("roughness", img)), "resultF")
    elif "glossiness" in maps:
        img = image("glossiness", maps["glossiness"], False)
        inv = sub.createNode("pxrinvert", "invert")
        w.connect(inv, "inputRGB", img, "resultRGB")
        tf = sub.createNode("pxrtofloat", "roughness_f")
        w.connect(tf, "input", inv, "resultRGB")
        w.connect(surf, "specularRoughness", tf, "resultF")

    if "specular" in maps:
        img = image("specular", maps["specular"], True)
        if mw is not None:
            w.connect(mw, "specular", cc("specular", img), "resultRGB")
        else:
            w.connect(surf, "specularEdgeColor",
                      cc("specular", img), "resultRGB")

    if "opacity" in maps:
        img = image("opacity", maps["opacity"], False)
        w.connect(surf, "presence",
                  tofloat("opacity", remap("opacity", img)), "resultF")

    if "emission" in maps:
        img = image("emission", maps["emission"], True)
        w.connect(surf, "glowColor", cc("emission", img), "resultRGB")
        w.set(surf, "glowGain", 1.0)

    if "normal" in maps:
        img = image("normal", maps["normal"], False)
        nm = sub.createNode("pxrnormalmap", "normal_map")
        if s["normal_scale"] != 1.0:
            w.set(nm, "bumpScale", s["normal_scale"])
        w.connect(nm, "inputRGB", img, "resultRGB")
        w.connect(surf, "bumpNormal", nm, "resultN")

    if "displacement" in maps:
        img = image("height", maps["displacement"], False)
        dt = sub.createNode("pxrdisptransform", "disp_transform")
        w.set(dt, "dispRemapMode", 2)
        w.connect(dt, "dispScalar", tofloat("height", img), "resultF")
        dp = sub.createNode("pxrdisplace", "displace")
        w.set(dp, "dispAmount", disp_scale)
        w.connect(dp, "dispScalar", dt, "resultF")
        out.setInput(1, dp, 0)
        w.set(out, "name2", "displacement")

    from .materials import eh_folha
    if plant and ("translucency" in maps or eh_folha(name)):
        # folha sem mapa de translucency entra pelo NOME (Maxtree nao
        # entrega p/ todas): transmit ganha o gain, cor fica default
        w.set(surf, "diffuseTransmitGain", s["subsurface"])
        w.set(surf, "diffuseDoubleSided", 1)
        if "translucency" in maps:
            img = image("translucency", maps["translucency"], True)
            w.connect(surf, "diffuseTransmitColor",
                      cc("translucency", img), "resultRGB")

    sub.layoutChildren()
    return sub


def build_vray(parent, name, maps, plant=False, disp_scale=0.01, w=None,
               settings=None):
    from .materials import _cfg
    s = _cfg(settings)
    # builder OFICIAL do V-Ray: BRDF direto no vray_material_output.
    # (o subnet generico publicava uma forma que o delegate nao le.)
    sub = parent.createNode("vray_vop_builder", "vray_" + name)
    out = sub.node("vrayOutput")
    # REUSA o vrayMtl que o builder ja traz -- criar outro deixava o
    # default solto na rede (apontado pelo Matheus)
    brdf = sub.node("vrayMtl") or sub.createNode("VRayNodeBRDFVRayMtl",
                                                 "surface")
    brdf.setName("surface")
    out.setInput(0, brdf, 0)              # input 0 = Material

    def tex(role, path, cor=False):
        # MetaImageFile, nao TexBitmap+BitmapBuffer: o Matheus testou no
        # viewport -- o par nao renderizava; o MetaImageFile com OCIO
        # (In sRGB do config ativo -> Out ACEScg) funciona
        t = sub.createNode("VRayNodeMetaImageFile", role)
        w.set(t, "BitmapBuffer_file", path)
        if cor:
            from .. import texconv
            w.set(t, "TexOCIO_use", 1)
            w.set(t, "TexOCIO_inout_type", "0")   # By Color Space
            w.set(t, "TexOCIO_config_src", "1")   # Environment
            w.set(t, "TexOCIO_mode", "0")         # ColorSpace
            w.set(t, "TexOCIO_colorspace_in", texconv._resolve("srgb"))
            w.set(t, "TexOCIO_colorspace_out", texconv._resolve("acescg"))
        else:
            # mapa de dado = linear, sem OCIO
            w.set(t, "auto_color_space", 0)
            w.set(t, "BitmapBuffer_color_space", "0")
        return t

    def cc(role, t):
        # colorcorrect neutro no caminho da cor (ajuste manual)
        n = sub.createNode("VRayNodeColorCorrection", role + "_cc")
        w.connect(n, "texture_map", t, "color")
        return n                       # sai em 'out_color'

    def remap(role, t):
        # remap neutro no caminho do dado (ajuste manual)
        n = sub.createNode("VRayNodeTexRemap", role + "_remap")
        w.connect(n, "input_value", t, "intensity")
        return n                       # sai em 'value'

    if "basecolor" in maps:
        w.connect(brdf, "diffuse",
                  cc("basecolor", tex("basecolor", maps["basecolor"],
                                      cor=True)), "out_color")
    if "roughness" in maps or "glossiness" in maps:
        # Jonas Noell (video das folhas): reflexao em BRANCO PURO + mapa
        # de roughness -- o default preto do VRayMtl = specular nenhum
        w.set(brdf, "reflect", [1.0, 1.0, 1.0, 1.0])
    if "roughness" in maps:
        w.set(brdf, "option_use_roughness", "1")
        w.connect(brdf, "reflect_glossiness",
                  remap("roughness", tex("roughness", maps["roughness"])),
                  "value")
    elif "glossiness" in maps:
        w.connect(brdf, "reflect_glossiness",
                  remap("glossiness", tex("glossiness", maps["glossiness"])),
                  "value")
    if "metalness" in maps:
        w.connect(brdf, "metalness",
                  remap("metalness", tex("metalness", maps["metalness"])),
                  "value")
    if "normal" in maps:
        w.set(brdf, "bump_type", "1")
        if s["normal_scale"] != 1.0 and brdf.parm("bump_amount") is not None:
            w.set(brdf, "bump_amount", s["normal_scale"])
        w.connect(brdf, "bump_map", tex("normal", maps["normal"]), "color")
    if "opacity" in maps:
        w.connect(brdf, "opacity",
                  remap("opacity", tex("opacity", maps["opacity"])), "value")
    if "emission" in maps:
        w.connect(brdf, "self_illumination",
                  cc("emission", tex("emission", maps["emission"],
                                     cor=True)), "out_color")
    if "refraction" in maps:
        w.connect(brdf, "refract",
                  cc("refraction", tex("refraction", maps["refraction"],
                                       cor=True)), "out_color")
    if "displacement" in maps:
        w.warn("displacement no V-Ray e' da geometria (VRayGeomDisplacedMesh),"
               " nao do material; '%s' sai sem" % name)

    from .materials import eh_folha
    if plant and ("translucency" in maps or eh_folha(name)):
        # a receita do video das folhas do Jonas Noell (e2KqOfraUyw):
        # thin-walled + translucency SSS; opacity em CLIP (folha nao tem
        # pixel semi-transparente -- renderiza mais rapido). O mapa entra
        # no translucency_amount (o 21.0 nao tem input de SSS color,
        # medido); o 'translucency_remap' no caminho e' onde se doma a
        # intensidade -- Jonas nunca chega perto de 1. Folha SEM mapa
        # (Maxtree nao entrega p/ todas) entra pelo NOME, com amount fixo.
        w.set(brdf, "translucency", "6")          # SSS (enum medido)
        w.set(brdf, "refract_thin_walled", True)
        w.set(brdf, "option_double_sided", True)
        w.set(brdf, "refract", [1.0, 1.0, 1.0, 1.0])
        if "opacity" in maps:
            w.set(brdf, "opacity_mode", "1")      # Clip
        if "translucency" in maps:
            w.connect(brdf, "translucency_amount",
                      remap("translucency",
                            tex("translucency", maps["translucency"])),
                      "value")
        else:
            w.set(brdf, "translucency_amount", s["subsurface"])

    if s["basecolor_gamma"] != 1.0:
        w.warn("basecolor_gamma custom nao aplicado em V-Ray (BitmapBuffer "
               "ja faz sRGB); '%s'" % name)

    sub.layoutChildren()
    sub.setMaterialFlag(False)   # quem publica e' o collect
    return sub
