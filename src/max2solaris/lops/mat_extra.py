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

Os dois publicam via subnet com rendercontext ('ri' / 'vray') -- o mesmo
mecanismo medido do subnet mtlx: o contexto vira o namespace do output
(outputs:ri:surface, outputs:vray:surface).
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
                    w=None):
    sub = ctx_subnet(parent, "renderman_" + name, "ri")
    out = sub.node("suboutput1")
    surf = sub.createNode("pxrsurface", "surface")
    out.setInput(0, surf, 0)
    w.set(out, "name1", "surface")

    def image(role, path, cor):
        img = sub.createNode("pxrtexture", role)
        w.set(img, "filename", path)
        w.set(img, "linearize", 1 if cor else 0)
        return img

    def tofloat(role, src):
        tf = sub.createNode("pxrtofloat", role + "_f")
        w.connect(tf, "input", src, "resultRGB")
        return tf

    if "basecolor" in maps:
        img = image("basecolor", maps["basecolor"], True)
        w.connect(surf, "diffuseColor", img, "resultRGB")

    if "roughness" in maps:
        img = image("roughness", maps["roughness"], False)
        w.connect(surf, "specularRoughness",
                  tofloat("roughness", img), "resultF")
    elif "glossiness" in maps:
        img = image("glossiness", maps["glossiness"], False)
        inv = sub.createNode("pxrinvert", "invert")
        w.connect(inv, "inputRGB", img, "resultRGB")
        tf = sub.createNode("pxrtofloat", "roughness_f")
        w.connect(tf, "input", inv, "resultRGB")
        w.connect(surf, "specularRoughness", tf, "resultF")

    if "specular" in maps:
        img = image("specular", maps["specular"], True)
        w.connect(surf, "specularEdgeColor", img, "resultRGB")

    if "metalness" in maps:
        image("metalness", maps["metalness"], False)  # solto, como no HDA
        w.warn("PxrSurface nao tem input de metallic; mapa de '%s' criado "
               "sem ligar (igual ao Asset_USD_Builder). Metal fiel em "
               "RenderMan vem com o LAMA depois." % name)

    if "opacity" in maps:
        img = image("opacity", maps["opacity"], False)
        w.connect(surf, "presence", tofloat("opacity", img), "resultF")

    if "emission" in maps:
        img = image("emission", maps["emission"], True)
        w.connect(surf, "glowColor", img, "resultRGB")
        w.set(surf, "glowGain", 1.0)

    if "normal" in maps:
        img = image("normal", maps["normal"], False)
        nm = sub.createNode("pxrnormalmap", "normal_map")
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

    if plant and "translucency" in maps:
        img = image("translucency", maps["translucency"], True)
        w.connect(surf, "diffuseTransmitColor", img, "resultRGB")
        w.set(surf, "diffuseTransmitGain", 1.0)
        w.set(surf, "diffuseDoubleSided", 1)

    sub.layoutChildren()
    return sub


def build_vray(parent, name, maps, plant=False, disp_scale=0.01, w=None):
    sub = ctx_subnet(parent, "vray_" + name, "vray")
    out = sub.node("suboutput1")
    brdf = sub.createNode("VRayNodeBRDFVRayMtl", "surface")
    mtl = sub.createNode("VRayNodeMtlSingleBRDF", "material")
    w.connect(mtl, "brdf", brdf, "brdf")
    out.setInput(0, mtl, 0)
    w.set(out, "name1", "surface")

    def tex(role, path):
        buf = sub.createNode("VRayNodeBitmapBuffer", role + "_file")
        w.set(buf, "file", path)
        t = sub.createNode("VRayNodeTexBitmap", role)
        w.connect(t, "bitmap", buf, "bitmap")
        return t

    if "basecolor" in maps:
        w.connect(brdf, "diffuse", tex("basecolor", maps["basecolor"]),
                  "color")
    if "roughness" in maps:
        w.set(brdf, "option_use_roughness", "1")
        w.connect(brdf, "reflect_glossiness",
                  tex("roughness", maps["roughness"]), "intensity")
    elif "glossiness" in maps:
        w.connect(brdf, "reflect_glossiness",
                  tex("glossiness", maps["glossiness"]), "intensity")
    if "metalness" in maps:
        w.connect(brdf, "metalness", tex("metalness", maps["metalness"]),
                  "intensity")
    if "normal" in maps:
        w.set(brdf, "bump_type", "1")
        w.connect(brdf, "bump_map", tex("normal", maps["normal"]), "color")
    if "opacity" in maps:
        w.connect(brdf, "opacity", tex("opacity", maps["opacity"]),
                  "intensity")
    if "emission" in maps:
        w.connect(brdf, "self_illumination",
                  tex("emission", maps["emission"]), "color")
    if "refraction" in maps:
        w.connect(brdf, "refract", tex("refraction", maps["refraction"]),
                  "color")
    if "displacement" in maps:
        w.warn("displacement no V-Ray e' da geometria (VRayGeomDisplacedMesh),"
               " nao do material; '%s' sai sem" % name)

    if plant and "translucency" in maps:
        w.set(brdf, "translucency", "6")          # SSS (enum medido)
        w.set(brdf, "refract_thin_walled", True)
        w.set(brdf, "option_double_sided", True)
        w.set(brdf, "refract", [1.0, 1.0, 1.0, 1.0])
        w.connect(brdf, "translucency_amount",
                  tex("translucency", maps["translucency"]), "intensity")

    sub.layoutChildren()
    return sub
