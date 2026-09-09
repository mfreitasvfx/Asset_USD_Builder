"""A convencao de nomes e pastas que o Asset_USD_Builder espera.

Tudo aqui foi lido do PythonModule do HDA `Carlo_Jongen::Asset_USD_Builder`,
nao suposto. As referencias sao para quando o HDA mudar e algo parar de casar.

COMO O HDA ACHA UM ASSET  (Get_AssetSearchDict)
    Ele faz os.walk na Source Directory. Todo arquivo cujo caminho contenha
    `.<FileFormat>` (fbx, por padrao nosso) marca a PASTA QUE O CONTEM como
    raiz de um asset. Se o arquivo estiver dentro de uma subpasta `Var*`, a
    raiz vira o pai dessa subpasta:

        ObjSourceFileRaw.rsplit('/Var', 1)[0] + '/'

    Ou seja, um asset e' uma pasta. Nao ha arquivo de manifesto.

VARIANTES  (GetVariantList)
    Detectadas por regex no caminho: `VarA_`, `VarB_`... ou `Var1_`, `Var2_`.
    Sem nenhuma, o HDA assume uma unica variante chamada 'Var1'.

LOD  (GetLodList)
    Regex `_(High|LOD\\d+)\\.` -- o token vem logo ANTES da extensao.
    Sem nenhum, o HDA trata como sem LOD.

TIPO PLANT  (GetAssetScanDict)
    Se QUALQUER arquivo da pasta tiver 'translucency' no nome, o asset e'
    marcado como TYPE='PLANT', e os builders de material ligam o caminho de
    folha. E' o unico gatilho -- nao ha outra forma de marcar.

TEXTURAS
    Reconhecidas por sufixo no nome. Os sufixos sao parametros do HDA; abaixo
    estao os defaults. O que importa pra nos e' terminar o nome com um deles.
"""
import re

# Sufixos default do HDA (GetImageTypeList + os parametros *_Extention).
# A ordem importa em um ponto: 'basecolor'/'albedo'/'diffuse' sao alternativos
# para a cor base, e o HDA usa o ULTIMO que encontrar.
TEXTURE_SUFFIXES = [
    "ao", "basecolor", "diffuse", "albedo", "specular", "metalness",
    "roughness", "gloss", "bump", "opacity", "normal", "displacement",
    "translucency", "transmission", "fuzz", "cavity", "curvature",
]

# O gatilho de PLANT. Deliberadamente separado da lista acima: e' a unica
# string cujo efeito vai alem de virar um mapa.
PLANT_TRIGGER = "translucency"

VARIANT_RE = re.compile(r"(Var[A-Z]|Var\d+)_", re.I)
LOD_RE = re.compile(r"_(High|LOD\d+)\.", re.I)

DEFAULT_LOD = "High"


def sanitize(name):
    """Nome seguro para pasta/arquivo, preservando o que o HDA usa pra casar."""
    out = "".join(c if (c.isalnum() or c in "_-") else "_" for c in str(name))
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_") or "unnamed"


def variant_token(index, style="letter"):
    """VarA, VarB... ou Var1, Var2... a partir de um indice 0-based."""
    if style == "number":
        return "Var%d" % (index + 1)
    letras = ""
    n = index
    while True:
        letras = chr(ord("A") + n % 26) + letras
        n = n // 26 - 1
        if n < 0:
            break
    return "Var" + letras


def geo_filename(asset, variant=None, lod=DEFAULT_LOD, ext="fbx"):
    """Nome do arquivo de geometria na convencao do HDA.

    O token de LOD tem que ficar colado na extensao -- o regex do HDA e'
    `_(High|LOD\\d+)\\.`, entao `_High` no meio do nome nao e' visto.
    """
    partes = [sanitize(asset)]
    if variant:
        partes.append(sanitize(variant))
    nome = "_".join(partes)
    if lod:
        nome += "_" + sanitize(lod)
    return "%s.%s" % (nome, ext)


def texture_filename(asset, suffix, ext="png", variant=None):
    """<asset>[_<variant>]_<suffix>.<ext>"""
    partes = [sanitize(asset)]
    if variant:
        partes.append(sanitize(variant))
    partes.append(sanitize(suffix).lower())
    return "%s.%s" % ("_".join(partes), ext)


def asset_dir(root, asset):
    """A pasta do asset. E' ela que o HDA reconhece como raiz."""
    return "%s/%s" % (str(root).replace("\\", "/").rstrip("/"), sanitize(asset))


def variant_dir(root, asset, variant):
    """Subpasta de variante. Usar SO' quando houver mais de uma variante --
    com uma so', o arquivo fica direto na pasta do asset e o HDA assume
    'Var1' sozinho."""
    return "%s/%s" % (asset_dir(root, asset), sanitize(variant))


# --------------------------------------------------------------------------
# leitura de volta: util para conferir o que ja existe em disco
# --------------------------------------------------------------------------

def parse_variant(path):
    m = VARIANT_RE.search(str(path).replace("\\", "/"))
    if not m:
        return None
    t = m.group(1)
    return t[:3].title() + t[3:].upper()


def parse_lod(path):
    m = LOD_RE.search(str(path).replace("\\", "/"))
    return m.group(1) if m else None


def looks_like_plant(filenames):
    """O mesmo teste que o HDA faz para marcar TYPE='PLANT'."""
    return any(PLANT_TRIGGER in str(f).lower() for f in filenames)


def texture_suffix_of(filename):
    """Qual sufixo de textura o HDA reconheceria neste nome, se algum.

    Casa do mais longo pro mais curto: 'basecolor' antes de 'color' evitaria
    um falso positivo se a lista crescer nessa direcao.
    """
    base = str(filename).rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
    for suf in sorted(TEXTURE_SUFFIXES, key=len, reverse=True):
        if base.endswith("_" + suf) or ("_" + suf + "_") in base:
            return suf
    return None
