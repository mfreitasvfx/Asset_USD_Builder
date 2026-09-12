# Estado — USD_Builder_Asset

Atualizado: 2026-09-10 (noite)

## Escopo (definido com o Matheus)

Recomeço deliberado. O projeto anterior (`C:\dev\max2lama`) reconstruía o
material inteiro no Houdini. Aqui a divisão é outra e mais simples:

    3ds Max  ──FBX no padrão──▶  Asset_USD_Builder (HDA)  ──▶  USD

O Max só exporta. Quem monta material e USD é o HDA, que já faz isso bem.

v1 é **só geometria**: sem import, sem cópia de arquivo.

## O que está feito

| peça | estado |
|---|---|
| `naming.py` — a convenção do HDA | escrita a partir do código dele |
| `settings.py` — opções serializáveis | ok |
| `exporter.py` — export FBX | **verificado em cena real** |
| `ui/window.py` — janela PySide6 | escrita, **não testada na UI do Max** |
| `textures.py` — cópia de texturas | escrita, desligada por padrão |

Verificado: `MT_PM_V93_Allium_cepa_01_01.max` → 743 KB de FBX em
`.../MT_PM_V93_Allium_cepa_01_01/MT_PM_V93_Allium_cepa_01_01_High.fbx`, e o
mesmo regex do HDA reconhece o LOD.

## Decisões que não são óbvias

**A janela não contém regra nenhuma.** Ela lê e escreve um `Settings` e chama
`exporter.export`. Isso é o que permite rodar o export inteiro pelo
`3dsmaxbatch` e testar sem clicar — se a lógica morasse nos callbacks da UI,
não haveria como verificar nada automaticamente.

**Não renomeamos textura.** Se o nome de origem não termina num sufixo que o
HDA reconhece, avisamos. Chutar o sufixo produziria um material montado com o
mapa errado — mais difícil de achar que um material vazio.

**Y-up e cm como default.** São os dois valores que fazem o asset chegar
deitado ou 100× fora de escala, e são silenciosos: ninguém vê no FBX, só no
Solaris.

## Ambiente medido

- 3ds Max 2027.2, Python 3.13.9, **PySide6 6.8.3**
- `3dsmaxbatch.exe` aceita script **Python** direto, não só MAXScript
- O log do `3dsmaxbatch` **não captura o stdout do Python**, e sempre termina
  em "Task Completed with Error(s)" por um aviso de env var do V-Ray. Não
  confiar no log para saber se deu certo — olhar o arquivo de saída.

## O FBX, medido (2026-09-09)

`tools/probe_fbx.py` importa um FBX num File SOP e reporta o que veio. Rodado
nos arquivos reais:

| | prims | objetos (`name`) | materiais (`shop_materialpath`) |
|---|---|---|---|
| Maxtree Zea mays | 57.834 | 1 | 6 |
| KitBash Lunar Base | 3.272.924 | 624 | 28 |

**Os nomes de material batem 100% com as partes que o scanner extrai das
texturas** — 6/6 no Maxtree, 28/28 no KitBash, zero divergências. O bind é
direto; não há tabela de tradução por biblioteca.

**Separar os assets do arquivo único do KitBash** sai do atributo `name`, que
traz o caminho da hierarquia (`KB3D_LNB_Antenna_A_grp/..._Main`): primeiro
componente sem o sufixo `_grp`. Conferido contra as 79 pastas que o Matheus
já tinha construído — casou 100% da amostra.

O Maxtree cai no mesmo código e dá um asset só. Não há caso especial.

Usamos **File SOP**, não o importador de FBX que cria árvore em `/obj` — é o
que evita os nulls e transforms que o HDA chamava de "FBX clutter".

## O vídeo do Arcanacom ("Import KitBash using TOPs", 23:14)

Assistido via o skill `/watch`. Três problemas que ele levou um dia para
resolver, e o que fazemos com cada um:

1. **Separar um FBX em vários assets.** Ele usa `filepattern` TOP → promove o
   atributo de primitiva `name` para atributo de *work item* → `ropfetch` num
   ROP FBX que escreve um arquivo por prop. É o mesmo `name` que medimos em
   `fbx.py`. Diferença: ele partia de 18 FBX de props; nosso KitBash é UM
   arquivo com as 624 peças, então dá para fatiar direto em SOPs, sem escrever
   FBX intermediário.

2. **Nome do prim raiz.** Ele monta um attribute wrangle que limpa o sufixo,
   promove para o **detail attribute `geo_name`**, e o `componentoutput` usa
   esse detail como nome do prim raiz. É exatamente a correção do
   `componentoutput1` repetido que eu tinha notado.

3. **Duplicados.** Peças modulares reaparecem em vários FBX do kit, então a
   asset gallery enche de objeto repetido. Ele resolve depois, editando o
   SQLite da gallery com o DB Browser. Melhor: detectar antes de construir.

Ele também converte unidades no ROP FBX — o mesmo cuidado que já temos no
lado do Max (Y-up/cm).

## O builder em LOPs (2026-09-09, fim do dia)

`src/usd_builder_asset/lops/` monta o componente: `componentgeometry` (File SOP +
partição por `shop_materialpath`, subsets sem prefixo) → `componentmaterial`
(materiallibrary em `/ASSET/mtl/`, bind explícito por parte) →
`componentoutput` (rootprim = nome do asset, sanitizado).

**Verificado escrevendo USD de verdade:**

| asset | resultado |
|---|---|
| Megascans (21.0.596) | 1 material Karma+preview, 1 bind, displacement |
| Maxtree (21.0.596) | 6 materiais, 6 binds, glossiness→invert, **thin_walled+subsurface nas folhas** |
| Megascans (22.0.368) | **Karma + Arnold no mesmo material** via collect |

Fatos medidos que sustentam o desenho:
- `partitionattribs` + `prefixpartitionsubsets=0` → subset com o nome limpo
  do material (probe_component.py)
- o componentmaterial NÃO casa por nome sozinho (medido; o hip do vídeo usa
  um Default só). Bind explícito por multiparm, uma entrada por parte.
- Megascans traz `shop_materialpath='default_material'` → asset de material
  único binda o material no `/ASSET/geo` inteiro, ignorando nome de subset.
- prim começando com dígito (`3d_...`) é inválido em USD e derruba o
  componentoutput em cascata → `naming.usd_prim_name()`.

Receitas de material: conversores da Rebelway (Karma mtlx + Arnold
standard_surface + collect). Desvio consciente: mapa de dado em Raw no
Arnold (eles usavam ACEScg em roughness/metalness). Planta = thin_walled +
subsurface com o mapa de translucency — a regra do Matheus, agora nos dois
renderers.

**Iteração sem reiniciar o Houdini:** `tools/build_lops.py` roda tudo via
hython; `install/houdini_reload.py` é o snippet de recarga para a sessão
aberta (mesmo padrão do lado Max).

Pendências conhecidas:
1. componentoutput gera `_duplicate1.usd` em re-runs — falta o parm de
   overwrite; e os nós soltos do Karma publicam 2 prims Material extras
   além do collect (inofensivo, mas é ruído).
2. KitBash split (`--object`) escrito e não testado ponta a ponta.
3. Resolução de textura (4K/8K do Megascans) ainda não é escolha de perfil.
4. RenderMan e V-Ray nos materiais LOPs — receitas já medidas no max2lama.
5. Vídeos do Jonas Noell (UVWRandomizer anti-tiling, Parallax Occlusion)
   assistidos e anotados — base do toolset de triplanar/anti-tiling futuro.

## KitBash no padrão Rebelway (2026-09-10)

O componentgeometry agora segue o RBL_Component_Builder_Template: branch
**default** (file → blast por objeto → nomes de peça limpos → convert_units →
center na origem), **proxy** (polyreduce 6%) e **simproxy** (shrinkwrap =
convex hull, para os LOPs de física).

A/B contra o build de referência do Matheus (LunarBase_OUTPUT/Antenna_A):

| | nosso | referência |
|---|---|---|
| defaultPrim | KB3D_LNB_Antenna_A | componentoutput1 (bug) |
| materiais | 11 | 11 |
| outputs | arnold+mtlx surface **e displacement** + preview | surface só |
| proxy | sim | sim |
| simproxy (guide) | **sim** | não |
| bbox | **idêntico** (15.3 m) | 15.3 m |

A escala veio do A/B: o FBX está em cm e sem o `unit_scale=0.01` do perfil o
asset saía 100× maior. É o "convert the units" do vídeo do Arcanacom.

**Todos os renderers no 21.0.596.** Dois consertos de ambiente no caminho:
1. O htoa.json apontava para o build do 22.0; o Matheus instalou o 6.4.6.0
   para 21.0.596 e o trava de ontem foi removido.
2. Causa raiz dos materiais vazios: o tradutor USD do **V-Ray** importa
   `vfh` num contexto onde `vfh_home/scripts/python` ainda não está no path
   quando o HtoA muda a ordem de init — e a exceção corrompe o registro de
   tradutores inteiro (thePreviewTranslators). Fix: PYTHONPATH no package do
   V-Ray (backup .bak2). Karma+RenderMan+V-Ray+Arnold convivem agora.

Desvios documentados do template: proxy por polyreduce (não VDB→remesh) e
simproxy de hull único (não por peça via foreach). Trocar se precisar.

## RenderMan + V-Ray no collect, e a janela (2026-09-10)

`lops/mat_extra.py`: **PxrSurface** (a receita do Asset_USD_Builder, sem o
.tex — inclusive a fidelidade de deixar metalness desconectado, porque
PxrSurface não tem input de metallic; metal fiel vem com LAMA depois) e
**VRayMtl** (a tabela medida no max2lama: option_use_roughness, bump_type
'1', enums string; displacement fica fora — no V-Ray é da geometria).

Antenna_A agora publica num material só:
`arnold:surface+displacement`, `mtlx:surface+displacement`,
`ri:surface+displacement`, `vray:surface`, `surface` (preview).

**Janela** (`ui/houdini_panel.py`, PySide6 com fallback PySide2): pasta →
Scan → lista de objetos (KitBash, com filtro e multi-select) → renderers →
Build. Recarrega os módulos a cada Scan/Build — editar no VS Code e clicar
de novo, sem reiniciar o Houdini. `install/houdini_reload.py` abre a janela.
Smoke-test offscreen no hython cobre a construção da UI (34 widgets, scan
do Maxtree ok); o clique real é do Matheus.

## Post Apocalypse + esquema KB3D_Converter_2.0 (2026-09-10, tarde)

O set do vídeo do Arcanacom é outro formato: 64 FBX numerados, material do
FBX é lixo ('01 - Default'), atlas único com basecolor dark/light. Sem
casamento por nome — o material nasce do atlas, como o Default único do hip.

`tools/batch_kitbash.py`: lote com modos (--no-proxy/--no-simproxy/
--no-center/--unit-scale — "a ferramenta é adaptativa, eu escolho o modo"),
cache bgeo para arquivos de props (o GenerateBGEO do vídeo; sem ele, 2
arquivos estouravam 10 min — com ele, 388 assets em ~8 min, 0 falhas).

Do KB3D_Converter_2.0 (script lido em Downloads/Kitbash_usd_Converter_latest):
- collect com material flag + um shader por renderer (karma_X, vray_X...)
- presets de shader copiáveis (qualidade controlada pelo artista) — ainda
  não adotado, anotado
- **variantes de material = variantes USD**: componentmaterial encadeados
  com variantname. Implementado: `build_asset(variants=[...])`;
  Building_01 saiu com variantSet mtl {dark, light}, vray+mtlx+preview.
- glass/window ganham transmission automático por nome — anotado, não feito.

Correção de contexto: o LunarBase_OUTPUT de referência foi produzido pelo
KB3D_Converter_2.0 (daí o defaultPrim componentoutput1 e o karma:surface).

## V-Ray de verdade + o lote que o Matheus testou (2026-09-10, noite)

O Matheus testou: "parece funcionar, só não funciona em V-Ray". Diagnóstico
MEDIDO comparando nosso USD com o que o builder OFICIAL do V-Ray emite
(`vray_vop_builder` + `vray_material_output`, achado no vfh.shelf):

- NOSSO (errado): NodeGraph → MtlSingleBRDF com terminal `outputs:material`.
  O delegate Hydra do V-Ray não resolve essa forma → material cinza.
- OFICIAL: `outputs:vray:surface → BRDFVRayMtl.outputs:brdf` DIRETO.

Conserto: `build_vray` agora cria o `vray_vop_builder` oficial (BRDF no
input Material do vrayOutput; sem MtlSingleBRDF). No collect só a saída
`surface` conecta (displacement no V-Ray é da geometria). De quebra: o
BitmapBuffer estava sRGB em TUDO — mapa de dado agora é linear
(`auto_color_space=0` + `color_space='0'`; o parm VOP se chama color_space,
não transfer_function como no USD).

O -498 do husk com o delegate V-Ray é criação do renderer em headless
(licença), NÃO o asset — o teste de render de verdade é no viewport do
Matheus.

Mais três problemas do teste dele, todos medidos e consertados:

1. **100 GB de texturas**: o `localize=1` do componentoutput copiava o
   atlas (119 MB) para DENTRO de cada um dos 819 assets. Modo
   `tex_dir`/`--tex-mode shared` (default no lote): UMA cópia em
   `<saida>/textures`, materiais com `../textures/...` relativo,
   `localize=0`.
2. **Segfault no arquivo 18/64**: 819 redes acumuladas numa sessão hython.
   `cleanup=True` destrói o subnet depois de escrever.
3. **"roda em multithread?"**: `--jobs N` = N processos hython, cada um com
   a fatia `i::N` dos arquivos (processo, não thread — o hou não é
   thread-safe p/ build). Cópia de textura ficou atômica (tmp+replace) por
   causa da corrida entre workers. Medido: 2 workers, 4 arquivos, 392
   assets, 0 falhas.

Pedidos do Matheus atendidos no mesmo passe:
- Nó renomeado: subnet `USD_Builder_Asset_<asset>` (era usdba_*).
- Janela com ETAPAS numeradas como o HDA do Carlo: 1 SCAN, 2 BUILD ASSETS
  (monta a rede SEM escrever — dá para abrir o subnet e alterar), 3 EXPORT
  USD's (executa os componentoutput). "chegar e alterar caso for preciso".
- Settings do Asset_USD_Builder (aba IMG SETTINGS): Displacement Scale,
  BaseColor Gamma (mtlxrange gamma / arnold color_correct; RenderMan e
  V-Ray avisam que não aplicam), Normal Scale (mtlxnormalmap.scale /
  normal_map.strength / pxrnormalmap.bumpScale), SubSurface (peso do sss
  nas plantas), Remap Displacement (mtlxremap / arnold::range) — em
  `materials.DEFAULTS`, threading via `settings=` até os builders.

## Rename total + feedback do teste do Matheus (2026-09-10, mais tarde)

O Matheus testou de verdade (render V-Ray no viewport OK!) e pediu:

1. **"não teremos mais esse nome em nada"**: rename completo
   max2solaris → **USD_Builder_Asset**. Pasta `C:\dev\USD_Builder_Asset`,
   pacote Python `usd_builder_asset`, janela, shelf, prefixos de nó
   (usdba_*). ATENÇÃO ao retomar: `C:\dev\max2solaris` não existe mais.
2. **Log no console do Houdini igual ao Asset_USD_Builder**: `log.py`
   (banners, checkmarks, BuildTime) e o `_diz` da janela espelha no
   stdout. START/FINISHED SCANNING/BUILDING/EXPORTING.
3. **"não localizou os arquivos"**: ele apontou `<set>/FBX/FBX`; as
   texturas moram em `<set>/Textures`. `_sobe_por_texturas()`: com
   geometria e sem textura, sobe até 3 níveis coletando mapas
   reconhecíveis (calado sobre Icon.jpg/Title_*.jpg da subida). Junto:
   `Asset.geo_files` + `multi_fbx` (vários FBX sem LOD = Post
   Apocalypse), `atlas_material`/`atlas_variants` moveram do batch para a
   library, e a JANELA ganhou o modo multi-FBX: a lista mostra os
   arquivos, o Build abre cada um e monta os assets de dentro com as
   variantes do atlas. Medido: scan no FBX/FBX acha 64 arquivos + atlas
   dark/light; build etapa 2 não escreve; etapa 3 escreve (8 s).

Checkboxes proxy/simproxy na janela (Branches). O Matheus quer rodar o
export completo ELE MESMO pelo script para caçar erros — não disparar
lote por ele.

## Próximo passo

1. Lunar Base completo (79 objetos, esquema FBX único name-matched).
1b. Presets de shader editáveis (esquema 2.0) — qualidade Jonas Noell no V-Ray.
2. TOPs: wrapper de visualização por work item (o --jobs já dá o paralelo;
   falta o "ver separado pra checar" na UI de TOPs que o Matheus pediu).
3. Duplicados entre kits (detectar no scan, antes de construir).
4. LAMA como quinto renderer do collect (receitas prontas no max2lama).
5. Lado Max: janela nunca aberta na UI; variantes VarA/VarB por definir.
6. componentoutput em re-run ainda gera _duplicateN.usd (parm de overwrite).

## Feedback do 2o teste + Asset Gallery (2026-09-10, noite)

Do print do Matheus, tudo medido/consertado:
- Lista em ORDEM NATURAL (`library.natural_key`): 1, 2, ..., 10 — não 1, 10, 11.
- Nó `output0` conectado embaixo do componentoutput nos dois caminhos.
- Centralizar ANTES de converter escala (equivalente geometricamente;
  ordem legível — pedido dele).
- Setas dos spinboxes maiores (26px de altura, botões 22px).
- Arnold DESLIGADO por default na janela ("esquece ele por enquanto").
- **Thumbnail + Asset Gallery**: `gallery.py` em cima do OFICIAL
  `husd.assetutils.AssetGallery` — `renderThumbnailForAsset` (render
  externo karma, funciona headless; medido) e `addAsset` com
  `variant_sets=["mtl"]`: dark/light viram TILES separados na Layout
  Asset Gallery com seleção automática de variante. Dedup por nome-BASE
  (labels saem "Nome (dark)") ANTES de inserir — o problema de duplicados
  que o vídeo conserta depois no DB Browser. Lote: --gallery (passe do
  processo pai = um escritor no SQLite) e --thumbs (por worker). Janela:
  checkbox no export; db em <saida>/asset_gallery.db; apontar a pane
  Layout Asset Gallery para ele.
- "Smoke test" explicado ao Matheus: teste automático que só abre a
  janela offscreen e confere que ela constrói sem erro — não clica nada.

## Espaços de cor + .tex + cores dos nós (2026-09-10, madrugada)

Pedidos do Matheus, tudo medido:

1. **Opções todas desligadas por default** na janela (tex compartilhada,
   gallery, proxy, simproxy, .tex) — ele liga o que quiser.
2. **Espaços de cor conferidos contra os scripts** (recuperados do
   transcript): Arnold da Rebelway = cor sRGB - Texture, normal/opacity
   Raw, e roughness/metalness em ACEScg — mantivemos nosso desvio
   consciente (Raw em dado; ACEScg em mapa de dado distorce valores).
   Karma da Rebelway usa SÓ a signature (color3/default/vector3), sem
   colorspace explícito — exatamente o que já fazemos. Os scripts NÃO
   convertem .rat/.tx: eles PULAM (mipmaps) — nosso scanner idem.
3. **linearize DESLIGADO no RenderMan** — achado do Matheus no viewport:
   o color manager do RfH (e o .tex ACEScg) já entregam linear; com
   linearize=1 corrigia duas vezes.
4. **texconv.py = o ImgConvert do HDA** (lido do PythonModule): OIIO
   colorconvert → ACEScg + make_texture (tile 32, half, prman_metadata,
   wrap periodic), nomes idênticos (_srgbtex_acescg/_data_acescg/.tex).
   PEGADINHA MEDIDA: o nome do espaço depende do config OCIO ativo — a
   máquina do Matheus roda o sidefx_aces do Labs, onde sRGB é
   'Texture - sRGB(2.2) (.jpg, .png)'; o 'sRGB - Texture' do HDA falharia
   CALADO (e o .tex sairia sem conversão). _resolve() casa candidatos
   contra o config ativo e NUNCA escreve .tex sem conversão.
   Opt-in: checkbox na janela / --tex-renderman no lote.
5. **Cores dos nós = padrão do Asset_USD_Builder** (lido do PythonModule):
   subnet planta [0.5,0.7,0.3], objeto [0.29,0.56,0.89], variante
   [1,0.6,0]; geo [1,1,0.5]; matlib [0.5,1,0.5] (vermelho sem textura);
   componentoutput [0,1,0].

## Nós de ajuste + metallic workflow + UPDATE MATERIALS (2026-09-10, tarde da noite)

Pedidos do Matheus, todos medidos e verificados no USD:

1. Settings JÁ reagem aos mapas: disp_scale entra quando ha displacement,
   subsurface quando planta+translucency — confirmado a ele.
2. **Nó de ajuste NEUTRO em todo caminho de mapa** ("se eu quiser alterar
   valor"): cor ganha colorcorrect (mtlxcolorcorrect / pxrcolorcorrect::3.0
   com o BaseColor Gamma / VRayNodeColorCorrection), dado ganha range/remap
   (mtlxrange / pxrremap::3.0 / VRayNodeTexRemap input_value→value).
   remap_height agora fica SEMPRE no caminho do displacement (neutro).
3. **Metallic no RenderMan conectado** — achado do Matheus: e' via
   `pxrmetallicworkflow::3.0` (in: baseColor/metallic/specular; out:
   resultDiffuseRGB/resultSpecularEdgeRGB/resultSpecularFaceRGB).
   basecolor_cc → baseColor, metalness_remap.resultR → metallic, e os 3
   outputs no PxrSurface. Verificado no mtl.usdc das duas variantes.
   O aviso antigo de "metalness sem ligar" morreu.
4. **UPDATE MATERIALS** (o UPDATE ALL SETTINGS do HDA): Result.matlibs
   guarda (materiallibrary, [(nome, mapas, plant)]);
   builder.rebuild_materials esvazia cada matlib e remonta com os
   settings/renderers atuais — geometria, binds e output ficam. Botão na
   janela entre BUILD e EXPORT. Verificado: rebuild + re-export escreve.
5. Vídeos de referência do Matheus (playlists RenderMan Material series,
   7OgyUs3UCyg e K3WbPZZYcg8) anotados p/ a fase de qualidade de shader.

## Config do thumbnail (2026-09-10, sequência)

A seção Thumbnail do componentoutput agora é configurável pela ferramenta
(parms medidos: thumbnailmode, autothumbnail, res1/res2, spin/pitch/dist):
`build_asset(thumb_cfg={"mode":1,"res":512,"spin":..,"pitch":..,"dist":..})`
liga o Re-Generate on Export. Na janela: checkbox "Thumbnail no export
(Houdini GL)" + res/spin/pitch/dist (desligado por default). O export com
gallery usa o thumbnail.png que o GL deixa na pasta; render externo só na
falta dele.

## Abas na janela + Karma no builder oficial (2026-09-10, madrugada 2)

- Janela em DUAS ABAS como o HDA: "USD BUILDER" (fonte, lista, renderers,
  saída, botões 1/2/3) e "SETTINGS" (ajustes, branches, opções, thumbnail
  e o UPDATE MATERIALS). Log embaixo, fora das abas.
- Renderers TODOS desligados por default (pedido; guarda avisa se Build
  sem nenhum marcado).
- Karma migrou para o builder OFICIAL (voptoolutils._setupMtlXBuilderSubnet,
  KARMAMTLX_TAB_MASK, contexto 'kma') — a forma do print do Matheus
  ('karmamaterial' com surface/displacement/properties). USD agora publica
  outputs:kma:surface + preview; ganha o material_properties (render
  settings por material). O mtlxdisplacement default é reusado quando há
  mapa e destruído quando não há. Nomes básicos mantidos (surface,
  basecolor, ...). O subnet manual ctx 'mtlx' também renderizava (medido
  no viewport do Matheus), mas o oficial é o padrão — mesma lição do V-Ray.
- gallery.py: dedup por nome-BASE ('Nome (dark)' conta como 'Nome') — o
  bug dos tiles duplicados de variante.

## Variantes abolidas + gallery incremental confirmada (2026-09-11)

Decisões do Matheus, medidas:

1. **Variantes dark/light FORA do default** ("quando publica duplica...
   fica a light mas sem o nome"): o fluxo multi-FBX monta UM material da
   variante LIGHT, nomeado pela parte-base do atlas
   (Post_apocalypse_city), sem sufixo. `--variant both` continua no lote
   para quem quiser. componentmaterial sem variantes agora zera o
   variantname (o default criava variante 'assign' com o nome do nó;
   vazio deixa o variantSet mtl declarado porém VAZIO — inerte).
2. **Thumbnail implícito na gallery**: um checkbox só ("Asset Gallery no
   export") — liga o autothumbnail GL no componentoutput E o registro no
   banco; a linha res/spin/pitch/dist configura.
3. **Gallery é INCREMENTAL, medido**: addItem direto no
   AssetGalleryDataSource persiste, chamadas separadas ACRESCENTAM
   (exportar aos poucos funciona), repetido dá 'ja existia'. O
   assetutils.addAsset SEM variantes criava o db e não inseria NADA
   (calado) — gallery.py voltou ao addItem direto, que é o que funciona.

## V-Ray: MetaImageFile + vrayMtl reusado (2026-09-11)

Feedback do teste do Matheus no viewport:

1. **TexBitmap+BitmapBuffer NAO renderiza** no delegate; o que funciona e'
   o **VRayNodeMetaImageFile** com OCIO ligado (ele provou na mao:
   Enable OCIO, Config Environment, Mode ColorSpace, In 'Texture -
   sRGB(2.2) (.jpg, .png)' -> Out 'ACEScg'). build_vray agora usa
   MetaImageFile: cor = OCIO com nomes resolvidos do config ativo
   (texconv._resolve); dado = BitmapBuffer_color_space '0' linear sem
   OCIO. Saidas identicas (color/intensity), cc/remap intactos.
2. **vrayMtl solto**: o vray_vop_builder ja nasce com um vrayMtl; criar
   outro deixava o default pendurado. Agora REUSA (renomeado 'surface').
3. atlas_material: parte-base = nome mais CURTO, e partes longas
   atualizam primeiro (arquivos extras de teste na pasta de texturas nao
   batizam o material nem sobrepoem os mapas da base).

## O cinza do Karma: bind perdido, nao material (2026-09-11, cont.)

O Matheus pegou no viewport: tudo cinza, "parece que o material library
nao le". Diagnostico por RENDER headless A/B (husk + Karma CPU, media de
canais): o material estava COMPLETO no USD, mas havia ZERO bindings.
Causa: meu `variantname=""` no componentmaterial (da limpeza da variante
'assign') -- o no SEMPRE autora o bind DENTRO de uma variante, e sem nome
a edicao se perde, calada. Nao existe toggle para desligar (medido:
parms sao so' variantset/variantname). Fix: variantname='default'.
Verificado: bind presente e render com cor (desvio 0.0108 vs 0.0000).
De quebra: o contexto kma do builder oficial do Karma renderiza certo --
nunca foi o problema.

## Maxtree + seletor de perfil + receita do Jonas nas folhas (2026-09-11)

1. **Seletor de Perfil na janela** ("não seria melhor eu indicar isso
   marcando?"): combo Auto/Megascans/Maxtree/KitBash/Construido/Generico;
   quando marcado, ele manda no scan E no build (base_key; cuidado: key
   de profiles.custom ganha '+custom', nunca reusar como base).
   Evermotion/SpeedTree/Fab entram quando houver pasta real para medir.
2. **Zea mays (Maxtree) verificado**: perfil auto, 6 materiais, 6 binds
   por nome, folhas com thin_walled+subsurface (karma) e translucency=6
   +refract_thin_walled (vray); render headless VERDE dominante (desvio
   0.0357). Build 9 s.
3. **Video das folhas do Jonas Noell (e2KqOfraUyw) extraido via /watch**
   (o skill do Matheus funciona) e a receita aplicada no build_vray:
   - reflect BRANCO PURO quando ha mapa de rough/gloss (o default preto
     = zero specular; estava faltando em TODOS os nossos VRayMtl!)
   - opacity_mode Clip ('1') nas plantas (folha nao tem semi-transparente)
   - subsurface default 0.25 (Jonas: "nunca perto de 1"; o HDA tambem usa
     0.25) -- karma weight e translucency do vray via remap no caminho
   - VRay2SidedMtl para frente/verso DIFERENTES: anotado, so quando o
     asset tiver textura de verso (Maxtree nao tem)
   Confirmado no USD: reflect (1,1,1,1) x6, opacity_mode 1 x2,
   translucency 6 x2.
4. README: legenda das cores dos nos (o laranja->azul que o Matheus viu =
   variantes -> objeto unico).

## Alavancas no geo sempre + folha pelo NOME + cores folha/tronco (2026-09-11)

1. **center_to_origin e convert_units SEMPRE dentro do componentgeometry**
   ("todos devem ter, ate porque a escala vem diferente"): perfil so' da
   os valores; neutros (justify None, scale 1) quando nao pede. Campo
   "Unit Scale (0 = do perfil)" na aba SETTINGS.
2. **"Nao pegou as folhas"** -- medido: Leaf_03 nao tem opacity nem
   translucency NEM NO PRODUTO original (a folha e' modelada inteira);
   o setup de folha so' disparava com mapa de translucency. Agora
   dispara tambem pelo NOME (leaf/folha): karma/renderman SSS puxando
   do basecolor, vray translucency_amount = subsurface (0.25).
   Verificado: Leaf_03 com translucency=6/thin=1/amount=0.25 e
   thin_walled+subsurface no karma.
3. **Cores por tipo de parte** (pedido): folha VERDE (0.5,0.7,0.3),
   tronco MARROM (0.45,0.3,0.15) -- tokens leaf/leaves/folha e
   trunk/tronco/bark/branch -- no collect e nos builders por renderer.

## Todos os albedos viram material (2026-09-11, cont.)

"Se pegar por albedo da pra ver que tem 12, assim como o Max. mas so
veio oito" -- a ferramenta so montava material para os subsets presentes
na malha DESTA variacao. Agora TODA parte das texturas vira material na
/ASSET/mtl (igual ao Max: 12 albedos = 12 materiais); o BIND continua
explicito, so nas partes com subset na malha. Verificado no Zea: 12
materiais no USD, 6 bindings. As outras variacoes da mesma planta acham
seus materiais prontos.

## V-Ray: BRDFBump e translucency como COR (2026-09-11, cont.)

O Matheus pediu pesquisa NOS MANUAIS antes de mexer -- feito
(docs.chaos.com):

1. **Normal via V-Ray Bump (BRDFBump)** -- manual do V-Ray for Houdini:
   e' um WRAPPER entre o material base e a saida (base_brdf <- brdf;
   bump_tex_color <- mapa; map_type '1' = Normal Tangent; bump amount =
   intensidade). O bump_map direto no BRDFVRayMtl era a forma antiga --
   provavel causa de materiais nao aparecerem. Rede agora igual a do
   print do Matheus (Cosmos).
2. **Translucency e' COR, nao intensity** -- o Matheus apontou e o
   SDK confirma: o plugin tem translucency_color (Value/texturavel),
   mas o VOP do vfh 21.0 NAO expoe como input (medido); os slots
   texturaveis da secao sao fog_color_tex (cor) + translucency_amount.
   Wiring novo: mapa (sRGB->ACEScg via MetaImageFile OCIO) -> cc ->
   fog_color_tex; translucency_amount ESCALAR = subsurface (0.25).
   O remap->amount antigo morreu.
   Verificado no USD do Zea: 12x BRDFBump (map_type 1, base_brdf
   conectado), folhas com fog_color_tex.connect + translucency=6 +
   amount=0.25.

## refract no default + auditoria de parms (2026-09-11, cont.)

1. **refract=[1,1,1,1] REMOVIDO** (erro apontado pelo Matheus): com
   thin-walled SSS, refract branco deixava a folha vitrea. Fica o
   default (preto). Verificado: 0 ocorrencias no USD novo.
2. **"Parametros que nao aparecem"** -- auditoria completa (material de
   folha com TODOS os papeis, 3 renderers): um unico aviso, o
   intencional do displacement. Todos os sets pegam. O que engana:
   (a) a UI do vfh esconde secoes condicionais (Translucency so aparece
   com modo != None, roughness muda o rotulo do glossiness, etc.);
   (b) o tradutor NAO autora valor igual ao default do plugin
   (shader_skipdefvalparms) -- ex.: option_double_sided default ja e'
   True, entao setar True nao aparece no USD e esta CERTO assim.
   Medido: double_sided default True, thin_walled default False (esse
   autora), opacity_mode default Stochastic (Clip autora).

## Fase de LOOK: presets editaveis (2026-09-11, fechamento)

"Funcionou, todas as texturas aparecem. o que falta agora e' ajuste de
look" -- implementado o esquema de presets do KB3D_Converter_2.0:

- presets.py: salvar(no selecionado) -> presets/<renderer>_<tipo>.cpio
  (tipo leaf/trunk/default pelos tokens do nome); carregar() no
  build_material ANTES da receita de codigo; aplicar_texturas()
  re-aponta por papel (contrato dos nomes basicos) com aviso para
  qualquer descasamento.
- Botao SAVE PRESET na aba SETTINGS (builder selecionado).
- Verificado ponta a ponta: ajuste do artista (amount 0.42, gloss 0.77)
  herdado pelo proximo build de folha, texturas trocadas para o asset
  novo, zero avisos.

O caminho da qualidade Jonas Noell agora e': ajustar UMA folha no
render, SAVE PRESET, e o lote inteiro herda.

## Zea com os 4 renderers + lista de checagem (2026-09-11, cont.)

Build do Zea com karma+arnold+renderman+vray: ri:surface no USD (6
connects, PxrMetallicWorkflow incluso), kma+vray+preview ok. Arnold NAO
constroi no hython (medido: shaders do htoa registram mas o HDA
arnold_materialbuilder nao carrega -- houdiniPath sem htoa); na GUI
deve carregar -- arnold_available() agora testa o TIPO DE NO, nao o
path. docs/checagem.md criado: a lista de checagem visual do Matheus
("pode construir para os outros renderizadores, so nao vou checar
agora. coloca na lista de checagem").

## CORRECAO: o ri tinha sumido do collect (2026-09-11, cont.)

O commit anterior AFIRMOU ri:surface no USD com base num grep gordo
(contava PxrSurface, nao o terminal) -- ERRADO. O terminal ri NAO estava
no Material. Bisseccao mediu a causa: ligar a saida 'properties' do
builder oficial do Karma no collect derruba o terminal do subnet ri
(km surface-so' + rman = kma+ri+preview convivem). Fix: o collect pula
a saida 'properties' do karma. Verificado no Zea: 12x
outputs:ri:surface.connect, contextos kma+ri+vray+preview.
Licao: grep de verificacao tem que mirar o TERMINAL exato.

## Two-sided nos 3 renderers + Karma 2.7x mais rapido + Arnold no H22 (2026-09-11)

1. **"Por que demora com karma marcado?"** -- MEDIDO: o
   _setupMtlXBuilderSubnet custa ~0.47s/material (parm templates). Fix:
   template criado UMA vez por materiallibrary (karma_TEMPLATE) e os
   demais por copia -- 2.82s -> 1.05s em 6 materiais.
2. **Two-sided (video das folhas)**: partes `<Nome>_Back` viram papeis
   back_* (_funde_verso). V-Ray = Mtl2Sided (front/back/translucency_tex;
   thin-walled FORA nesse caso, o video mostra que anula); Karma =
   twosided chaveando basecolor por facing (traduz como sourceAsset com
   nome _undefined -- render a conferir); Arnold = arnold::two_sided
   (front/back, medido no H22). Sem biblioteca real com verso: checagem
   pendente com textura sintetica/manual.
3. **Arnold valida no Houdini 22** (pedido): zea_h22 com 12 materiais e
   outputs:arnold:surface + kma + preview. No 21 o HDA do htoa nao
   carrega em hython; na GUI do 21 deve funcionar (check por tipo de no).

## Two-sided opt-in, UI em ingles, pastas recentes (2026-09-11, cont.)

1. Two-sided virou CHECKBOX na tela principal (USD BUILDER, junto dos
   renderers), default OFF -- build_asset(two_sided=) / --two-sided no
   lote. Sem o box, partes _Back ficam como materiais separados.
2. UI do builder em INGLES (labels, botoes e mensagens principais do
   log). Codigo/comentarios continuam PT.
3. Asset Folder virou combo editavel com as ULTIMAS 8 pastas (persistem
   em $HOME_HOUDINI/usd_builder_asset_recent.json; salvas a cada SCAN
   valido, mais recente primeiro).

## translucency_color: diferenca entre builds do vfh (2026-09-12)

O Matheus notou o input translucency_color presente no 20.5 e ausente no
21.0. MEDIDO: Houdini_20.5 roda V-Ray 7.00.10 (release) e Houdini_21.0
roda 7.10.00 (Update 1) -- a Chaos REMOVEU o input no Update 1 (o parm
continua; conectaveis viram translucency_amount + fog_color_tex).
build_vray agora e' adaptativo: usa translucency_color quando o build
expoe, senao fog_color_tex.

## unit_scale 0.01 e' o DEFAULT de todos os perfis (2026-09-12)

Decisao do Matheus: o pipeline exporta em cm (Max/KitBash/Megascans) e
o USD e' metros. Default do Profile mudou de 1.0 para 0.01 -- todos os
perfis herdam. VERIFICADO no Zea rebuild: milho com 2.09 m de altura
(antes saia 100x). O Unit Scale da janela (0 = do perfil) sobrepoe.

## Branches de planta copiados do hip do Matheus (2026-09-12)

Ele montou a mao, no Zea, os branches de proxy/simproxy e pediu para a
ferramenta replicar -- "nao sobrescreve os outros, e' um ACRESCIMO de
exports" para Maxtree/plantas. Dump medido do `asst builder.hiplc`
(Downloads/Maxtree ... /FBX_Export):

- proxy   : labs::delete_small_parts (mode 0, threshold 2.39) ->
  lowres_geo::1.1.1 (HDA dele em Documents/houdini21.0/otls, 2%) ->
  wrangle `s@asset_name = chs("asset_name")` (spare parm, "/<prim>") ->
  Color class=prim, colortype=4 (Random from Attribute), seed 0.97,
  attrib asset_name -> attribpromote Cd prim->DETAIL (inclass=1,
  outclass=0 -- menu medido: 0=detail!) -> attribdelete asset_name.
  Resultado: UMA cor aleatoria por asset (Zea = magenta .61/.02/.90).
- simproxy: lowres_geo -> assemble -> convexdecomposition ->
  attribdelete class.
- TODOS os outputs (default incluso) fecham com Add remove=1 --
  medido: "Remove Unused Points", limpeza inofensiva.

Implementacao: `builder._branches_planta` (nomes de nos identicos aos
dele), ligada por `Profile.proxy_style="plant"`; maxtree agora tem
proxy=True, simproxy=True, proxy_style="plant". KitBash segue no
estilo "reduce" (polyreduce/shrinkwrap) -- nada sobrescrito. Fallback:
sem o HDA lowres_geo, entra polyreduce 2%.

Janela: no SCAN os checkboxes de Branches passam a REFLETIR o perfil
(maxtree/kitbash acendem; desmarcar antes do BUILD sobrepoe --
ferramenta adaptativa). Smoke: rede gerada = hip dele (topologia,
parms, cor final e contagem 493 prims/368 pts identicas).

## Proxy ligado = shader sumia do render: bind perdido DE NOVO (2026-09-12)

O Matheus reportou: com proxy (ate' feito a mao) o shader nao aparece no
render. NAO e' viewport/purpose: A/B estrutural mostrou o USD com proxy
saindo com ZERO binds (sem proxy: 6). Causa: com branches, o
componentgeometry ANINHA a malha em /ASSET/geo/render/<mesh>/<subset> e
o padrao de bind `/ASSET/geo/*/<parte>` (um nivel de curinga) deixa de
casar. Detalhe: `**` no MEIO do caminho nao casa no componentmaterial
(medido; `/ASSET/geo/**` no fim e `%type:GeomSubset` funcionam).

Conserto: _bind_parts vira o UNICO lugar que monta padrao (o caminho
sem variantes tinha uma copia inline -- unificado) e usa DOIS padroes
separados por espaco: `/ASSET/geo/*/<p> /ASSET/geo/render/*/<p>`.
PROVA: A/B Zea com 6 binds nos dois casos e husk/Karma com renders
PIXEL-IDENTICOS (hoiiotool --diff PASS). Purposes conferidos: proxy
prim purpose=proxy, simproxy invisivel.

Nota de viewport p/ o Matheus: GL/Storm mostram purpose guide+proxy
(UsdRenderers.json do HFS), Karma/V-Ray/RenderMan mostram render
(medido nos UsdRenderers.json de cada um) -- entao GL mostra o proxy
chapado de cor e o delegate mostra o shader; e' o desenho do USD.

Extra: sop.layoutChildren() no fim da montagem da geometria -- os nos
criados por codigo nasciam empilhados ("fica bagunçado").

## Two-Sided sem textura de verso: espelha a da frente (2026-09-12)

O Matheus marcou o box no Zea e nada foi criado. Certo pelo codigo de
ontem (so agia com <Parte>_Back, e Maxtree nao tem), errado pelo video:
o Jonas monta o 2Sided da folha com a MESMA textura dos dois lados.
_funde_verso agora, alem de fundir _Back reais, espelha
back_basecolor=basecolor nas partes de folha (mesmo criterio do caminho
V-Ray: nome de folha OU mapa de translucency). Medido no Zea com o box:
Leaf_01-04, Bud_01-03 e Flower_01 ganham twosided (Karma) e Mtl2Sided
(V-Ray); Fruit e Trunk seguem de um lado so. No V-Ray isso TROCA o
modelo da folha de thin-walled+SSS para o 2Sided do video (translucency
no slot do 2Sided, thin-walled fora).
