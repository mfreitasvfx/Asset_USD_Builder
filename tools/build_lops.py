"""Roda o builder em LOPs sem abrir o Houdini.

    hython tools/build_lops.py <pasta_do_asset> [saida] [--object NOME]

E' o loop de iteracao: editar no VS Code -> rodar isto -> ver o resumo.
Nada de reiniciar Houdini; a sessao aberta usa install/houdini_reload.py.
"""
import os
import sys

sys.path.insert(0, r"C:/dev/max2solaris/src")

from max2solaris import library, profiles           # noqa: E402
from max2solaris.lops import builder                # noqa: E402


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not argv:
        print(__doc__)
        return 2
    pasta = argv[0]
    out = argv[1] if len(argv) > 1 else None
    obj = None
    if "--object" in sys.argv:
        obj = sys.argv[sys.argv.index("--object") + 1]

    a = library.scan(pasta)
    p, etapas, avisos = profiles.plan(a)
    print(a.resumo())
    print(p.resumo(a))
    for w in avisos:
        print("   ! %s" % w)
    print()

    if p.key == "construido":
        print("asset ja construido; nada a montar.")
        return 0

    if p.asset_grain == "object" and obj is None:
        nomes = builder.list_assets_in_file(a.default_geo)
        print("%d objetos no arquivo; use --object <nome>. Primeiros:"
              % len(nomes))
        for n in nomes[:10]:
            print("   ", n)
        return 0

    res = builder.build_asset(a, p, out_dir=out, asset_name=obj,
                              renderers=("karma", "arnold", "renderman", "vray"))
    print(res.resumo())
    return 1 if (res.usd_path and not os.path.isfile(res.usd_path)) else 0


if __name__ == "__main__":
    sys.exit(main())
