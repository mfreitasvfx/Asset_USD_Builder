"""Conversao de textura para .tex ACEScg -- o ImgConvert do Asset_USD_Builder.

Portado do PythonModule do HDA (lido, nao suposto):
  - OIIO ImageBufAlgo.colorconvert -> ACEScg, unpremult=True
      cor  (basecolor/specular/translucency/emission): 'sRGB - Texture'
      cor em .exr:                                     'Linear'
      dado (roughness/metalness/normal/opacity/...):   'Raw'
  - make_texture MakeTxTexture: tile 32x32, half (ou float),
    maketx:prman_metadata=1, resize=1, wrapmodes periodic
  - nome de saida identico ao do HDA:
      <base>_srgbtex_acescg.<ext>.tex   (cor)
      <base>_srgblin_acescg.<ext>.tex   (cor .exr)
      <base>_data_acescg.<ext>.tex      (dado)

E' por isso que o PxrTexture fica com linearize DESLIGADO (medido pelo
Matheus no viewport): a cor ja' chega linear/ACEScg no .tex -- linearizar
de novo dobrava a correcao.

Reusa o .tex se ja existir (como o HDA sem OverWrite).
"""
import os

_PAPEIS_COR = {"basecolor", "specular", "emission", "translucency"}

# O NOME do espaco depende do config OCIO ativo -- medido na maquina do
# Matheus: o Labs carrega 'sidefx_aces', onde sRGB de textura se chama
# 'Texture - sRGB(2.2) (.jpg, .png)'; o HDA assumia 'sRGB - Texture' (do
# config ACES 1.3 puro) e a conversao falharia calada. Resolvemos contra
# o config ativo, na ordem dos candidatos.
_CANDIDATOS = {
    "srgb": ["sRGB - Texture", "Texture - sRGB(2.2) (.jpg, .png)",
             "srgb_tex", "Utility - sRGB - Texture", "sRGB"],
    "linear": ["Linear", "Texture - sRGB(linear) (.exr, .hdr)",
               "Utility - Linear - sRGB", "lin_rec709", "scene_linear"],
    "raw": ["Raw", "raw", "Utility - Raw", "data"],
    "acescg": ["ACEScg", "ACES - ACEScg", "lin_ap1"],
}


def _resolve(chave):
    cands = _CANDIDATOS[chave]
    try:
        import PyOpenColorIO as ocio
        nomes = {cs.getName()
                 for cs in ocio.GetCurrentConfig().getColorSpaces()}
        for c in cands:
            if c in nomes:
                return c
    except Exception:
        pass
    return cands[0]


def _sufixo(papel, ext):
    if papel in _PAPEIS_COR:
        return "_srgblin_acescg" if ext == ".exr" else "_srgbtex_acescg"
    return "_data_acescg"


def nome_tex(caminho, papel):
    base, ext = os.path.splitext(str(caminho))
    return "%s%s%s.tex" % (base, _sufixo(papel, ext.lower()), ext)


def tex(caminho, papel, bitdepth="half", wrap="periodic", avisos=None):
    """Converte um mapa para .tex ACEScg. Devolve o caminho do .tex.

    Em erro (OIIO ausente, arquivo ruim) avisa e devolve o original --
    material montado com o mapa fonte e' melhor que material vazio.
    """
    caminho = str(caminho).replace("\\", "/")
    alvo = nome_tex(caminho, papel).replace("\\", "/")
    if os.path.isfile(alvo):
        return alvo
    try:
        import OpenImageIO as oiio
        from OpenImageIO import ImageBufAlgo
    except ImportError:
        if avisos is not None:
            avisos.append("OpenImageIO indisponivel; usando %s sem .tex"
                          % os.path.basename(caminho))
        return caminho
    try:
        buf = oiio.ImageBuf(caminho)
        if buf.has_error:
            raise RuntimeError(buf.geterror())
        origem = _resolve({"_srgbtex_acescg": "srgb",
                           "_srgblin_acescg": "linear",
                           "_data_acescg": "raw"}[
            _sufixo(papel, os.path.splitext(caminho)[1].lower())])
        ok_cc = ImageBufAlgo.colorconvert(buf, buf, fromspace=origem,
                                          tospace=_resolve("acescg"),
                                          unpremult=True)
        if not ok_cc or buf.has_error:
            # NUNCA escrever um .tex sem a conversao -- ele passaria por
            # ACEScg sendo sRGB e ninguem veria o erro
            raise RuntimeError("colorconvert %s->ACEScg: %s"
                               % (origem, buf.geterror()))
        cfg = oiio.ImageSpec()
        cfg.tile_width = 32
        cfg.tile_height = 32
        cfg.tile_depth = 1
        if bitdepth == "float":
            cfg.set_format(oiio.FLOAT)
            cfg.attribute("maketx:datatype", "float")
        else:
            cfg.set_format(oiio.HALF)
            cfg.attribute("maketx:datatype", "half")
        cfg.attribute("maketx:fileformatname", "exr")
        cfg.attribute("maketx:resize", 1)
        cfg.attribute("maketx:prman_metadata", 1)
        cfg.attribute("wrapmodes", '"%s,%s"' % (wrap, wrap))
        ok = ImageBufAlgo.make_texture(oiio.MakeTxTexture, buf, alvo, cfg)
        if not ok or not os.path.isfile(alvo):
            raise RuntimeError(buf.geterror() or "make_texture falhou")
        return alvo
    except Exception as e:
        if avisos is not None:
            avisos.append(".tex falhou (%s); usando %s"
                          % (e, os.path.basename(caminho)))
        return caminho
