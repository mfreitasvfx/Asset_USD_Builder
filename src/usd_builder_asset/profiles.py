"""Perfis de importacao: um por biblioteca, cada um com seu toolset.

O scanner (`library.py`) diz O QUE a pasta e'. O perfil diz O QUE FAZER com
ela. Sao coisas separadas de proposito: reconhecer um Megascans e decidir
como monta-lo mudam por motivos diferentes e em ritmos diferentes.

Um perfil e' quase todo declarativo. Isso e' escolha, nao preguica: quando
chegar a proxima biblioteca, acrescentar um perfil deve ser preencher uma
tabela, nao escrever codigo novo. So' o que e' genuinamente comportamento
(`steps`) fica como lista de etapas nomeadas.

O QUE CADA CAMPO DECIDE
    lod_policy       quais LODs viram variantes no USD
    asset_grain      'folder'  -> a pasta e' um asset
                     'object'  -> o arquivo tem varios objetos e cada um
                                  vira um asset (KitBash)
    rough_source     de onde sai a rugosidade: ja e' roughness, ou e'
                     glossiness e precisa inverter (Maxtree, Megascans)
    plant_workflow   liga o caminho de folha (thin-walled + SSS)
    steps            o toolset, em ordem
"""
from . import library as _lib

# Etapas conhecidas. Nomes, nao funcoes -- quem executa e' o builder, e assim
# um perfil pode ser lido e conferido sem importar Houdini.
PASSO_SCAN = "scan"                    # ler a pasta
PASSO_SPLIT = "split_objects"          # separar objetos de um arquivo unico
PASSO_GEO = "component_geometry"       # importar geometria (por LOD/variante)
PASSO_MATS = "build_materials"         # um material por parte
PASSO_BIND = "bind_materials"          # ligar material a subset/objeto
PASSO_PLANT = "leaf_shading"           # thin-walled + SSS nas folhas
PASSO_OUT = "component_output"         # escrever o USD do asset
PASSO_REF = "reference_existing"       # ja construido: so' referenciar


class Profile(object):

    def __init__(self, key, label, library, steps,
                 lod_policy="all", asset_grain="folder",
                 rough_source="roughness", plant_workflow=False,
                 texture_subdirs=(), notes="",
                 proxy=False, simproxy=False, center=False,
                 unit_scale=0.01, proxy_style="vdb"):
        # unit_scale DEFAULT 0.01 (decisao do Matheus, 2026-09-12): o
        # pipeline exporta em CENTIMETROS (Max, KitBash, Megascans FBX) e
        # o USD e' metros. O Unit Scale da janela (0 = do perfil) sobrepoe.
        self.key = key
        self.label = label
        self.library = library
        self.steps = list(steps)
        self.lod_policy = lod_policy
        self.asset_grain = asset_grain
        self.rough_source = rough_source
        self.plant_workflow = plant_workflow
        self.texture_subdirs = tuple(texture_subdirs)
        self.notes = notes
        # padrao Rebelway do component builder: branch de proxy (GL leve),
        # branch de simproxy (convex hull p/ Edit/Drop LOP) e centralizacao
        # da peca na origem (asset de catalogo, nao layout de set)
        self.proxy = proxy
        self.simproxy = simproxy
        self.center = center
        # fonte em cm (KitBash) -> USD em metros. Medido no A/B: sem isso o
        # asset sai 100x maior que o build de referencia do Matheus.
        self.unit_scale = unit_scale
        # como montar o proxy, os tres setups do teste_proxy.hip, na
        # ordem em que o Matheus os lista na janela:
        #   'lowres' lowres_geo 2% (Maxtree) | 'vdb' VDB+remesh+reduce
        #   (hard surface, default) | 'bounds' caixa por peca (KitBash)
        self.proxy_style = proxy_style

    def lods_for(self, asset):
        """Quais LODs este perfil quer, dado o que a pasta tem."""
        if not asset.geometry:
            return []
        if self.lod_policy == "highest":
            return asset.lods[:1]
        if isinstance(self.lod_policy, (list, tuple)):
            return [l for l in asset.lods if l in self.lod_policy]
        return asset.lods

    def to_dict(self):
        return {"key": self.key, "label": self.label, "library": self.library,
                "steps": self.steps, "lod_policy": self.lod_policy,
                "asset_grain": self.asset_grain,
                "rough_source": self.rough_source,
                "plant_workflow": self.plant_workflow}

    def resumo(self, asset=None):
        linhas = ["perfil: %s" % self.label,
                  "   etapas   : %s" % " -> ".join(self.steps),
                  "   LODs     : %s" % self.lod_policy,
                  "   asset por: %s" % self.asset_grain,
                  "   rugosidade: %s" % self.rough_source]
        if asset is not None:
            linhas.append("   nesta pasta: LODs %s, %d material(is)"
                          % (self.lods_for(asset) or "-", len(asset.parts)))
        if self.notes:
            linhas.append("   nota: %s" % self.notes)
        return "\n".join(linhas)


_BASE = [PASSO_SCAN, PASSO_GEO, PASSO_MATS, PASSO_BIND, PASSO_OUT]


PERFIS = {
    "megascans": Profile(
        "megascans", "Megascans", _lib.MEGASCANS,
        steps=_BASE,
        lod_policy="all",
        asset_grain="folder",
        # O Megascans entrega Gloss em varios packs e Roughness em outros;
        # o scanner ja distingue os dois papeis, entao o builder escolhe.
        rough_source="auto",
        notes="uma pasta = um objeto, 1 material, ate' 7 LODs; metade em .abc",
    ),

    "maxtree": Profile(
        "maxtree", "Maxtree (plantas)", _lib.MAXTREE,
        steps=[PASSO_SCAN, PASSO_GEO, PASSO_MATS, PASSO_PLANT, PASSO_BIND,
               PASSO_OUT],
        lod_policy="highest",
        asset_grain="folder",
        rough_source="glossiness",
        plant_workflow=True,
        # acrescimo de exports pedido pelo Matheus (2026-09-12): proxy com
        # cor aleatoria por asset + simproxy convexo, copiados do hip dele
        proxy=True, simproxy=True, proxy_style="lowres",
        notes="uma planta = uma pasta com ~12 materiais; sem LOD no pacote",
    ),

    "kitbash": Profile(
        "kitbash", "KitBash3D", _lib.KITBASH,
        steps=[PASSO_SCAN, PASSO_SPLIT, PASSO_GEO, PASSO_MATS, PASSO_BIND,
               PASSO_OUT],
        lod_policy="highest",
        # O .fbx do KitBash traz dezenas de objetos nomeados; cada um vira um
        # asset. Quantos sao so' se sabe abrindo o arquivo -- por isso existe
        # a etapa split_objects, e por isso o lote pede TOPs.
        asset_grain="object",
        rough_source="roughness",
        texture_subdirs=("KB3DTextures", "textures"),
        # caixa por peca no proxy, como o Matheus montou no Building_01
        proxy=True, simproxy=True, center=True, unit_scale=0.01,
        proxy_style="bounds",
        notes="um arquivo com dezenas de objetos e um atlas compartilhado",
    ),

    "construido": Profile(
        "construido", "Asset ja construido (Component Builder)", None,
        steps=[PASSO_SCAN, PASSO_REF],
        lod_policy="all",
        notes="tem payload/geo/mtl.usdc: referenciar, nao reconstruir",
    ),

    "generico": Profile(
        "generico", "Generico", _lib.DESCONHECIDA,
        steps=_BASE,
        lod_policy="all",
        rough_source="auto",
        notes="biblioteca nao reconhecida; roda o caminho basico e avisa",
    ),
}


def pick(asset):
    """O perfil para este asset.

    `built` vem antes da biblioteca: uma pasta ja construida do KitBash nao
    deve ser reconstruida so' porque os arquivos dizem KB3D.
    """
    if getattr(asset, "built", False):
        return PERFIS["construido"]
    for p in PERFIS.values():
        if p.library and p.library == asset.library:
            return p
    return PERFIS["generico"]


def plan(asset):
    """O que fazer com este asset: (perfil, etapas, avisos)."""
    p = pick(asset)
    avisos = list(asset.avisos)

    if p.key == "generico":
        avisos.append("biblioteca nao reconhecida -- conferir o resultado a "
                      "mao, ou acrescentar um perfil em profiles.py")
    if p.plant_workflow and not asset.plant:
        avisos.append("perfil de planta, mas nenhum mapa de translucency na "
                      "pasta; o caminho de folha nao vai ter o que ligar")
    if p.asset_grain == "object":
        avisos.append("este pacote tem varios objetos num arquivo so'; a "
                      "separacao acontece em split_objects")
    if p.rough_source == "glossiness" and "glossiness" not in asset.roles():
        avisos.append("perfil espera glossiness e a pasta nao tem")

    return p, p.steps, avisos


def custom(base_key, **over):
    """Um perfil derivado com escolhas do usuario por cima dos defaults.

    E' o mecanismo do 'modo': o perfil da biblioteca da' o ponto de partida,
    e a janela/lote sobrepoe proxy, simproxy, center, unit_scale... A
    ferramenta se adapta; quem decide o modo de operar e' o Matheus.
    """
    base = PERFIS[base_key]
    campos = dict(
        key=base.key + "+custom", label=base.label + " (custom)",
        library=base.library, steps=list(base.steps),
        lod_policy=base.lod_policy, asset_grain=base.asset_grain,
        rough_source=base.rough_source, plant_workflow=base.plant_workflow,
        texture_subdirs=base.texture_subdirs, notes=base.notes,
        proxy=base.proxy, simproxy=base.simproxy, center=base.center,
        unit_scale=base.unit_scale, proxy_style=base.proxy_style)
    campos.update(over)
    return Profile(**campos)
