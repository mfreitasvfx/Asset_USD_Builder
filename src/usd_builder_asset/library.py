"""Le uma pasta de asset e diz o que ela e'.

Sem dependencia de Max nem de Houdini -- stdlib pura, para poder ser testada
contra pastas reais sem abrir nada.

POR QUE ISSO EXISTE
    "Importar um asset" esconde coisas muito diferentes. Medido nas pastas
    reais do Matheus:

      Maxtree    uma planta = uma pasta, 12 materiais, 1 LOD
      Megascans  um objeto = uma pasta, 1 material, 7 LODs, meio deles .abc
      KitBash    UM arquivo com 79 objetos dentro e um atlas de materiais
                 compartilhado numa subpasta

    Um builder que trate os tres igual acerta um e erra dois. Entao o scanner
    classifica antes, e o builder pergunta.

O QUE E' UMA "PARTE"
    O agrupamento de texturas por material. Regra generica: tira o sufixo de
    papel do nome, e o que sobra e' a parte.

        MT_PM_V93_Zea_mays_01_Bud_01_albedo.jpg -> ..._Bud_01
        wjuvdeyqx_8K_Albedo.jpg                 -> wjuvdeyqx
        KB3D_LNB_Cable_basecolor.png            -> KB3D_LNB_Cable

    Serve para as tres bibliotecas sem regra especifica. Tokens de resolucao
    (_8K) e de LOD saem antes, senao o Megascans viraria uma parte por
    resolucao.

ASSET JA CONSTRUIDO
    Uma pasta com payload.usdc + geo.usdc + mtl.usdc e' saida do Component
    Builder do Houdini -- nao e' fonte. O scanner marca `built=True` para o
    builder referenciar em vez de reconstruir.
"""
import json
import os
import re

from . import naming

MAXTREE = "maxtree"
MEGASCANS = "megascans"
KITBASH = "kitbash"
BIGMEDIUMSMALL = "bigmediumsmall"
DESCONHECIDA = "desconhecida"

_RES_RE = re.compile(r"_\d+k(?=_|$)", re.I)              # _8K, _4K
_LODTOK_RE = re.compile(r"_(?:lod\d+|high)(?=_|$)", re.I)
# token final que e' so' FORMATO de imagem: 'CPTaxiRoof_normal_png.png'
# (BigMediumSmall) virava parte falsa 'CPTaxiRoof_png' e a normal ficava
# orfa do material -- medido no pacote cyberpunk
_FMT_RE = re.compile(r"_(?:png|jpe?g|tga|tiff?|exr|bmp)$", re.I)
# rabo de bake do BigMediumSmall: 'vh_cp_glass car_Bake1_PBR_Diffuse.jpg'
# -- o material do FBX se chama 'vh_cp_glass car'; sem tirar _Bake1_PBR a
# parte nao casa com o subset
_BAKE_RE = re.compile(r"_bake\d+(?:_pbr)?$", re.I)
# a mesma marca, mas no MEIO do nome, serve de assinatura da biblioteca
_BAKE_SIG_RE = re.compile(r"_bake\d+_pbr_", re.I)
_GEO_EXT = (".fbx", ".abc", ".obj", ".bgeo", ".usd", ".usdc", ".usda")
_IMG_EXT = (".jpg", ".jpeg", ".png", ".exr", ".tif", ".tiff", ".tga")

# Camadas do Component Builder. Nao sao geometrias alternativas.
# extra.usdc e' opcional -- exigi-la fazia asset construido passar por fonte.
_LAYERS_COMPONENT = {"payload.usdc", "geo.usdc", "mtl.usdc"}
_LAYERS_OPCIONAIS = {"extra.usdc"}

# Subpastas que nunca contem fonte de asset.
_IGNORAR = {"backup", "previews", "thumbs", "thumbnails", "render", "out",
            "__pycache__", ".git"}

# Quando o mesmo papel/geometria aparece em dois formatos -- o Megascans
# entrega Displacement em .exr E .jpg, o KitBash da' .fbx E .obj -- ficar com
# o que o listdir devolveu primeiro descartaria a melhor versao sem avisar.
_PESO_IMG = {".exr": 4, ".tif": 3, ".tiff": 3, ".png": 2, ".tga": 2,
             ".jpg": 1, ".jpeg": 1}
_PESO_GEO = {".usd": 5, ".usdc": 5, ".usda": 5, ".abc": 4, ".fbx": 3,
             ".bgeo": 2, ".obj": 1}


def _ext(p):
    return os.path.splitext(str(p))[1].lower()


def natural_key(p):
    """Ordena '2.fbx' antes de '10.fbx' (numeros como numeros)."""
    nome = os.path.basename(str(p)).lower()
    return [int(t) if t.isdigit() else t
            for t in re.split(r"(\d+)", nome)]


class Asset(object):
    """O que um builder precisa saber antes de montar qualquer coisa."""

    def __init__(self, root):
        self.root = str(root).replace("\\", "/").rstrip("/")
        self.name = os.path.basename(self.root)
        self.library = DESCONHECIDA
        self.plant = False
        self.built = False        # ja e' saida do Component Builder
        self.geometry = {}        # lod -> caminho
        self.geo_files = []       # TODOS os arquivos de geometria achados
        self.parts = {}           # parte -> {papel: caminho}
        self.preview = None
        self.meta = {}
        self.avisos = []

    @property
    def multi_fbx(self):
        """Set multi-arquivo (Post Apocalypse): varios FBX sem token de LOD
        dividindo UM atlas. Cada arquivo carrega seus proprios assets."""
        return len(self.geo_files) > 1 and len(self.geometry) <= 1

    @property
    def lods(self):
        return sorted(self.geometry.keys(), key=_lod_key)

    @property
    def default_geo(self):
        return self.geometry[self.lods[0]] if self.geometry else None

    @property
    def is_multi_material(self):
        return len(self.parts) > 1

    @property
    def multi_material_file(self):
        """Uma geometria so' e varios materiais dentro dela.

        NAO diz quantos objetos ha' no arquivo -- isso so' se sabe abrindo.
        Um Maxtree e' UM objeto com 12 IDs de material; um KitBash sao 79
        objetos compartilhando um atlas. Os dois caem aqui, e quem decide se
        vira um asset ou varios e' o builder, pela biblioteca.
        """
        return len(self.geometry) <= 1 and len(self.parts) > 1

    def roles(self):
        out = set()
        for mapas in self.parts.values():
            out.update(mapas.keys())
        return sorted(out)

    def to_dict(self):
        return {"name": self.name, "root": self.root, "library": self.library,
                "plant": self.plant, "built": self.built,
                "geometry": self.geometry, "parts": self.parts,
                "preview": self.preview, "lods": self.lods,
                "roles": self.roles(),
                "multi_material": self.is_multi_material,
                "multi_material_file": self.multi_material_file,
                "avisos": self.avisos}

    def resumo(self):
        etiquetas = [self.library]
        if self.built:
            etiquetas.append("ja construido")
        if self.multi_material_file:
            etiquetas.append("%d materiais num arquivo" % len(self.parts))
        linhas = [
            "%s  [%s]" % (self.name, ", ".join(etiquetas)),
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


def _lod_key(lod):
    l = str(lod).lower()
    if l == "high":
        return (0, 0)
    m = re.match(r"lod(\d+)$", l)
    return (1, int(m.group(1))) if m else (2, 0)


def _part_name(filename):
    base = os.path.basename(str(filename)).rsplit(".", 1)[0]
    suf = naming.texture_suffix_of(base)
    if suf:
        i = base.lower().rfind("_" + suf)
        if i >= 0:
            base = base[:i] + base[i + len(suf) + 1:]
    base = _LODTOK_RE.sub("", _RES_RE.sub("", base))
    base = _FMT_RE.sub("", base.strip("_"))
    base = _BAKE_RE.sub("", base)
    # espaco no nome de material (BigMediumSmall) vira '_' no prim USD do
    # subset; a parte precisa casar com o subset, entao sanitiza igual
    base = base.replace(" ", "_")
    return base.strip("_") or "default"


def _arquivos(root, profundidade=2):
    """Arquivos da pasta e de subpastas rasas.

    As texturas do KitBash moram em `KB3DTextures/` e as de um asset ja
    construido em `textures/` -- ler so' a raiz perdia todas elas.
    """
    achados = []
    root = root.rstrip("/")
    base_n = root.count("/")
    for atual, dirs, arqs in os.walk(root):
        atual = atual.replace("\\", "/")
        if atual.count("/") - base_n >= profundidade:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d.lower() not in _IGNORAR]
        for a in arqs:
            achados.append((a, atual + "/" + a))
    return achados


def _coleta_imagem(a, nome, cheio, avisar=True):
    if naming.is_preview(nome):
        a.preview = a.preview or cheio
        return
    papel = naming.texture_role(nome)
    if papel is None:
        if avisar:
            a.avisos.append("mapa nao reconhecido: %s" % nome)
        return
    parte = _part_name(nome)
    mapas = a.parts.setdefault(parte, {})
    anterior = mapas.get(papel)
    if anterior is None or _PESO_IMG.get(_ext(cheio), 0) > \
            _PESO_IMG.get(_ext(anterior), 0):
        mapas[papel] = cheio


def _sobe_por_texturas(a, niveis=3):
    """Aponta-se <set>/FBX/FBX e as texturas moram em <set>/Textures
    (Post Apocalypse). Sobe ate `niveis` pais atras de mapas reconheciveis
    -- sem aviso por arquivo, porque na subida aparece de tudo (Icon.jpg,
    Title_*.jpg) e so' interessa o que casa com papel de textura."""
    pai = a.root
    for _ in range(niveis):
        novo = os.path.dirname(pai)
        if not novo or novo == pai or len(novo) <= 3:
            return
        pai = novo
        for nome, cheio in _arquivos(pai, profundidade=2):
            if nome.lower().endswith(_IMG_EXT):
                _coleta_imagem(a, nome, cheio, avisar=False)
        if a.parts:
            a.avisos.append("texturas achadas subindo a arvore: %s"
                            % pai.replace("\\", "/"))
            return


def _texturas_indicadas(a, tex_dir):
    """Pasta de texturas apontada pelo usuario na janela.

    Fallback para pacotes que guardam textura longe da geometria
    (BigMediumSmall: FBX+OBJ/... e as texturas noutra arvore). COMPLEMENTA
    o que o scan da pasta achou: papel ja preenchido so' e' trocado se o
    arquivo novo pesa mais (regra normal do _coleta_imagem)."""
    tex_dir = str(tex_dir).replace("\\", "/").rstrip("/")
    if not os.path.isdir(tex_dir):
        a.avisos.append("pasta de texturas nao existe: %s" % tex_dir)
        return
    antes = set(a.parts)
    for nome, cheio in _arquivos(tex_dir, profundidade=3):
        if nome.lower().endswith(_IMG_EXT):
            _coleta_imagem(a, nome, cheio, avisar=False)
    novas = len(set(a.parts) - antes)
    if novas:
        a.avisos.append("pasta de texturas indicada: %d parte(s) nova(s) "
                        "de %s" % (novas, tex_dir))
    else:
        a.avisos.append("pasta de texturas indicada nao acrescentou parte "
                        "nenhuma: %s" % tex_dir)


def parts_for_file(asset, geo_path):
    """Partes de textura DESTE arquivo de um set multi-FBX, ou None.

    BigMediumSmall: cada FBX traz as texturas EMBUTIDAS, que o Houdini
    extrai para a pasta irma <arquivo>.fbm na primeira importacao. Quando
    ela existe, o veiculo tem materiais proprios e o atlas do set esta'
    ERRADO para ele. Sem .fbm, devolve None e o chamador usa o atlas
    (Post Apocalypse).
    """
    fbm = os.path.splitext(str(geo_path).replace("\\", "/"))[0] + ".fbm"
    if not os.path.isdir(fbm):
        return None
    b = Asset(fbm)
    for nome, cheio in _arquivos(fbm, profundidade=1):
        if nome.lower().endswith(_IMG_EXT):
            _coleta_imagem(b, nome, cheio, avisar=False)
    return b.parts or None


def scan(root, tex_dir=None):
    """Le a pasta e devolve um Asset.

    tex_dir: pasta EXTRA de texturas (campo Textures da janela) -- usada
    quando o pacote nao guarda as texturas junto da geometria.
    """
    a = Asset(root)
    if not os.path.isdir(a.root):
        a.avisos.append("pasta nao existe")
        return a

    arquivos = _arquivos(a.root)
    nomes_raiz = {n.lower() for n, _c in arquivos}
    a.built = _LAYERS_COMPONENT.issubset(nomes_raiz)

    geo_por_lod = {}
    for nome, cheio in arquivos:
        low = nome.lower()

        if low.endswith(_GEO_EXT):
            if a.built and low in (_LAYERS_COMPONENT | _LAYERS_OPCIONAIS):
                continue          # camada, nao geometria alternativa
            a.geo_files.append(cheio)
            lod = naming.parse_lod(nome) or naming.DEFAULT_LOD
            atual = geo_por_lod.get(lod)
            # .fbx e .obj do mesmo asset nao sao conflito: sao formatos do
            # mesmo LOD. Ficamos com o de maior peso, calados.
            if atual is None or _PESO_GEO.get(_ext(cheio), 0) > \
                    _PESO_GEO.get(_ext(atual), 0):
                geo_por_lod[lod] = cheio
            continue

        if low.endswith(_IMG_EXT):
            _coleta_imagem(a, nome, cheio)
            continue

        if low.endswith(".json"):
            try:
                with open(cheio, "r", encoding="utf-8") as fh:
                    dados = json.load(fh)
                if isinstance(dados, dict):
                    a.meta[nome] = dados
            except Exception:
                pass

    a.geometry = geo_por_lod
    a.geo_files.sort(key=natural_key)
    a.plant = naming.looks_like_plant([n for n, _c in arquivos])
    a.library = classify([n for n, _c in arquivos], a.root)

    if a.geometry and not a.parts and not a.built:
        _sobe_por_texturas(a)
    if tex_dir:
        _texturas_indicadas(a, tex_dir)

    if not a.geometry:
        a.avisos.append("nenhuma geometria na pasta")
    if not a.parts and not a.built:
        a.avisos.append("nenhuma textura reconhecida -- nao ha com que montar "
                        "material")
    return a


def atlas_material(asset, variant="light", com_sufixo=False):
    """Junta o jogo de mapas UNICO de um set com atlas compartilhado.

    O scanner fragmenta 'X_color_dark'/'X_color_light' em partes separadas
    e deixa os mapas de dado na parte base. Aqui: basecolor da variante
    pedida + todos os mapas de dado.

    DEFAULT (decisao do Matheus, 2026-09-10): variante LIGHT, nome SEM
    sufixo -- variantes duplicavam na gallery e ele aboliu. O nome do
    material e' a parte-base do atlas (ex.: Post_apocalypse_city);
    com_sufixo=True volta ao nome '<set>_<variante>' (o lote --variant
    both ainda usa).
    """
    mapas = {}
    basecolor = None
    bases = []
    # partes mais LONGAS primeiro: a parte-base (curta) atualiza por
    # ultimo e ganha de arquivos extras deixados na pasta
    for parte, m in sorted(asset.parts.items(),
                           key=lambda kv: -len(kv[0])):
        low = parte.lower()
        if low.endswith("_" + variant) and "basecolor" in m:
            basecolor = m["basecolor"]
            continue
        if low.endswith("_dark") or low.endswith("_light"):
            continue                       # a outra variante
        mapas.update(m)
        bases.append(parte)
    if basecolor:
        mapas["basecolor"] = basecolor
    if com_sufixo:
        nome = "%s_%s" % (asset.name, variant)
    else:
        # a parte-base e' o NOME MAIS CURTO: arquivos extras que o artista
        # deixa na pasta (ex.: *_ACES.png de teste) viram partes mais
        # longas e nao podem batizar o material
        nome = min(bases, key=len) if bases else asset.name
    return nome, mapas


def atlas_variants(asset):
    """[(variante, {nome: mapas})] quando o atlas tem dark/light; None se
    nao ha variantes. NAO e' mais o default da ferramenta (variantes
    duplicavam na gallery; o Matheus aboliu) -- fica para o lote
    --variant both de quem quiser."""
    tem = [v for v in ("dark", "light")
           if any(p.lower().endswith("_" + v) for p in asset.parts)]
    out = []
    for v in tem:
        nome, mapas = atlas_material(asset, v, com_sufixo=True)
        if mapas:
            out.append((v, {nome: mapas}))
    return out or None


def classify(arquivos, root=""):
    """De que biblioteca veio. Cada assinatura foi conferida contra uma pasta
    real; nao ha regra inventada."""
    nomes = [f.lower() for f in arquivos]

    # KitBash: prefixo KB3D_ nos arquivos e nas texturas.
    if any(n.startswith("kb3d_") for n in nomes):
        return KITBASH

    # BigMediumSmall: o nome do pacote no caminho (vale ja' no primeiro
    # scan, antes de existir o .fbm) ou o rabo de bake das texturas
    # embutidas. Importa porque a ESCALA deles e' outra: medido no
    # CP_Vehicles, o carro tem 5.36 unidades = 5,36 m, ja' em metros.
    if "bigmediumsmall" in str(root).lower().replace(" ", "") \
            or any(_BAKE_SIG_RE.search(n) for n in nomes):
        return BIGMEDIUMSMALL

    # Megascans: token de resolucao (_8K_, _4K_) mais LOD na geometria ou um
    # <id>_Preview.png. Nao exigimos .fbx -- metade da biblioteca vem em .abc,
    # e foi assim que essa regra falhou da primeira vez.
    tem_meta = any(n.endswith("__meta.json") for n in nomes)
    tem_res = any(_RES_RE.search(n) for n in nomes)
    exts = "|".join(e.lstrip(".") for e in _GEO_EXT)
    tem_lod_geo = any(re.search(r"_lod\d+\.(?:%s)$" % exts, n) for n in nomes)
    tem_preview = any(n.endswith("_preview.png") for n in nomes)
    if tem_meta or (tem_res and (tem_lod_geo or tem_preview)):
        return MEGASCANS

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
        if os.path.isdir(sub) and nome.lower() not in _IGNORAR:
            a = scan(sub)
            if a.geometry or a.parts:
                achados.append(a)
    return achados
