"""Lote de um kitbash multi-FBX com atlas compartilhado -> um USD por asset.

    hython tools/batch_kitbash.py <raiz_do_set> <saida> [opcoes]

    --limit N            para depois de N arquivos (teste rapido)
    --variant dark|light escolhe o basecolor do atlas (default: dark)
    --renderers a,b      default: vray,karma  ("vamos ficar no vray")

Feito para o formato do Post Apocalypse Survivor Environment (o set do video
"Import KitBash using TOPs" do Arcanacom):

    <raiz>/FBX/FBX/1.fbx .. 64.fbx    um asset por arquivo, nomeado pelo
                                      objeto de topo (Building_01, ...)
    <raiz>/Textures/                  UM atlas para o set inteiro, com
                                      basecolor em duas variantes (dark/light)

Aqui o shop_materialpath do FBX e' lixo ('01 - Default'), entao nao ha
casamento por nome: o lote monta UM material a partir do atlas -- igual ao
'Default' unico do hip do video -- e o builder binda no asset inteiro.
"""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, r"C:/dev/max2solaris/src")

import hou                                            # noqa: E402
from max2solaris import library, profiles             # noqa: E402
from max2solaris.lops import builder                  # noqa: E402


def atlas_material(asset, variant="dark"):
    """Monta o jogo de mapas unico a partir do que o scan achou no set.

    O scanner fragmenta 'X_color_dark'/'X_color_light' em partes separadas
    (dark/light) e deixa os mapas de dado na parte base. Aqui juntamos:
    basecolor da variante pedida + todos os mapas de dado.
    """
    mapas = {}
    basecolor = None
    for parte, m in asset.parts.items():
        low = parte.lower()
        if low.endswith("_" + variant) and "basecolor" in m:
            basecolor = m["basecolor"]
            continue
        if low.endswith("_dark") or low.endswith("_light"):
            continue                       # a outra variante
        mapas.update(m)
    if basecolor:
        mapas["basecolor"] = basecolor
    nome = "%s_%s" % (asset.name, variant)
    return nome, mapas


def natural(p):
    m = re.search(r"(\d+)\.fbx$", p.lower())
    return (int(m.group(1)) if m else 1 << 30, p.lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raiz")
    ap.add_argument("saida")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--variant", default="both",
                    choices=["both", "dark", "light"],
                    help="both = variantes USD dark+light no mesmo asset "
                         "(esquema KB3D_Converter_2.0)")
    ap.add_argument("--renderers", default="vray,karma")
    # modos: a ferramenta e' adaptativa -- o usuario escolhe como operar
    ap.add_argument("--no-proxy", action="store_true")
    ap.add_argument("--no-simproxy", action="store_true")
    ap.add_argument("--no-center", action="store_true")
    ap.add_argument("--unit-scale", type=float, default=None)
    a = ap.parse_args()

    renderers = tuple(r.strip() for r in a.renderers.split(",") if r.strip())

    asset = library.scan(a.raiz)
    over = {}
    if a.no_proxy: over["proxy"] = False
    if a.no_simproxy: over["simproxy"] = False
    if a.no_center: over["center"] = False
    if a.unit_scale is not None: over["unit_scale"] = a.unit_scale
    perfil = profiles.custom("kitbash", **over)   # o set nao tem marca KB3D
    if a.variant == "both":
        variantes = []
        for v in ("dark", "light"):
            nome_v, mapas_v = atlas_material(asset, v)
            if mapas_v:
                variantes.append((v, {nome_v: mapas_v}))
        if not variantes:
            print("ERRO: nenhum mapa montado do atlas")
            return 1
        mat_nome, mapas = None, None
        print("set      :", asset.name)
        print("variantes:", [v for v, _ in variantes])
    else:
        variantes = None
        mat_nome, mapas = atlas_material(asset, a.variant)
        print("set      :", asset.name)
        print("material :", mat_nome, "->", sorted(mapas))
        if not mapas:
            print("ERRO: nenhum mapa montado do atlas")
            return 1
    print("renderers:", renderers)

    fbxs = sorted(glob.glob(os.path.join(a.raiz, "FBX", "FBX", "*.fbx")),
                  key=natural)
    if not fbxs:
        fbxs = sorted(glob.glob(os.path.join(a.raiz, "**", "*.fbx"),
                                recursive=True), key=natural)
    if a.limit:
        fbxs = fbxs[:a.limit]
    print("arquivos :", len(fbxs))

    ok, falhas = [], []
    cache_dir = os.path.join(a.saida, "_bgeo_cache")
    for i, f in enumerate(fbxs, 1):
        try:
            tops = builder.list_assets_in_file(f)
        except Exception as e:
            falhas.append((f, "listagem: %s" % e))
            continue
        fonte = f
        if len(tops) > 1:
            # o passo GenerateBGEO do video: um arquivo de props recarregado
            # uma vez por prop mataria o lote -- converte pra bgeo uma vez
            try:
                fonte = builder.cache_bgeo(f, cache_dir)
                print("[%d/%d] %s -> bgeo (%d props)"
                      % (i, len(fbxs), os.path.basename(f), len(tops)))
            except Exception as e:
                print("   cache bgeo falhou (%s); seguindo com o fbx" % e)
        for top in tops:
            print("\n[%d/%d] %s :: %s" % (i, len(fbxs),
                                          os.path.basename(f), top))
            try:
                res = builder.build_asset(
                    asset, perfil, out_dir=a.saida, asset_name=top,
                    renderers=renderers, geo_path=fonte,
                    parts=({mat_nome: mapas} if variantes is None else None),
                    variants=variantes)
                print(res.resumo())
                if res.usd_path and os.path.isfile(res.usd_path):
                    ok.append(res.usd_path)
                else:
                    falhas.append((f, top))
            except Exception as e:
                import traceback
                traceback.print_exc()
                falhas.append((f, "%s: %s" % (top, e)))

    print("\n" + "=" * 60)
    print("ok: %d | falhou: %d" % (len(ok), len(falhas)))
    for f in falhas[:10]:
        print("   ", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
