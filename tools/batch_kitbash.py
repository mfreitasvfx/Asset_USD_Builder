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

sys.path.insert(0, r"C:/dev/USD_Builder_Asset/src")

import hou                                            # noqa: E402
from usd_builder_asset import library, profiles             # noqa: E402
from usd_builder_asset.lops import builder                  # noqa: E402


# a logica do atlas mora na library (a janela usa a mesma)
atlas_material = library.atlas_material


def natural(p):
    m = re.search(r"(\d+)\.fbx$", p.lower())
    return (int(m.group(1)) if m else 1 << 30, p.lower())


def _paralelo(a):
    """Multiprocesso: N hythons, cada um com a fatia i::N dos arquivos.

    Processo (nao thread): o hou nao e' thread-safe para builds paralelos,
    e processos separados ainda contornam o acumulo de memoria que
    derrubou o lote de 819 assets numa sessao so'.
    """
    import subprocess
    logs = []
    procs = []
    if not os.path.isdir(a.saida):
        os.makedirs(a.saida)
    base = [sys.executable, os.path.abspath(__file__), a.raiz, a.saida,
            "--variant", a.variant, "--renderers", a.renderers,
            "--tex-mode", a.tex_mode, "--jobs", "1",
            "--disp-scale", str(a.disp_scale),
            "--basecolor-gamma", str(a.basecolor_gamma),
            "--normal-scale", str(a.normal_scale),
            "--subsurface", str(a.subsurface)]
    if a.limit:
        base += ["--limit", str(a.limit)]
    if a.no_proxy:
        base.append("--no-proxy")
    if a.no_simproxy:
        base.append("--no-simproxy")
    if a.no_center:
        base.append("--no-center")
    if a.unit_scale is not None:
        base += ["--unit-scale", str(a.unit_scale)]
    if a.thumbs:
        base.append("--thumbs")
    if a.tex_renderman:
        base.append("--tex-renderman")
    # --gallery NAO desce para os workers: o pai registra tudo no final,
    # senao N processos brigam pelo mesmo SQLite
    for i in range(a.jobs):
        log = os.path.join(a.saida, "_log_worker_%d.txt" % i)
        logs.append(log)
        fh = open(log, "w")
        procs.append((subprocess.Popen(
            base + ["--slice", "%d:%d" % (i, a.jobs)],
            stdout=fh, stderr=subprocess.STDOUT), fh))
        print("worker %d/%d -> %s" % (i + 1, a.jobs, log))
    ret = 0
    for i, (p, fh) in enumerate(procs):
        p.wait()
        fh.close()
        ret |= p.returncode
        with open(logs[i]) as f:
            fim = f.read().strip().splitlines()[-4:]
        print("worker %d saiu com %d:" % (i, p.returncode))
        for ln in fim:
            print("   ", ln)
    if a.gallery:
        _gallery_pass(a.saida, "mtl" if a.variant == "both" else None)
    return ret


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
    ap.add_argument("--tex-mode", default="shared",
                    choices=["shared", "copy"],
                    help="shared = UMA copia do atlas em <saida>/textures "
                         "(o localize por asset deu 100 GB no set inteiro, "
                         "medido); copy = comportamento antigo")
    ap.add_argument("--jobs", type=int, default=1,
                    help="processos hython em paralelo, cada um com uma "
                         "fatia dos arquivos")
    ap.add_argument("--slice", default=None, help=argparse.SUPPRESS)
    # settings do Asset_USD_Builder
    ap.add_argument("--disp-scale", type=float, default=0.01)
    ap.add_argument("--basecolor-gamma", type=float, default=1.0)
    ap.add_argument("--normal-scale", type=float, default=1.0)
    ap.add_argument("--subsurface", type=float, default=1.0)
    ap.add_argument("--gallery", action="store_true",
                    help="registra os assets em <saida>/asset_gallery.db "
                         "ao final (um escritor so', com dedup)")
    ap.add_argument("--tex-renderman", action="store_true",
                    help="converte mapas p/ .tex ACEScg no material RenderMan "
                         "(a etapa do Asset_USD_Builder)")
    ap.add_argument("--thumbs", action="store_true",
                    help="gera thumbnail.png por asset (render karma -- "
                         "LENTO num set grande)")
    a = ap.parse_args()

    if a.jobs > 1 and a.slice is None:
        return _paralelo(a)

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
    if a.slice:
        idx, n = (int(x) for x in a.slice.split(":"))
        fbxs = fbxs[idx::n]
    print("arquivos :", len(fbxs))

    tex_dir = None
    if a.tex_mode == "shared":
        tex_dir = os.path.join(a.saida, "textures").replace("\\", "/")
    settings = {"basecolor_gamma": a.basecolor_gamma,
                "normal_scale": a.normal_scale,
                "subsurface": a.subsurface,
                "tex_renderman": a.tex_renderman}

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
                    variants=variantes, tex_dir=tex_dir, cleanup=True,
                    disp_scale=a.disp_scale, settings=settings,
                    thumb=a.thumbs)
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

    # gallery so' no processo "dono" (sem --slice): um escritor no SQLite
    if a.gallery and a.slice is None:
        _gallery_pass(a.saida, "mtl" if a.variant == "both" else None)
    return 1 if falhas else 0


def _gallery_pass(saida, variant_set=None):
    from usd_builder_asset import gallery
    db = os.path.join(saida, "asset_gallery.db").replace("\\", "/")
    itens = []
    for pasta in sorted(os.listdir(saida)):
        d = os.path.join(saida, pasta)
        usd = os.path.join(d, pasta + ".usd")
        if not os.path.isfile(usd):
            continue
        png = os.path.join(d, "thumbnail.png")
        itens.append((pasta, usd, png if os.path.isfile(png) else None))
    novos, dups = gallery.registrar_lote(db, itens, variant_set=variant_set)
    print("asset gallery: %d novos, %d ja existiam -> %s"
          % (novos, dups, db))


if __name__ == "__main__":
    sys.exit(main())
