"""Coleta das texturas da cena para a pasta do asset.

Desligado por padrao -- a v1 da ferramenta so' exporta geometria. Existe
porque o `Asset_USD_Builder` monta o material a partir dos nomes de arquivo
que encontra na pasta do asset: sem textura la', ele acha o FBX e nao monta
material nenhum.

Nao renomeamos nada. Se o nome de origem ja termina num sufixo que o HDA
reconhece (_albedo, _normal, _roughness...), ele funciona; se nao termina,
avisamos em vez de inventar um sufixo -- chutar aqui produziria um material
montado com o mapa errado, que e' pior de achar do que um material vazio.
"""
import os
import shutil

from pymxs import runtime as rt

from . import naming


def scene_bitmap_paths():
    """Todos os arquivos de bitmap referenciados pela cena."""
    caminhos = []
    try:
        arquivos = rt.usedMaps()
    except Exception:
        arquivos = []
    for f in arquivos or []:
        try:
            s = str(f)
        except Exception:
            continue
        if s.strip():
            caminhos.append(s)
    return caminhos


def _resolve(raw):
    if os.path.isfile(raw):
        return raw
    try:
        achado = rt.mapPaths.getFullFilePath(raw)
        if achado and os.path.isfile(achado):
            return achado
    except Exception:
        pass
    return None


def collect(root, geo_files):
    """Copia as texturas da cena para a pasta de cada asset exportado.

    Devolve (copiadas, problemas).
    """
    destinos = sorted({os.path.dirname(g) for g in geo_files})
    copiadas, problemas = [], []

    for raw in scene_bitmap_paths():
        origem = _resolve(raw)
        if origem is None:
            problemas.append(raw)
            continue

        base = os.path.basename(origem)
        if naming.texture_suffix_of(base) is None:
            problemas.append(
                "%s (sem sufixo reconhecido pelo Asset_USD_Builder; "
                "renomeie para terminar em _albedo, _normal, _roughness...)"
                % base)
            # ainda assim copiamos: ter o arquivo la' ajuda o ajuste manual

        for d in destinos:
            alvo = os.path.join(d, base)
            try:
                if os.path.abspath(origem) != os.path.abspath(alvo):
                    shutil.copy2(origem, alvo)
                copiadas.append(alvo)
            except Exception as e:
                problemas.append("%s -> %s (%s)" % (base, d, e))

    return copiadas, problemas
