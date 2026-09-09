"""Le uma pasta de asset e diz o que ela e'.

Sem dependencia de Max nem de Houdini -- stdlib pura, para poder ser testada
contra pastas reais sem abrir nada.

POR QUE ISSO EXISTE
    "Importar um asset" e' uma frase que esconde tres coisas diferentes:
    um Maxtree tem uma dezena de materiais por planta, cada um com seu jogo
    de mapas; um Megascans tem UM material e seis LODs; um kitbash costuma
    ter varios objetos que compartilham um atlas. Um builder que trata os
    tres igual acerta um e erra dois.

    Entao o scanner nao adivinha na hora de montar: ele classifica antes, e
    o builder pergunta.

O QUE E' UMA "PARTE"
    O agrupamento de texturas por material. A regra e' generica: tira o
    sufixo de papel do nome e o que sobra e' a parte.

        MT_PM_V93_Zea_mays_01_Bud_01_albedo.jpg -> MT_PM_V93_..._Bud_01
        wjuvdeyqx_8K_Albedo.jpg                 -> wjuvdeyqx

    Funciona para os dois sem regra especifica de biblioteca. Tokens de
    resolucao (_8K, _4K) e de LOD sao removidos antes, senao o Megascans
    viraria uma parte por resolucao.
"""
import json
import os
import re

from . import naming

# Bibliotecas que sabemos reconhecer.
MAXTREE = "maxtree"
MEGASCANS = "megascans"
KITBASH = "kitbash"
DESCONHECIDA = "desconhecida"

_RES_RE = re.compile(r"_\d+k(?=_|$)", re.I)          # _8K, _4K
_LODTOK_RE = re.compile(r"_(?:lod\d+|high)(?=_|$)", re.I)
_GEO_EXT = (".fbx", ".abc", ".obj", ".bgeo", ".usd", ".usdc", ".usda")
_IMG_EXT = (".jpg", ".jpeg", ".png", ".exr", ".tif", ".tiff", ".tga")

# Quando o mesmo papel aparece em dois formatos -- o Megascans entrega
# Displacement em .exr E .jpg -- ficar com o que o listdir devolveu primeiro
# jogaria fora os 16/32 bits sem avisar. Maior numero ganha.
_FORMATO_PESO = {".exr": 4, ".tif": 3, ".tiff": 3, ".png": 2,
                 ".tga": 2, ".jpg": 1, ".jpeg": 1}


def _peso(caminho):
    return _FORMATO_PESO.get(os.path.splitext(str(caminho))[1].lower(), 0)


class Asset(object):
    """O que um builder precisa saber antes de montar qualquer coisa."""

    def __init__(self, root):
        self.root = str(root).replace("\\", "/").rstrip("/")
        self.name = os.path.basename(self.root)
        self.library = DESCONHECIDA
        self.plant = False
        self.geometry = {}      # lod -> caminho
        self.parts = {}         # parte -> {papel: caminho}
        self.preview = None
        self.meta = {}          # metadados da biblioteca, se houver
        self.avisos = []

    # -- derivados -------------------------------------------------------

    @property
    def lods(self):
        return sorted(self.geometry.keys(), key=_lod_key)

    @property
    def default_geo(self):
        """A geometria de maior resolucao: High se existir, senao o menor LOD."""
        if not self.geometry:
            return None
        return self.geometry[self.lods[0]]

    @property
    def is_multi_material(self):
        return len(self.parts) > 1

    def roles(self):
        out = set()
        for mapas in self.parts.values():
            out.update(mapas.keys())
        return sorted(out)

    def to_dict(self):
        return {
            "name": self.name, "root": self.root, "library": self.library,
            "plant": self.plant, "geometry": self.geometry,
            "parts": self.parts, "preview": self.preview,
            "lods": self.lods, "roles": self.roles(),
            "multi_material": self.is_multi_material,
            "avisos": self.avisos,
        }

    def resumo(self):
        linhas = [
            "%s  [%s]" % (self.name, self.library),
            "   geometria : %s" % (", ".join(self.lods) or "(nenhuma)"),
            "   materiais : %d" % len(self.parts),
            "   papeis    : %s" % (", ".join(self.roles()) or "(nenhum)"),
            "   planta    : %s" % ("sim" if self.plant else "nao"),
        ]
        if self.preview:
            linhas.append("   preview   : %s" % os.path.basename(self.preview))
        for a in self.avisos:
            linhas.append("   ! %s" % a)
        return "\n".join(linhas)


# --------------------------------------------------------------------------

def _lod_key(lod):
    """High primeiro, depois LOD0, LOD1... e o resto no fim."""
    l = str(lod).lower()
    if l == "high":
        return (0, 0)
    m = re.match(r"lod(\d+)$", l)
    return (1, int(m.group(1))) if m else (2, 0)


def _part_name(filename):
    """Nome do arquivo sem o sufixo de papel, resolucao e LOD."""
    base = os.path.basename(str(filename)).rsplit(".", 1)[0]
    suf = naming.texture_suffix_of(base)
    if suf:
        low = base.lower()
        i = low.rfind("_" + suf)
        if i >= 0:
            base = base[:i] + base[i + len(suf) + 1:]
    base = _RES_RE.sub("", base)
    base = _LODTOK_RE.sub("", base)
    return base.strip("_") or "default"


def scan(root):
    """Le a pasta e devolve um Asset."""
    a = Asset(root)
    if not os.path.isdir(a.root):
        a.avisos.append("pasta nao existe")
        return a

    arquivos = [f for f in os.listdir(a.root)
                if os.path.isfile(os.path.join(a.root, f))]

    for f in arquivos:
        cheio = "%s/%s" % (a.root, f)
        low = f.lower()

        if low.endswith(_GEO_EXT):
            lod = naming.parse_lod(f) or naming.DEFAULT_LOD
            if lod in a.geometry:
                a.avisos.append("mais de uma geometria para o LOD %s; fiquei "
                                "com %s" % (lod, os.path.basename(a.geometry[lod])))
                continue
            a.geometry[lod] = cheio
            continue

        if low.endswith(_IMG_EXT):
            if naming.is_preview(f):
                a.preview = a.preview or cheio
                continue
            papel = naming.texture_role(f)
            if papel is None:
                a.avisos.append("mapa nao reconhecido: %s" % f)
                continue
            parte = _part_name(f)
            a.parts.setdefault(parte, {})
            atual = a.parts[parte].get(papel)
            if atual is not None and _peso(atual) >= _peso(cheio):
                continue     # ja temos um formato igual ou melhor
            a.parts[parte][papel] = cheio
            continue

        if low.endswith(".json"):
            try:
                with open(cheio, "r", encoding="utf-8") as fh:
                    dados = json.load(fh)
                if isinstance(dados, dict):
                    a.meta[f] = dados
            except Exception:
                pass

    a.plant = naming.looks_like_plant(arquivos)
    a.library = classify(a, arquivos)

    if not a.geometry:
        a.avisos.append("nenhuma geometria na pasta")
    if not a.parts:
        a.avisos.append("nenhuma textura reconhecida -- o builder nao vai ter "
                        "com que montar material")
    return a


def classify(asset, arquivos):
    """Qual biblioteca produziu este asset.

    Assinaturas que checamos, em ordem de confianca. Cada uma foi conferida
    contra uma pasta real; nao ha regra inventada aqui. Kitbash ainda nao tem
    amostra, entao nao ha deteccao -- e' melhor cair em 'desconhecida' e
    dizer isso do que classificar errado.
    """
    nomes = [f.lower() for f in arquivos]

    # Megascans: token de resolucao nos mapas (_8K_, _4K_) mais LOD na
    # geometria ou um <id>_Preview.png. Nao exigimos .fbx: metade da
    # biblioteca vem em .abc, e foi assim que essa regra falhou da primeira
    # vez. Nem exigimos __meta.json, que so' alguns assets trazem.
    tem_meta = any(n.endswith("__meta.json") for n in nomes)
    tem_res = any(_RES_RE.search(n) for n in nomes)
    tem_lod_geo = any(re.search(r"_lod\d+\.(?:%s)$" % "|".join(
        e.lstrip(".") for e in _GEO_EXT), n) for n in nomes)
    tem_preview = any(n.endswith("_preview.png") for n in nomes)
    if tem_meta or (tem_res and (tem_lod_geo or tem_preview)):
        return MEGASCANS

    # Maxtree: prefixo MT_ nos arquivos, e um jogo de mapas por parte.
    if any(n.startswith("mt_") for n in nomes):
        return MAXTREE

    return DESCONHECIDA


def scan_many(root):
    """Varre uma pasta de pastas. Devolve [Asset] ordenado por nome."""
    root = str(root).replace("\\", "/").rstrip("/")
    if not os.path.isdir(root):
        return []
    achados = []
    for nome in sorted(os.listdir(root)):
        sub = os.path.join(root, nome)
        if os.path.isdir(sub):
            a = scan(sub)
            if a.geometry or a.parts:
                achados.append(a)
    return achados
