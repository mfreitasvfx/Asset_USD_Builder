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
    # RenderMan Material Builder, nao subnet generico: o builder tem render
    # mask 'RIB' (medido) e e' isso que faz o TAB listar os nos Pxr* --
    # no subnet generico (mask vazia) o Matheus nao conseguia criar no'
    # nenhum a mao. Por dentro vem um output_collect: surface no input 0,
    # displacement no 1, e o builder expoe 'surface'/'displacement' para
    # o collect externo. O preview_surface automatico dele NAO toma o
    # outputs:surface do nosso preview (medido nas duas ordens).
    sub = parent.createNode("pxrmaterialbuilder", "renderman_" + name)
    out = sub.node("output_collect")
    surf = sub.createNode("pxrsurface", "surface")
    out.setInput(0, surf, 0)
    # frente/verso SEMPRE (pedido do Matheus: todo setup RenderMan)
    w.set(surf, "diffuseDoubleSided", 1)
    w.set(surf, "specularDoubleSided", 1)

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
    # SEMPRE via PxrMetallicWorkflow (pedido do Matheus): sem mapa de
    # metalness o metallic fica no default 0 e o workflow so' passa o
    # basecolor -- mas o no' ja' esta' la' para ele ligar o que quiser
    mw = sub.createNode("pxrmetallicworkflow::3.0", "metallic_workflow")
    if base is not None:
        w.connect(mw, "baseColor", base, "resultRGB")
    if "metalness" in maps:
        mimg = image("metalness", maps["metalness"], False)
        w.connect(mw, "metallic", remap("metalness", mimg), "resultR")
    w.connect(surf, "diffuseColor", mw, "resultDiffuseRGB")
    w.connect(surf, "specularEdgeColor", mw, "resultSpecularEdgeRGB")
    w.connect(surf, "specularFaceColor", mw, "resultSpecularFaceRGB")

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
        w.connect(mw, "specular", cc("specular", img), "resultRGB")

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

    from .materials import eh_folha
    if plant and ("translucency" in maps or eh_folha(name)):
        # folha sem mapa de translucency entra pelo NOME (Maxtree nao
        # entrega p/ todas): transmit ganha o gain, cor fica default
        w.set(surf, "diffuseTransmitGain", s["subsurface"])
        if "translucency" in maps:
            img = image("translucency", maps["translucency"], True)
            w.connect(surf, "diffuseTransmitColor",
                      cc("translucency", img), "resultRGB")

    if "back_basecolor" in maps:
        # frente/verso do box Two-Sided, jeito oficial do PxrSurface
        # (Args do RMan 27.3: diffuseDoubleSided/specularDoubleSided +
        # diffuseBackColor). Verso ESPELHADO (mesmo arquivo da frente)
        # usa a propria cor -- sem segunda leitura de textura; verso
        # REAL (_Back) entra em diffuseBackColor.
        if maps["back_basecolor"] == maps.get("basecolor"):
            w.set(surf, "diffuseBackUseDiffuseColor", 1)
        else:
            w.set(surf, "diffuseBackUseDiffuseColor", 0)
            imgb = image("back_basecolor", maps["back_basecolor"], True)
            w.connect(surf, "diffuseBackColor",
                      cc("back_basecolor", imgb), "resultRGB")

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
    rough_src = None
    if "roughness" in maps:
        w.set(brdf, "option_use_roughness", "1")
        rough_src = remap("roughness", tex("roughness", maps["roughness"]))
        w.connect(brdf, "reflect_glossiness", rough_src, "value")
    elif "glossiness" in maps:
        rough_src = remap("glossiness",
                          tex("glossiness", maps["glossiness"]))
        w.connect(brdf, "reflect_glossiness", rough_src, "value")
    if "metalness" in maps:
        w.connect(brdf, "metalness",
                  remap("metalness", tex("metalness", maps["metalness"])),
                  "value")
    # normal via BRDFBump -- o manual da Chaos (V-Ray Bump): um WRAPPER
    # entre o material base e a saida, nao o bump_map do proprio BRDF
    # (o Matheus achou a forma certa na rede do Cosmos)
    final_brdf = brdf
    if "normal" in maps:
        bp = sub.createNode("VRayNodeBRDFBump", "bump")
        w.connect(bp, "base_brdf", brdf, "brdf")
        w.set(bp, "map_type", "1")            # Normal (Tangent)
        if s["normal_scale"] != 1.0:
            w.set(bp, "bump_tex_mult", s["normal_scale"])
            w.set(bp, "normal_map_mult", s["normal_scale"])
        w.connect(bp, "bump_tex_color", tex("normal", maps["normal"]),
                  "color")
        final_brdf = bp
    out.setInput(0, final_brdf, 0)
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

    # frente/verso (video das folhas): so' quando o pacote traz textura
    # de verso. Mtl2Sided combina os DOIS materiais; a translucency vai
    # no slot do 2Sided, e o thin-walled fica FORA (no video, com 2Sided
    # o thin-walled anula a translucency).
    tem_verso = "back_basecolor" in maps
    if tem_verso:
        bb = sub.createNode("VRayNodeBRDFVRayMtl", "surface_back")
        w.connect(bb, "diffuse",
                  cc("back_basecolor", tex("back_basecolor",
                                           maps["back_basecolor"],
                                           cor=True)), "out_color")
        if rough_src is not None:
            w.set(bb, "reflect", [1.0, 1.0, 1.0, 1.0])
            if "roughness" in maps:
                w.set(bb, "option_use_roughness", "1")
            w.connect(bb, "reflect_glossiness", rough_src, "value")
        m2 = sub.createNode("VRayNodeMtl2Sided", "two_sided")
        w.connect(m2, "front", final_brdf, "brdf")
        w.connect(m2, "back", bb, "brdf")
        if "translucency" in maps:
            w.connect(m2, "translucency_tex",
                      cc("translucency",
                         tex("translucency", maps["translucency"],
                             cor=True)), "out_color")
        out.setInput(0, m2, 0)

    from .materials import eh_folha
    if plant and not tem_verso \
            and ("translucency" in maps or eh_folha(name)):
        # folhas: thin-walled + translucency SSS (Jonas Noell) com a
        # correcao do Matheus, confirmada no manual/SDK da Chaos: o mapa
        # de translucency e' COR -- e neste build do vfh o slot de cor
        # texturavel e' fog_color_tex (translucency_color existe so' como
        # parm; o amount e' ESCALAR = subsurface, nunca perto de 1).
        w.set(brdf, "translucency", "6")          # SSS (enum medido)
        w.set(brdf, "refract_thin_walled", True)
        w.set(brdf, "option_double_sided", True)
        # refract fica no DEFAULT (preto) -- apontado pelo Matheus: com
        # thin-walled SSS, refract=1 deixava a folha vitrea/transparente
        if "opacity" in maps:
            w.set(brdf, "opacity_mode", "1")      # Clip
        # MEDIDO entre builds do vfh: o V-Ray 7.00 (Houdini 20.5) expoe o
        # input translucency_color; o 7.10/Update 1 (Houdini 21.0) removeu.
        if "translucency_color" in brdf.inputNames():
            w.set(brdf, "translucency_amount", s["subsurface"])
            if "translucency" in maps:
                w.connect(brdf, "translucency_color",
                          cc("translucency",
                             tex("translucency", maps["translucency"],
                                 cor=True)), "out_color")
        else:
            # setup do Matheus para a versao SEM mascara de cor (2026-09-21):
            # Type SSS, Method Directional, Radius 1 1 1, Scale 1 cm, COR
            # fixa verde HSV(84, 0.781, 0.5) e o mapa de translucency
            # entrando como AMOUNT por um TexRemap 0.2..1 (Amount fica
            # conectado, nao escalar). glossiness_remap 0.2..0.9.
            w.set(brdf, "translucency_surfaceLighting", "0")   # Directional
            w.set(brdf, "translucency_color", (0.3438, 0.5, 0.1095, 1.0))
            w.set(brdf, "fog_color", (1.0, 1.0, 1.0, 1.0))      # Radius
            w.set(brdf, "fog_mult", 1.0)                        # Scale (cm)
            if "translucency" in maps:
                tr = remap("translucency",
                           tex("translucency", maps["translucency"]))
                w.set(tr, "output_min", 0.2)
                w.set(tr, "output_max", 1.0)
                w.connect(brdf, "translucency_amount", tr, "value")
            else:
                w.set(brdf, "translucency_amount", s["subsurface"])
            if "glossiness" in maps and rough_src is not None:
                w.set(rough_src, "output_min", 0.2)
                w.set(rough_src, "output_max", 0.9)

    if s["basecolor_gamma"] != 1.0:
        w.warn("basecolor_gamma custom nao aplicado em V-Ray (BitmapBuffer "
               "ja faz sRGB); '%s'" % name)

    sub.layoutChildren()
    sub.setMaterialFlag(False)   # quem publica e' o collect
    return sub
