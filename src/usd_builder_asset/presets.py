"""Presets de shader editaveis -- o esquema do KB3D_Converter_2.0.

A fase de LOOK: o Matheus ajusta UM material no capricho (a qualidade do
canal do Jonas Noell), salva como preset, e TODO build seguinte daquele
renderer+tipo carrega o preset em vez da receita de codigo -- so' as
texturas sao re-apontadas, por PAPEL (os nomes basicos dos nos sao o
contrato: basecolor, roughness, normal...).

    preset = <repo>/presets/<renderer>_<tipo>.cpio
    renderer: karma | arnold | renderman | vray   (prefixo do no)
    tipo:     leaf | trunk | default              (tokens do nome da parte)

Salvar: selecionar o builder (ex.: vray_MT_..._Leaf_02) na materiallibrary
e apertar SAVE PRESET na aba SETTINGS. Nao ha magia: e' o
saveItemsToFile/loadItemsFromFile do proprio Houdini.
"""
import os

import hou

PRESET_DIR = r"C:/dev/USD_Builder_Asset/presets"
RENDERERS = ("karma", "arnold", "renderman", "vray")

# parm de arquivo por tipo de no de textura (medidos nos builders)
_PARM_ARQUIVO = {
    "mtlximage": "file",
    "VRayNodeMetaImageFile": "BitmapBuffer_file",
    "pxrtexture": "filename",
    "image": "filename",                 # arnold
}


def tipo_da_parte(nome):
    from .lops.materials import _TOKENS_FOLHA, _TOKENS_TRONCO
    low = nome.lower()
    if any(t in low for t in _TOKENS_FOLHA):
        return "leaf"
    if any(t in low for t in _TOKENS_TRONCO):
        return "trunk"
    return "default"


def caminho(renderer, tipo):
    return "%s/%s_%s.cpio" % (PRESET_DIR, renderer, tipo)


def salvar(node):
    """Salva um builder selecionado como preset. Devolve (caminho, tipo).

    O renderer sai do prefixo do nome (vray_X...), o tipo dos tokens do
    resto do nome.
    """
    nome = node.name()
    prefixo = nome.split("_", 1)[0]
    if prefixo not in RENDERERS:
        raise ValueError("selecione um builder de renderer "
                         "(karma_*/arnold_*/renderman_*/vray_*), nao %r"
                         % nome)
    resto = nome.split("_", 1)[1] if "_" in nome else nome
    tipo = tipo_da_parte(resto)
    if not os.path.isdir(PRESET_DIR):
        os.makedirs(PRESET_DIR)
    alvo = caminho(prefixo, tipo)
    node.parent().saveItemsToFile([node], alvo)
    return alvo, tipo


def carregar(parent, renderer, nome_parte):
    """Carrega o preset (renderer, tipo da parte) em `parent`, se existir.

    Devolve o no carregado (renomeado <renderer>_<nome_parte>) ou None.
    """
    arq = caminho(renderer, tipo_da_parte(nome_parte))
    if not os.path.isfile(arq):
        return None
    antes = set(parent.children())
    parent.loadItemsFromFile(arq)
    novos = [n for n in parent.children() if n not in antes]
    if not novos:
        return None
    node = novos[0]
    node.setName("%s_%s" % (renderer, nome_parte), unique_name=True)
    return node


def aplicar_texturas(node, maps):
    """Re-aponta os nos de textura do preset pelos PAPEIS. Devolve avisos.

    Papel sem no no preset ou no de textura sem mapa novo viram aviso --
    nunca corrigimos calados.
    """
    avisos = []
    filhos = {c.name(): c for c in node.children()}
    usados = set()
    for papel, arquivo in maps.items():
        alvo = filhos.get(papel)
        if alvo is None:
            if papel != "displacement" or "vray" not in node.name():
                avisos.append("preset %s: sem no p/ papel '%s'"
                              % (node.name(), papel))
            continue
        parm = _PARM_ARQUIVO.get(alvo.type().name())
        if parm is None or alvo.parm(parm) is None:
            avisos.append("preset %s: no '%s' (%s) sem parm de arquivo"
                          % (node.name(), papel, alvo.type().name()))
            continue
        alvo.parm(parm).set(str(arquivo).replace("\\", "/"))
        usados.add(papel)
    for nome, c in filhos.items():
        if nome not in usados and c.type().name() in _PARM_ARQUIVO \
                and nome in ("basecolor", "roughness", "glossiness",
                             "metalness", "normal", "opacity", "height",
                             "translucency", "emission", "refraction"):
            avisos.append("preset %s: no de textura '%s' sem mapa novo -- "
                          "mantive o do preset" % (node.name(), nome))
    return avisos
