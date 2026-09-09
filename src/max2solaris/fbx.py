"""O que o FBX entrega dentro do Houdini, e como ler isso.

Duas perguntas decidem o builder inteiro, e as duas foram MEDIDAS com
`tools/probe_fbx.py` nos FBX reais do Matheus -- nao supostas.

1. COMO VEM A ATRIBUICAO DE MATERIAL
   Atributo de primitiva `shop_materialpath`. Nao ha grupos, nao ha subsets.

   E o achado que simplifica tudo: os nomes batem EXATAMENTE com os nomes de
   parte que o scanner extrai das texturas.

       Maxtree   6 materiais no FBX, 6 casaram, 0 divergiram
       KitBash  28 materiais no FBX, 28 casaram, 0 divergiram

   Ou seja: bind direto, sem tabela de traducao por biblioteca.

2. COMO SEPARAR VARIOS ASSETS DE UM ARQUIVO SO'
   Atributo de primitiva `name`, com o caminho da hierarquia:

       KB3D_LNB_Antenna_A_grp/KB3D_LNB_Antenna_A_Main

   O primeiro componente, sem o sufixo `_grp`, e' o asset. Conferido contra
   as 79 pastas que o Matheus ja tinha construido: casou 100% da amostra.

   O Maxtree cai no mesmo codigo e da' um asset so' -- o `name` la' e'
   `MT_PM_V93_Zea_mays_01_04`, sem barra. Nao ha caso especial.
"""
import os

#: Sufixos de agrupamento que os pacotes usam no no pai.
_SUFIXOS_GRUPO = ("_grp", "_group", "_geo", "_grp1")

#: Atributos de primitiva que carregam a atribuicao de material, em ordem de
#: preferencia. O primeiro que existir na geometria vence.
ATTR_MATERIAL = ("shop_materialpath", "usdmaterialpath", "material_override")

#: Atributo com o caminho da hierarquia.
ATTR_NAME = "name"


def asset_key(name_value):
    """O nome do asset a partir de um valor do atributo `name`.

    'KB3D_LNB_Antenna_A_grp/KB3D_LNB_Antenna_A_Main' -> 'KB3D_LNB_Antenna_A'
    'MT_PM_V93_Zea_mays_01_04'                       -> 'MT_PM_V93_Zea_mays_01_04'
    """
    primeiro = str(name_value).replace("\\", "/").split("/")[0].strip()
    baixo = primeiro.lower()
    for suf in _SUFIXOS_GRUPO:
        if baixo.endswith(suf):
            return primeiro[:-len(suf)]
    return primeiro


def material_key(material_value):
    """O nome de parte a partir de um valor de `shop_materialpath`.

    O FBX pode trazer o material como caminho ('/mat/KB3D_LNB_Cable') ou
    como nome puro. Ficamos com o ultimo componente, que e' o que casa com o
    nome de parte das texturas.
    """
    return str(material_value).replace("\\", "/").rstrip("/").split("/")[-1]


def group_by_asset(name_values):
    """{asset: [valores de name]} -- a base do passo `split_objects`."""
    grupos = {}
    for v in name_values:
        grupos.setdefault(asset_key(v), []).append(v)
    return grupos


def cross_check(material_values, parts):
    """Confere os materiais do FBX contra as partes que o scanner achou.

    Devolve (casaram, so_no_fbx, so_nas_texturas). O builder deve reclamar de
    `so_no_fbx`: material na geometria sem textura nenhuma vira superficie
    cinza no render, e isso passa despercebido num lote grande.
    """
    mats = {material_key(m) for m in material_values if str(m).strip()}
    p = set(parts)
    return sorted(mats & p), sorted(mats - p), sorted(p - mats)


# --------------------------------------------------------------------------
# leitura da geometria (so' funciona dentro do Houdini)
# --------------------------------------------------------------------------

def read_geo(geometry):
    """Le um hou.Geometry e devolve o que o builder precisa.

    Isolado numa funcao para que o resto do modulo continue testavel sem
    Houdini -- as regras acima sao string, nao geometria.
    """
    def strings(nome):
        a = geometry.findPrimAttrib(nome)
        if a is None:
            return []
        try:
            return sorted(set(a.strings()))
        except Exception:
            return []

    materiais = []
    attr_usado = None
    for cand in ATTR_MATERIAL:
        materiais = strings(cand)
        if materiais:
            attr_usado = cand
            break

    nomes = strings(ATTR_NAME)
    return {
        "attr_material": attr_usado,
        "materiais": materiais,
        "nomes": nomes,
        "assets": group_by_asset(nomes),
    }


def load_sop(parent, caminho, nome="fbx_in"):
    """File SOP lendo o FBX. E' o que vai dentro de um componentgeometry.

    O File SOP le .fbx direto -- nao precisa do importador de FBX que cria
    uma arvore de objetos em /obj, e que traria os nulls e transforms que o
    HDA do Carlo chamava de 'FBX clutter'.
    """
    n = parent.createNode("file", nome)
    n.parm("file").set(str(caminho).replace("\\", "/"))
    return n


def asset_dirname(caminho_fbx):
    return os.path.basename(os.path.dirname(str(caminho_fbx)))
