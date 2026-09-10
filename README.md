# max2solaris

Exporta do **3ds Max** no padrão que o HDA `Asset_USD_Builder` (Solaris)
consome. Só o lado do Max — a construção do USD continua sendo do HDA.

## Instalar

Nada a instalar. No Listener do Max:

```
fileIn @"C:\dev\max2solaris\install\max2solaris.ms"
```

Abre a janela. O script recarrega os módulos a cada execução, então dá para
editar no VS Code sem reiniciar o Max.

## Como a ferramenta pensa: adaptativa, você escolhe o modo

Não existe UM jeito de importar kitbash. Três esquemas reais, medidos nos
pacotes do estúdio:

| esquema | exemplo | o que muda |
|---|---|---|
| **Um FBX, atlas nomeado** | KitBash3D Lunar Base | 1 arquivo com 79 objetos; `shop_materialpath` casa 100% com as texturas → bind por nome |
| **Multi-FBX, atlas único** | Post Apocalypse (vídeo Arcanacom) | 64 FBX numerados; material do FBX é lixo (`01 - Default`) → UM material do atlas, com variantes dark/light |
| **Pasta = asset** | Megascans, Maxtree | material único ou por parte; LODs; plantas ligam thin-walled+SSS |

O scanner (`library.py`) diz o que a pasta é; o perfil (`profiles.py`) dá os
defaults; e **o usuário sobrepõe o modo**: proxy, simproxy, center,
unit_scale, renderers, variantes (`profiles.custom()` / flags do lote /
checkboxes da janela).

Do KB3D_Converter_2.0 (vídeo do lucaroe) absorvemos: o **collect com
material flag** contendo um shader por renderer ("escolhi dois renderizadores
→ um collect com dois materiais"), e as **variantes de material como
variantes USD** — `componentmaterial` encadeados com `variantname`, dark e
light no MESMO asset.

O lote do Post Apocalypse usa o passo **GenerateBGEO** do vídeo do Arcanacom:
um FBX de props com centenas de objetos é convertido para bgeo UMA vez, em
vez de recarregado por prop.

```bash
hython tools/batch_kitbash.py "<raiz do set>" "<saida>" --no-proxy --no-simproxy
```

Verificado: 388 assets em 3 arquivos, 0 falhas; Building_01 com variantSet
mtl {dark, light} e outputs vray+mtlx+preview.

## O padrão que ele produz

Lido do PythonModule do HDA, não suposto — as referências estão em
[`naming.py`](src/max2solaris/naming.py).

```
<destino>/
  <Asset>/                        ← a pasta é o asset. Não há manifesto.
      <Asset>_High.fbx            ← LOD colado na extensão: _High. / _LOD0.
      <Asset>_VarA_High.fbx       ← variante, quando houver mais de uma
      <Asset>_..._albedo.png      ← texturas, reconhecidas por sufixo
      <Asset>_..._translucency.png
```

Três coisas decidem como o HDA lê o asset:

| o quê | como |
|---|---|
| **asset** | qualquer `.fbx` marca a pasta que o contém como raiz; dentro de `Var*`, a raiz é o pai |
| **LOD** | regex `_(High\|LOD\d+)\.` — o token tem que colar na extensão |
| **PLANT** | qualquer arquivo com `translucency` no nome marca o asset como planta, e os builders de material ligam o caminho de folha |

## Estado (v0.1)

Só geometria. A cópia de texturas existe mas vem **desligada** — e o export
avisa que, sem elas na pasta, o HDA acha o FBX e não monta material nenhum.

Defaults do FBX: **Y-up** e **centímetros**. São os dois que fazem o asset
chegar deitado ou 100× fora de escala no Solaris.

## Rodar sem a janela

A janela não contém regra nenhuma — ela lê e escreve um `Settings` e chama
`exporter.export`. Por isso o export é testável sem clicar:

```bash
"C:/Program Files/Autodesk/3ds Max 2027/3dsmaxbatch.exe" C:/dev/max2solaris/tools/headless_export.py -sceneFile "C:/.../asset.max"
```

O `3dsmaxbatch` não captura o stdout do Python, então o relatório aparece no
`_max2solaris.json` ao lado do FBX, não no log. E o log termina em
"Task Completed with Error(s)" por causa de um aviso de variável de ambiente
do V-Ray — não é o export.
