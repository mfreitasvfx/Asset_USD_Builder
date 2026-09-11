"""Thumbnail + Asset Gallery.

REGISTRO: direto no `hou.AssetGalleryDataSource` (addItem + setThumbnail).
MEDIDO (2026-09-10): o addItem puro persiste e o banco e' INCREMENTAL --
registrar aos poucos ACRESCENTA, nunca reescreve; instancia nova le tudo
de volta. Ja o addAsset do husd.assetutils SEM variantes criava o arquivo
e nao inseria item nenhum (calado) -- e com variantes duplicava tiles.
Como o Matheus aboliu as variantes ("fica a light, sem o nome"), o
caminho simples e' tambem o que funciona.

Dedup por nome ANTES de inserir (o video conserta duplicados depois, no
DB Browser; aqui nao deixamos entrar).

THUMBNAIL: o do export (autothumbnail GL do componentoutput) e' o
preferido; `thumbnail()` renderiza um via assetutils (processo externo,
karma) so' quando nao ha png no disco.

Para ver no Houdini: pane Layout Asset Gallery -> Data Source -> o .db.
"""
import os

import hou


def thumbnail(usd_path, png_path=None):
    """Renderiza o thumbnail de um asset USD (karma, processo externo).

    Devolve o caminho do png ou None.
    """
    usd_path = str(usd_path).replace("\\", "/")
    if png_path is None:
        png_path = os.path.join(os.path.dirname(usd_path),
                                "thumbnail.png").replace("\\", "/")
    try:
        from husd import assetutils
        assetutils.AssetGallery(None).renderThumbnailForAsset(usd_path,
                                                              png_path)
    except Exception:
        return None
    return png_path if os.path.isfile(png_path) else None


def registrar(db_path, nome, usd_path, thumb_png=None):
    """Um asset no banco. Devolve 'novo' ou 'ja existia'."""
    novos, _d = registrar_lote(db_path, [(nome, usd_path, thumb_png)])
    return "novo" if novos else "ja existia"


def registrar_lote(db_path, itens):
    """Registra varios (nome, usd, png). Devolve (novos, dups).

    Incremental: um banco existente e' ACRESCIDO (dedup por nome); um
    inexistente e' criado. Um escritor por vez -- no lote com --jobs so'
    o processo pai registra.
    """
    ds = hou.AssetGalleryDataSource(str(db_path).replace("\\", "/"))
    existentes = {ds.label(i) for i in ds.itemIds()}
    novos = dups = 0
    for nome, usd_path, thumb_png in itens:
        if nome in existentes:
            dups += 1
            continue
        item = ds.addItem(nome, file_path=str(usd_path).replace("\\", "/"))
        if thumb_png and os.path.isfile(thumb_png):
            with open(thumb_png, "rb") as fh:
                ds.setThumbnail(item, fh.read())
        existentes.add(nome)
        novos += 1
    return novos, dups
