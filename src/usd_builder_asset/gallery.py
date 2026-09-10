"""Thumbnail + Asset Gallery, em cima do utilitario OFICIAL da SideFX.

`husd.assetutils.AssetGallery` e' o que a propria Layout Asset Gallery usa:
  - addAsset(usd, ...): poe no banco e, se nao ha' thumbnail, RENDERIZA um
    (processo externo, funciona headless).
  - variant_sets=["mtl"]: cada variante (dark/light) vira um tile proprio
    na gallery, com a selecao de variante automatica ao instanciar --
    exatamente o esquema do KB3D_Converter.
  - renderThumbnailForAsset(usd, png): so' o thumbnail.

Dedup por nome ANTES de inserir (o video conserta duplicados depois, no
DB Browser; aqui nao deixamos entrar).

Para ver no Houdini: pane Layout Asset Gallery -> Data Source -> o .db.
"""
import os

import hou


def _gal(db_path):
    from husd import assetutils
    return assetutils.AssetGallery(str(db_path).replace("\\", "/"))


def thumbnail(usd_path, png_path=None):
    """Renderiza o thumbnail de um asset USD (karma, processo externo).

    Devolve o caminho do png ou None.
    """
    usd_path = str(usd_path).replace("\\", "/")
    if png_path is None:
        png_path = os.path.join(os.path.dirname(usd_path),
                                "thumbnail.png").replace("\\", "/")
    try:
        _gal(None).renderThumbnailForAsset(usd_path, png_path)
    except Exception:
        return None
    return png_path if os.path.isfile(png_path) else None


def _nomes_existentes(db_path):
    """Nomes-BASE ja no banco. Um asset com variantes entra como
    'Nome (dark)' / 'Nome (light)' -- o dedup compara sem o sufixo."""
    try:
        ds = hou.AssetGalleryDataSource(str(db_path).replace("\\", "/"))
        return {ds.label(i).split(" (")[0] for i in ds.itemIds()}
    except Exception:
        return set()


def registrar(db_path, nome, usd_path, thumb_png=None, variant_set=None):
    """Um asset no banco. Devolve 'novo' ou 'ja existia'."""
    novos, _d = registrar_lote(db_path, [(nome, usd_path, thumb_png)],
                               variant_set=variant_set)
    return "novo" if novos else "ja existia"


def registrar_lote(db_path, itens, variant_set=None):
    """Registra varios (nome, usd, png). Devolve (novos, dups).

    variant_set: nome do variantSet ("mtl") para abrir cada variante num
    tile proprio. Sem thumbnail pronto o addAsset RENDERIZA um -- num lote
    grande isso pesa; gere antes (--thumbs) ou aceite a espera.
    """
    gal = _gal(db_path)
    existentes = _nomes_existentes(db_path)
    novos = dups = 0
    for nome, usd_path, thumb_png in itens:
        if nome in existentes:
            dups += 1
            continue
        gal.addAsset(str(usd_path).replace("\\", "/"),
                     thumbnail_file_path=(str(thumb_png).replace("\\", "/")
                                          if thumb_png else None),
                     asset_name=nome,
                     variant_sets=([variant_set] if variant_set else []))
        existentes.add(nome)
        novos += 1
    return novos, dups
