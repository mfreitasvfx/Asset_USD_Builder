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

## Cor randomica do proxy: viva e legivel, nao so randomica (2026-09-12)

O Matheus reclamou do esquema de cor do proxy. MEDIDO antes de mexer:
(a) o pipeline funciona ponta a ponta -- o USD exportado tem
displayColor no proxy (detail Cd vira constant); (b) o hash do Color
SOP 'Random from Attribute' VARIA por nome, inclusive nomes parecidos
(01_04 magenta, 01_05 azul); (c) a alternativa VEX
rand(random_shash()) COLIDE em nomes parecidos -- descartada; (d) o
defeito real: RGB arbitrario sai escuro/lamacento (Building_01 deu
(0.19, 0.03, 0.05), quase preto -- parece proxy sem cor no GL).

Conserto: wrangle nice_color depois do color1 -- rgbtohsv, mantem o
matiz (e' ele que distingue os assets) e sobe saturacao para
fit(0.55..0.95) e brilho para fit(0.60..0.95). Medido no chain real:
01_04/05/06 e Building_01/02 todos vivos e distintos.

## Subnet com o nome do asset, sem prefixo (2026-09-12)

Pedido do Matheus: o subnet em /stage leva o nome do asset que esta
importando (MT_PM_V93_Zea_mays_01_04), nao mais USD_Builder_Asset_<...>.
Armadilha MEDIDA no caminho: o auto-rename do Houdini incrementa o
digito final, e um REBUILD do Zea_01_04 nascia como "Zea_01_05" --
nome de outro asset real. Dedup explicito: segundo build do mesmo
asset vira <nome>_1, _2... Mensagens da janela atualizadas.

## Subnet nomeado pelo FBX (2026-09-12, cont.)

Ajuste do pedido anterior: "o nome do subnetwork tem que pegar o nome
do fbx". Pasta-e-asset (Maxtree/Megascans): subnet = nome do ARQUIVO
(MT_PM_V93_Zea_mays_01_04_High); KitBash (asset_grain=object, arquivo
"1.fbx" com dezenas de assets): continua o nome do OBJETO. A resolucao
do geo_path subiu para antes do subnet -- de quebra, asset sem
geometria nao deixa mais subnet vazio em /stage. Prim/USD seguem com o
nome do asset (so o subnet muda). Rebuild do mesmo fbx: _High_1.

## Two-Sided no RenderMan (2026-09-12, cont.)

Pedido do Matheus: ligar o double-sided do RenderMan como nos outros
tres renderers. O conversor KB3D nao tem nada de RenderMan (conferido
nos scripts dele); o jeito oficial e o do proprio PxrSurface (Args do
RMan 27.3): diffuseDoubleSided + specularDoubleSided; verso espelhado
(box Two-Sided sem _Back real) usa diffuseBackUseDiffuseColor=1 (sem
segunda leitura de textura); _Back real entra por diffuseBackColor
(BackUse=0). Medido no Zea com o box: 8 partes de folha double-sided,
Fruit/Trunk de um lado so. O caminho de folha ja ligava
diffuseDoubleSided; agora o box tambem age, com o par especular.

## Multi-versao: Arnold no 22, RenderMan no 21, V-Ray no 20.5 (2026-09-13)

Ideia do Matheus, MEDIDA antes de opinar. Build completo do Zea no
20.5.410 + vfh 7.00.10: 6 partes, zero avisos, e o leaf do V-Ray
conectou translucency_color (o slot que o 7.10/H21 removeu) -- o
build_vray adaptativo fez o certo sozinho. Fallbacks agiram: sem Labs
no 20.5, delete_small_parts e' pulado; lowres_geo::1.1.1 existe nos
prefs do 20.5 (origem dele).

Mapa medido das versoes:
- H22.0.368: Arnold (+Karma). vfh e RfH nao existem p/ 22.
- H21.0.596: RenderMan + Karma + V-Ray 7.10 (sem translucency_color).
- H20.5.410: V-Ray 7.00.10 COM translucency_color (+Karma). RfH exige
  20.5.684 (instalados: .410/.584) -- RenderMan nao roda no 20.5.
  ATENCAO: vfh 20.5 so' suporta ate' 20.5.445 -- usar o .410, nao .584.

Pegadinhas do fluxo: o json do vfh 20.5 esta' com INSTALL_ROOT
placeholder (nunca registrado; rodei com copia corrigida via
HOUDINI_PACKAGE_DIR); shelf precisa ser copiada p/ houdini20.5 e 22;
cada versao escreve SEU USD (nenhuma versao tem os 4 renderers --
export final continua 21 + passada Arnold no 22); preset .cpio de
V-Ray salvo no 20.5 pode nao bater 1:1 nos nos do 7.10.

## Instalacao multi-versao feita (2026-09-13, cont.)

O Matheus aprovou o fluxo Arnold@22 / RenderMan@21 / V-Ray@20.5 e pediu
a instalacao do que faltava + o MT_AssetLibrary (projeto irmao em
C:/dev/MT_AssetLibrary, package proprio) nas outras versoes.

Instalado e VERIFICADO por hython (so com os prefs, sem env na mao):
- houdini20.5: vray_for_houdini_20.5.json (o json da Chaos estava com
  INSTALL_ROOT placeholder -- nunca registrado), zz_MT_AssetLibrary.json,
  shelf+svg. Verificado: VRayNodeBRDFVRayMtl ok, translucency_color
  CONECTAVEL, lowres_geo ok (copia sipi- ja existia), MTAL env ok.
  Labs ausente no 20.5: delete_small_parts e' pulado (fallback).
- houdini22.0: shelf+svg, zz_MT_AssetLibrary.json, otls/
  sop-lowres_geo-1.1.1.hda (nao existia). Verificado: Arnold 7.5.3
  registra, labs ok, lowres_geo ok, MTAL env ok. vfh nao existe p/ 22.
O botao do MT se pendura sozinho na shelf USD_Builder no primeiro boot
com UI (uiready.py, libs cobrem py3.10-3.13). A Asset Gallery e' o
asset_gallery.db DENTRO da pasta de saida -- viaja com os assets,
qualquer versao abre pelo pane Layout Asset Gallery -> Data Source.

## Campo Textures na janela + parser BigMediumSmall (2026-09-13, cont.)

Pedido do Matheus vendo o CP_Vehicles (BigMediumSmall cyberpunk): a
geometria mora em FBX+OBJ/... e as texturas em Textures/... (fundo
demais pra subida automatica de 3 pais) -- o scan dava 0 partes.

1. Campo "Textures (optional)" ABAIXO do Asset Folder, mesmo esquema de
   memoria (combo editavel, recentes proprios em
   usd_builder_asset_recent_tex.json, max 8), comeca VAZIO (opcional
   nao se auto-preenche). library.scan(root, tex_dir=) COMPLEMENTA as
   partes com a pasta indicada (profundidade 3; papel ja achado so' cai
   por peso maior). Log avisa quantas partes novas entraram.
2. Parser: token final de FORMATO ('CPTaxiRoof_normal_png.png') virava
   parte falsa <Parte>_png com a normal orfa. _FMT_RE derruba
   png/jpg/tga/tif/exr/bmp no fim do nome de parte.

MEDIDO no pacote real: 0 partes sem o campo -> 103 partes com ele,
todas com normal no lugar (112 com fantasmas antes do parser).
Biblioteca segue "desconhecida" (perfil generico) -- perfil proprio
BigMediumSmall fica para depois do primeiro build visual.

## CP_Vehicles por inteiro + preview + UI (2026-09-13, cont.)

Quatro pedidos do Matheus no teste do BigMediumSmall:

1. "Nao monta todos os shaders" -- MEDIDO: as texturas dos veiculos sao
   EMBUTIDAS no FBX; o Houdini extrai p/ <arquivo>.fbm na primeira
   importacao (por isso o scan de ontem dava 0). Alem disso os materiais
   tem ESPACO no nome ('vh_cp_glass car') e as texturas rabo _Bake1_PBR.
   Consertos: _BAKE_RE tira o rabo, espaco vira '_' no nome da parte
   (casa com o prim USD do subset), e library.parts_for_file(asset, fbx)
   devolve as partes do .fbm do arquivo -- o modo multifbx da janela usa
   as partes DO ARQUIVO quando existem (o list_assets_in_file roda antes
   e ja extrai o .fbm na primeira vez); sem .fbm cai no atlas (PA).
   PROVA: cp_vh_car_A com 6/6 bindados (glass/trim inclusive), 0 missing.
2. usdpreviewsurface EXPLICITO em todo material (build_preview, copia do
   MatLib do HDA: UsdUVTexture cor sRGB + opacity raw -> preview no
   collect). Sem ele so' build com Karma/MtlX aparecia no GL. Terminais
   conferidos no USD: outputs:kma:surface + outputs:vray:surface +
   outputs:surface juntos. O atalho "karma sozinho sem collect" saiu.
3. Janela nao encolhia: combos com caminho comprido ditavam a largura
   minima -- AdjustToMinimumContentsLengthWithIcon + comprimento 24.
4. Botoes OPEN (esquema do Asset_USD_Builder) nos tres campos de pasta.

AVISO ambiente: o vray_for_houdini_21.0.json APARECEU movido p/
packages/bkp hoje 17:47 (nao foi a ferramenta); restaurado e conferido.

## O OPEN aparecia vazio: px fixo x Global UI Size (2026-09-13, cont.)

"ta faltando no nosso" (screenshot do HDA do Carlo ao lado da nossa
janela): os tres botoes OPEN existiam, mas saiam VAZIOS na tela do
Matheus.

CAUSA MEDIDA (nao era a fonte, era o tema + a escala):
  - ui.pref do Matheus: general.ui.scale := 1.5 (no 21.0 e no 20.5)
  - $HFS/houdini/config/Styles/base.qss:426 poe
    QPushButton { padding-left: @15px@; padding-right: @15px@; }
    e esses tokens sao multiplicados pelo Global UI Size -> 22px de cada
    lado na escala 1.5, 44px de padding dentro de um botao de 48px
  - sobrou 4px para a palavra: o Qt nao elide, CLIPA centralizado, e o
    botao fica vazio. Provado em PNG por tamanho de fonte x escala
    (1.00 mostra "PE", 1.25 meia letra, 1.50 nada).

CONSERTOS (nenhum px fixo decide mais largura/altura):
  - _bt(): largura = max(sizeHint, texto na fonte corrente + 36*escala).
    Medido na escala 1.5: OPEN precisa 92px, ficou 100; "..." precisa
    61, ficou 69. Nas tres versoes (20.5/PySide2, 21, 22) monta igual.
  - _S(n) = hou.ui.scaledSize(n) com fallback headless; aplicado no
    resize inicial, nos setMinimumHeight (34/26) e no width dos botoes
    de spinbox no qss (px de stylesheet nao escalam sozinhos).
  - A janela nunca nasce maior que a tela (na escala 1.5 os 760 de
    altura viravam 1140).
  - _bt_icone(): botao de escolher pasta com o icone nativo
    BUTTONS_chooser_folder (receita do FileChooserButton da SideFX),
    com canCreateIcon/isNull checados e fallback "..." sem GUI.

JANELA QUE ENCOLHE (a queixa antiga, agora medida de verdade):
  minimo era 852x811 na escala 1.5. Quem mandava: rotulo comprido de
  checkbox ("Asset Gallery on export (...)" sozinho pedia 588px) e a
  linha Thumbnail (4 spinboxes). Rotulos encurtados com a explicacao no
  tooltip -> 791; cada aba dentro de um QScrollArea -> 151x206.

PARIDADE COM O HDA (medido no
Carlo_Jongen__Asset_USD_Builder__2.1.otl): a linha dele e' so' um parm
"type directory" + um button "OPEN" com joinnext; o triangulo e o icone
de pasta o Houdini desenha de graca, e o menu do triangulo sai de
$HOUDINI_USER_PREF_DIR/dir.history (secao DIRECTORY). Entao:
  - _hist_houdini() le esse mesmo dir.history e completa os nossos
    recentes -- as pastas que ele usa no Houdini aparecem no triangulo
    da nossa janela;
  - Output Folder virou combo editavel com memoria propria
    (usd_builder_asset_recent_out.json), como os outros dois campos;
  - auto-preenchimento so' com a memoria NOSSA: uma pasta de saida
    vinda do historico geral do Houdini seria pedir export no lugar
    errado.

## Unit Scale: o campo manda no convert_units (2026-09-14)

Decisao do Matheus: o valor do convert_units sai do CAMPO da janela, com
padrao 0.01; quando o pacote ja' vem em metros ele mesmo poe 1. Nada de
perfil decidindo escondido.

  - houdini_panel: Unit Scale nasce em 0.01 e o valor vai SEMPRE para o
    over (antes so' ia quando > 0, e com 0 o perfil entrava por baixo com
    0.01 -- era esse o "valor no transform" que aparecia sem ele pedir).
  - Conferido no H21 pelo caminho da janela: campo 1 -> convert_units 1;
    campo 0.01 -> convert_units 0.01.

MEDIDO no caminho (fica registrado, mas a escolha continua sendo dele):
  BigMediumSmall  carro 5.358 un = 5,36 m   -> ja' em metros, pede 1
  Maxtree V93     soja 48.26 un  = 48 cm    -> centimetros, 0.01
  KitBash3D       set 23264 un   = 232 m    -> centimetros, 0.01
                  (o OBJ do MESMO set mede exatamente 1/100 do fbx)
O UnitScaleFactor gravado no FBX mente nas tres, entao nao da' para
decidir pelo header. O CP_Vehicles exportado com 0.01 saiu 100x menor
(extent 0.0536 m) e precisa ser refeito com 1 -- a escala fica assada
nos pontos, nao da' para consertar num xformOp depois.

PROCESSO (recado dele nesta rodada): fazer SO' o que foi pedido, e
bateria longa de teste antes de entregar deixa o trabalho lento. Perfil
proprio do BigMediumSmall, deteccao automatica de biblioteca e medicao
de tamanho no export foram invencoes minhas nesta rodada e sairam.

## Os tres setups do teste_proxy.hip viram a base (2026-09-14)

O Matheus montou tres setups em Testes/teste_proxy.hip e disse "serao
nossa base". Lidos no a no; o que a ferramenta monta agora:

COMUM AOS TRES: labs::delete_small_parts abre os ramos e o proxy fecha em
color (class Detail, colortype Random, seed = EXPRESSAO
nprims(opinputpath(".",0)) -- o pedido dele de usar a contagem de prims
como seed) -> attribdelete asset_name -> add Remove Unused Points.
Saiu o esquema antigo (set_color_data + Color 'from Attribute' +
nice_color HSV + attribpromote): o seed por contagem substitui tudo isso.

PROXY POR ESTILO (profile.proxy_style):
  plant  Maxtree   lowres_geo::1.1.1 2% -> fuse tol3d 0.0175
  boxes  KitBash   connectivity(prim) -> compile+foreach por peca ->
                   bound -> fuse 0.02 -> normal -> clean fixoverlap
  vdb    default   vdbfrompolygons -> convertvdb(poly) ->
                   remesh 0.1949 -> polyreduce 31.53% -> normal
SIMPROXY: plant/boxes = assemble -> convexdecomposition -> attribdelete
class -> add; vdb = shrinkwrap -> normal -> add. No boxes ele sai do
clean1 do proxy, como no Building_01.
delete_small_parts: plant mode Perimeter/2.39; boxes 0.2; vdb 0.3 (Area).

ARQUIVO PRONTO EM DISCO (pedido: "se tiver proxy e simproxy com o mesmo
nome ele cria um unico file"): a convencao medida e' pasta-irma, nao
sufixo -- <dir>/1.fbx, <dir>/proxy/1.fbx, <dir>/simproxy/1.fbx, mesmo
nome. library.proxy_prontos() acha, e o builder monta SO' um File SOP por
ramo (10 nos em vez de 27, medido no Building_01). O checkbox "force" na
aba SETTINGS monta a rede de novo mesmo com o arquivo la'.

ROP FBX PROCEDURAL (pedido: "puxar o mesmo nome do arquivo de file"):
quando a rede e' montada, cada ramo ganha um rop_fbx com sopoutput por
EXPRESSAO PYTHON derivada do fbx_in --
    os.path.dirname(p) + "/proxy/" + os.path.basename(p)
(HScript nao tem basename/dirname: medido, as duas devolvem string vazia
sem erro). Assim o ROP escreve onde o SCAN seguinte vai procurar.
ATENCAO: o nome vem do ARQUIVO, como ele pediu. Num fbx com VARIOS assets
(KitBash de 28 objetos) todos escreveriam no mesmo proxy/<arquivo>.fbx --
para esses, ou se exporta um por vez, ou o nome teria que vir do asset.

BUG ACHADO NO CAMINHO: o SCAN estava listando proxy/1.fbx e
simproxy/1.fbx como se fossem assets -- o build montou um asset chamado
"convexdecomposition2" (o nome do no' de onde o rop_fbx2 dele exportou).
As duas pastas entraram em library._IGNORAR; a lista do Post Apocalypse
voltou de 66 para 64 arquivos.

LAYOUT: o que estava bagunçado era /stage, nao o miolo (as 9 chamadas de
layoutChildren ja' cobrem subnet, sopnet, matlib e cada builder de
material). moveToGoodPosition() nao resolvia porque posiciona pelas
CONEXOES e os subnets de asset nao se ligam entre si -- num lote todos
caiam no mesmo ponto. Agora cada asset novo procura a primeira posicao
livre numa grade de 6 colunas, sem tocar no resto da cena.

NAO replicado de proposito: o blast de limpeza do Building_01 ("pode
ignorar o clean_geo blaster, so fiz para remover uns elementos") -- sao
ranges de primitiva fixos daquele fbx.

## Cor do proxy e nome do proxy por asset (2026-09-14, cont.)

1. "mesmo colocando cor no proxy ele e' sobrescrito pelo usd preview":
   MEDIDO -- o bind ia para /ASSET/geo (raiz) quando o asset tem material
   unico, e binding no USD DESCE por toda a subarvore: /geo/proxy/add1
   herdava o material e o UsdPreviewSurface ganhava do displayColor.
   Prova no Building_01: o prim do proxy tinha cor 0.617/0.974/0.473 e
   ainda assim aparecia com o shader.
   Conserto em _bind_parts: a raiz do bind passa a ser /ASSET/geo/render
   quando ha branches (single) e /ASSET/geo/render/*/<parte> no
   multi-material; sem branches continua /ASSET/geo e /ASSET/geo/*/<parte>.
   Depois: /geo/render com o material, /geo/proxy/add1 com
   ComputeBoundMaterial = NENHUM e a cor intacta. Binds sem regressao --
   Zea (multi, com branches) 2/2 e CP_Vehicles (sem branches) 6/6.

2. Nome do proxy quando o fbx tem VARIOS assets (pedido dele): o painel
   passa proxy_base = nome do asset quando list_assets_in_file devolve
   mais de um (ou quando a lista de objetos tem mais de um); com um asset
   so' continua o nome do arquivo, como estava.
     proxy_base=None         -> <dir>/proxy/1.fbx
     proxy_base=Building_01  -> <dir>/proxy/Building_01.fbx
   library.proxy_prontos(geo, base) procura pelo mesmo nome.
   Bug pego no caminho: dentro de _branches a variavel 'base' ja' era o
   NO' da cadeia (delete_small_parts1) e engolia o parametro com o nome
   -- o ROP saia gravando 'delete_small_parts1.fbx'. Parametro renomeado
   para nome_base.

## Megascans: plantas (3dplant) e objetos (3d) (2026-09-14, cont.)

Pedido: construir plantas e objetos do Megascans como ja' se constroi o
resto, com os quatro renderizadores. Medido antes de mexer:

BUG CENTRAL -- .abc: o File SOP le Alembic PACKADO (1 prim AlembicRef, sem
name e sem shop_materialpath). Sem 'name' o componentgeometry autora
/ASSET/mesh_0,1,2 como IRMAOS de /ASSET/geo, e binding no USD so' desce
pela subarvore: o bind ficava em /geo e as malhas saiam com
ComputeBoundMaterial = NENHUM -> cinza nos quatro renderizadores. E
parts_bound MENTIA ('wmfiaaldw' listado como ligado). Metade da biblioteca
3d do Megascans (82 pastas) so' tem .abc, e nas plantas o .abc ainda ganha
do .fbx por peso. Conserto: um `unpack` depois do File SOP quando a
geometria e' .abc. Depois: /ASSET/geo/shape + GeomSubset, material
efetivo em todas as malhas.

PLANTAS -- as 12 variacoes: uma fern tem 12 Var x 5 LOD x 2 formatos = 120
arquivos, e asset.geometry e' um dict lod->caminho (5 slots): 11 plantas
iam pro lixo caladas. Agora library.variacoes() devolve {Var: {lod:
caminho}}, a janela entra em modo 'variacoes' e lista Var1..Var12; cada
uma vira um asset <pasta>_<Var>, com nome_asset (que NAO liga o blast de
extracao -- o arquivo da Var ja' tem so' aquela planta).

MATERIAIS FANTASMA no Megascans: o scan da fern devolvia 3 partes --
'vmkpdbeia' (o Atlas, certo), 'Billboard' e 'vmkpdbeia_convert'. A
segunda vem de Textures/Billboard, que so' serve para o cartao do ultimo
LOD (medido: LOD4 tem bbox Z=0.0000 e 5 prims, e o UV e' o enquadramento
1:1 de uma foto); o HDA do Carlo tambem descarta. A terceira vem de
'vmkpdbeia_4K_Albedo_convert.jpg', sobra do nosso proprio pipeline.
Agora: 'billboard' em _IGNORAR e _CONVERT_RE derruba _convert/_raw/
_acescg/_srgbtex. A fern passou de 3 partes para 1, sem aviso perdido.

CONFERIDO (H21, karma+renderman+vray no mesmo material):
  fern Var1 (.abc)      1 malha, material efetivo, 0.492 x 0.217 x 0.500 m
                        -- bate com as Dimensions do vmkpdbeia.json
  building LOD2 (.abc)  1 malha, material efetivo, 4.000 x 4.250 x 1.977 m
  terminais nos dois: outputs:surface + kma:surface + kma:displacement +
  ri:surface + ri:displacement + vray:surface
  janela: SCAN lista as 12 variacoes, BUILD monta 3dplant_fern_..._Var1

ARNOLD: nao entra porque o packages/htoa.json esta em
Documents/houdini21.0/packages/bkp/htoa.json (movido em 10/09 11:35, o
mesmo que tinha acontecido com o vray_for_houdini_21.0.json). O
HTOA_ROOT que ele aponta existe e funciona -- medido: com esse caminho no
HOUDINI_PATH o arnold_materialbuilder carrega e o builder monta o ramo
Arnold sem erro. Nao mexi nos packages.

Diferencas conscientes em relacao ao HDA do Carlo: ele faz 1 USD por
asset com variantSet 'geo' contendo todas as Var (nos: 1 USD por Var,
que e' o fluxo de lista da janela) e monta UM renderizador por build
(nos: os quatro no mesmo material, que e' o pedido).

## Proxy setup escolhido na janela (2026-09-14, cont.)

Pedido: "embaixo do proxy cria opcoes para caso eu decida qual setup de
proxy criar lowres, vdb e bounds, que seria essa ordem. todos no mesmo
esquema de rop fbx e import".

  - Combo "Proxy setup" na aba SETTINGS, logo abaixo de Branches, com os
    tres na ordem pedida: lowres (lowres_geo 2%), vdb (remesh + reduce),
    bounds (caixa por peca).
  - Os estilos passaram a se chamar assim no codigo tambem (eram 'plant'
    e 'boxes'): perfil maxtree = lowres, kitbash = bounds, resto = vdb.
  - O SCAN marca no combo o estilo do perfil e o que ficar la' e' o que o
    BUILD monta -- mesmo esquema que ele pediu para o Unit Scale (o campo
    mostra o valor e o campo manda).
  - Os tres ja' tinham, e continuam com, o par rop_fbx (grava
    <dir>/proxy e /simproxy com o nome do arquivo ou do asset) + File SOP
    quando o arquivo ja' existe. Conferido pela janela nos tres:
      lowres 20 nos, vdb 22, bounds 27, todos com rop_fbx_proxy e
      rop_fbx_simproxy.

## RenderMan no Material Builder oficial (2026-09-18)

"criei um megascan com renderman mas ele nao esta no subnet do renderman;
existe vantagem ou desvantagem? porque eu nao consigo criar os nodes por
mim mesmo" + "coloca ele em metallic_workflow" + "garante que todos os
setup de renderman tenham double sided".

MEDIDO: o TAB do Houdini filtra os VOPs pelo render mask do container.
pxrsurface e pxrmaterialbuilder tem mask 'RIB'; o subnet generico da
ferramenta (ctx_subnet com rendercontext 'ri') tem mask VAZIA -- por isso
dentro dele o TAB nao lista Pxr* nenhum e ele nao conseguia criar no' a
mao. Era essa a desvantagem; no USD os terminais saiam iguais.

O QUE MUDOU em mat_extra.build_renderman:
  - container = pxrmaterialbuilder (RenderMan Material Builder). Por
    dentro vem um output_collect: pxrsurface no input 0, pxrdisplace no
    input 1; o builder expoe 'surface'/'displacement' e o collect
    externo da ferramenta liga os dois como antes. O preview_surface
    automatico do builder NAO toma o outputs:surface do nosso
    preview_<parte>: medido nas duas ordens no collect, outputs:surface
    fica com o usdpreviewsurface nosso.
  - PxrMetallicWorkflow SEMPRE: basecolor_cc -> baseColor; metalness
    (quando existe) -> metallic, senao fica no default 0; diffuse/
    specularEdge/specularFace do PxrSurface vem do workflow. Specular map
    entra no workflow tambem.
  - diffuseDoubleSided=1 e specularDoubleSided=1 em TODO PxrSurface, nao
    so' nas folhas/back (esses continuam ligando transmit / backcolor).

CONFERIDO no H21 (renderman+karma): Megascans building sem metalness e
Zea 12 materiais -- todos pxrmaterialbuilder, dds=sds=1, metallic_workflow
presente e alimentando o diffuseColor; USD com ri:surface,
ri:displacement (quando ha' height), kma:* e outputs:surface do preview.
presets.py identifica o builder pelo NOME (renderman_*), entao os presets
salvos continuam valendo.

## Variantes de geometria: um USD por arquivo com Var por objeto (2026-09-21)

Pedido: o Maxtree Vol 148 traz VARIAS palmeiras num fbx
(MT_PM_V148_Acrocomia_aculeata_01.fbx = 6 objetos) e o Matheus quer o
setup do Component Builder (Flower Perenial): N componentgeometry ->
componentgeometryvariants -> componentmaterial -> componentoutput, um USD
so' com variantSet 'geo'.

MEDIDO no fbx: 6 objetos por `name`; o `MaxHandle` que ele sugeriu
particiona igual (1:1), mas o name da' o nome legivel da variante, entao
o corte continua por name. 1.9M prims, cm (5381 un -> 0.01), 8 materiais
compartilhados. geovariantname do componentgeometry = `$OS`: a variante
chama-se como o no'.

IMPLEMENTADO (build_asset(geo_variants=[...])):
  - o primeiro objeto e' o componentgeometry normal; os outros sao
    hou.copyNodesTo do mesmo (branches/unit/center iguais) com o blast
    keep_* apontando para o objeto da vez; todos entram num
    componentgeometryvariants 'variants'.
  - BIND: um componentmaterial POR variante, ANTES do variants. Medido
    primeiro com um so' depois: ele autora caminhos concretos da
    variante ativa no export e as outras 5 saiam sem material (0/6). Com
    assign_1..6 antes do variants, 6/6 subsets com material em todas.
    Cada assign liga TODAS as partes com textura (Leaf_02 existe na
    palmeira 03 e nao na 01); padrao que nao casa e' inofensivo.
  - Janela: checkbox "Geo variants (one asset per file)" na aba SETTINGS,
    default OFF. No modo multi-FBX, ligado, cada arquivo com mais de um
    objeto vira UM asset (nome do arquivo) com as variantes; desligado
    continua um asset por objeto (6 builds, como antes).

CONFERIDO: Acrocomia -> variantSets ['geo','mtl'], 6 variantes, alturas
7.46..15.93 m, 6/6 (ou 5/5) subsets com material em cada uma; Zea sem
variantes inalterado (6 bound). Build de 23 s sem branches (1.9M prims).
Proxy pronto em disco por asset (proxy_base) nao se aplica no modo de
variantes -- as copias apontam para o mesmo arquivo.

## Multi-fbx Maxtree: partes do PROPRIO arquivo, nao o atlas (2026-09-21)

"nao montou o render certo: geometria Acrocomia, material
renderman_MT_PM_V148_Brahea_moorei_01_Leaf_01". No modo multi-FBX sem
.fbm o build caia em atlas_material(), que e' a regra do Post Apocalypse
(um atlas para todos os arquivos) -- no Vol 148 isso entregava a
primeira planta da lista (Brahea) para todas. parts_for_file agora, sem
.fbm, filtra asset.parts pelo prefixo do nome do arquivo
(MT_PM_V148_Acrocomia_aculeata_01 -> ..._Leaf_01, ..._Trunk_01): 9 partes
proprias; Post Apocalypse continua None -> atlas. Conferido pela janela:
'6 assets, 9 own texture parts', nenhum Brahea na matlib.

## Planta pelo que se achou + V-Ray 7.10 sem translucency_color (2026-09-21)

1. "tem transmission mas nao montou como ele; era plant e nao
   identificou": a.plant era calculado com os arquivos da PASTA (so' fbx
   no Vol 148) antes de _sobe_por_texturas -- as texturas moram um nivel
   acima. Agora, depois de coletar, a.plant = a.plant or 'translucency'
   in a.roles(). V148 -> planta: sim; CP_Vehicles segue nao.
2. Setup do Matheus no V-Ray da versao SEM mascara de cor (7.10/H21),
   copiado das telas dele para build_vray, so' no ramo sem o input
   translucency_color:
     Type SSS (translucency='6'), Method Directional
     (translucency_surfaceLighting='0'), Radius = fog_color 1 1 1,
     Scale (cm) = fog_mult 1, Color = translucency_color HSV(84,0.781,0.5)
     = (0.3438, 0.5, 0.1095) fixa, mapa de translucency entrando como
     AMOUNT por TexRemap 0.2..1 (translucency_amount conectado), e
     glossiness_remap 0.2..0.9. fog_color_tex nao e' mais ligado.
   O ramo 7.00 (H20.5, com translucency_color conectavel) ficou como era.
   Conferido no Zea/H21: Leaf_02 Type=6 Method=0 cor (0.344,0.5,0.11)
   amount<-translucency_remap 0.2..1, gloss 0.2..0.9; Trunk_01 sem SSS.

## leaf_controls: um null na matlib para as folhas do V-Ray (2026-09-21)

Pedido: "cria um null no material library para controlar o
glossiness_remap output min/max; color translucency + translucency_remap
min/max; basecolor_cc; isso somente para leaf".

mat_extra._controles_folha(parent): null 'leaf_controls' criado na
primeira folha do build (um por materiallibrary), com spare parms
gloss_min/max (0.2/0.9), transl_color (HSV 84/.781/.5), transl_min/max
(0.2/1), cc_saturation, cc_hue_shift, cc_hue_tint, cc_tint_strength,
cc_brightness, cc_contrast (defaults do V-Ray ColorCorrection). Nos
vray_<folha> os parms apontam por expressao ch("../../leaf_controls/..").
Somente no ramo de folha (plant + translucency/eh_folha); Petiole, Thorn
e Trunk continuam com valores literais. O ramo 7.00 (translucency_color
conectado) recebe gloss + basecolor_cc; cor/remap da translucency so' no
7.10. Conferido no Vol 148/H21: 1 null, 3 folhas seguindo (mexi
gloss_max/saturation/transl_color e as tres mudaram), Petiole sem expr.

Nota: a pasta de teste MaxToLama/Testes/v04/MT_PM_V93_Zea_mays_01_04
nao existe mais -- os testes de folha passaram a usar o Vol 148.

## Lote: pasta de .max -> um FBX por arquivo (2026-09-21, noite)

Pedido: "um plugin do max para exportar fbx [da pasta MT_PM_V93] ... quero o
display de uma lista".

- `batch.py` (sem UI): `list_max_files`, `preview_of` (o .jpg ao lado),
  `target_of`, `export_files(paths, settings, on_progress)`. Abre cada .max
  com `loadMaxFile useFileUnits:true quiet:true`, roda o MESMO
  `exporter.export`, segue no erro. Forca selection_only=False,
  one_asset_per_object=False, asset_name="" -- as prefs da janela principal
  nao vazam. Escreve `<destino>/_usd_builder_asset_lote.json`.
- `ui/batch_window.py`: pasta de origem, QListWidget com checkbox + thumb do
  preview, filtro por nome, Todos/Nenhum/Inverter (so' no visivel), destino,
  "Ver o que vai sair", "Exportar marcados" com QProgressBar, confirmacao
  antes (abrir o .max descarta a cena atual). Pasta de origem lembrada em
  `Settings.batch_source_dir` (campo novo; a janela principal ignora).
- `install/usd_builder_asset_batch.ms` abre a janela; `tools/batch_smoketest.py`
  e' o teste pelo 3dsmaxbatch (lista + janela + export real dos N primeiros).

Medido (Python do Max 2027 + pymxs falso, Qt platform `windows`): 132 .max
listados, thumbs carregam, filtro "allium" = 9, export de 3 com 1 falha
simulada -> 2 ok / 1 erro / lote continua, relatorio escrito.
NAO medido: o export de verdade dentro do Max -- o `3dsmaxbatch` imprime o
cabecalho e nunca lanca o 3dsmax.exe enquanto ha' sessao interativa aberta
(duas do Matheus abertas; esperei 11 min). Rodar o smoketest com o Max
fechado, ou abrir a janela no Max e exportar 2 marcados.

Armadilha: o PySide6 do Python do Max nao tem o plugin `offscreen`
(QApplication morre com exit 127, sem mensagem). Fora do 3dsmaxbatch, usar
QT_QPA_PLATFORM=windows.

## Build em contexto SOP: nos comuns, sem subnet (2026-09-25)

Pedido: "export em sop context que exporta do mesmo jeito que o
megascan, mas em vez de criar um subnet ele cria um node comum,
identificando o contexto aberto se e' em sop ou lops".

  - A cadeia de geometria saiu do build_asset para _rede_geometria()
    (fbx_in -> [unpack .abc] -> [keep/clean] -> center_to_origin ->
    convert_units -> default + branches com rop_fbx/File pronto). Ela
    exige tres nos default/proxy/simproxy no parent: em LOP sao os
    outputs do componentgeometry, em SOP viram NULLS com as cores do
    Component Builder.
  - builder.build_sop(asset, profile, parent_sop, ...): monta isso
    direto no SOP, mais uma matnet 'mtl' ao lado com os MESMOS builders
    de material (sao VOPs, valem em /mat) e um wrangle assign_materials
    que troca o shop_materialpath do fbx (so' o nome) pelo caminho do no
    na matnet -- o Material SOP faria o mesmo, por grupo.
  - Janela: _contexto_sop() le hou.ui.paneTabOfType(NetworkEditor).pwd();
    se o childTypeCategory e' Sop, o BUILD chama build_sop (log "context:
    SOP /obj/x") e o EXPORT aperta os rop_fbx (proxy/simproxy); senao
    continua o subnet em /stage. Nada de checkbox: o contexto decide.
  - Conferido no Zea/H21: 20 nos no /obj/zea_sop, 12 materiais na
    matnet, shop_materialpath resolvendo para nos existentes, proxy 238
    prims / simproxy 5082, rops gravando em <dir>/proxy|simproxy/; o
    build LOP do mesmo asset segue com 18 nos no sopnet.

## 2026-09-26 — botão Cache_hython na shelf USD_Builder
Ferramenta externa ao projeto, mora em `C:\dev\hou_batch_cache` (shelf_tool.py
na GUI, hython_cache.py no hython). Grava o File Cache/ROP selecionado fora
da GUI e opcionalmente fecha o Houdini. Só o `<tool>` e o `<memberTool>` estão
em install/usd_builder_asset.shelf; a shelf viva em Documents/houdini21.0 foi
editada igual.

## Aba SOP LEVEL: containers por asset, em geo novo ou dentro do geo (2026-10-22)

Pedido (Matheus, ja' no Linux): "continuar construindo em SOP level...
uma aba SOP level, para construir no geo ou dentro do geo. Cada node tem
que ter seu material container com os nodes dentro; a geometria a mesma
coisa, com os nodes dentro de escalar, split e centralizar. Por enquanto
nao mexer em proxy, focar na geometria e materiais."

  - builder.build_sop(asset, profile, parent, modo="geo"|"inside", ...)
    substitui o build_sop de 2026-09-25 (nos soltos no geo aberto). Agora
    cada asset sao QUATRO nos:
        geometry          subnet SOP: fbx_in -> [unpack] -> [keep/clean]
                          -> center_to_origin -> convert_units -> output
                          'default' (outputs proxy/simproxy so' nascem se
                          o perfil pedir os branches)
        mtl               matnet com os MESMOS builders (karma_/vray_/
                          preview_ + collect <parte>, leaf_controls)
        assign_materials  wrangle: shop_materialpath -> <mtl>/<parte>
        default           null de saida, verde do Component Builder,
                          display+render
    modo "geo": nasce /obj/<asset> (dedup explicito _1, _2 -- a armadilha
    do auto-rename). modo "inside": tudo dentro do SOP aberto com o
    prefixo <asset>_ (rebuild vira <asset>_1_...).
  - Matnet aninhado em matnet NAO existe (medido: "Invalid node type
    name"); por isso o container de material e' o matnet do asset, nao
    um por parte.
  - rebuild_materials aceita o matnet (sem o multiparm 'materials'):
    UPDATE MATERIALS vale para os builds SOP.
  - Janela: aba SOP LEVEL (Target: New geo node / Inside the geo open in
    the network editor + BUILD SOP). O BUILD da aba USD BUILDER voltou a
    ser SEMPRE /stage -- a bifurcacao implicita pelo contexto do editor
    de rede saiu (a aba e' explicita). _preparar() e' a leitura comum da
    janela (perfil, alvos, renderers, settings) para os dois builds.
    No SOP level os proxies ficam desligados (copia do perfil).
  - Medido (hython 22.0.476, Zea): 12 materiais, 6 shop_materialpath do
    fbx resolvendo para nos existentes, bbox 2.05 m de altura com 0.01;
    Karma ROP de /out renderiza as texturas (folhas, caule, opacity) --
    o SOP Import LOP headless NAO traduz material nenhum (nem um
    Principled em /mat), entao a prova e' o ROP, nao o sopimport.
    Houdini 21.0.512 + V-Ray 7.20: vray_vop_builder x12 no collect.
  - Aviso pre-existente que aparece no render com Two-Sided: "Invalid
    shader wire ... twosided/isconnected/snippet" (o translator do USD
    nao leva os nos VEX do twosided do Karma). Nao e' desta aba.

## SOP level + V-Ray: o assign aponta para o vray_<parte>, nao o collect (2026-10-22, cont.)

"testando o vray nao sai a textura no render". Causa medida: o plugin
(strings do vray_for_houdini.so) so' resolve material por um
vray_material_output -- o 'collect' do Houdini nao e' lido, a malha sai
cinza. O LOP nao sofria porque la' o caminho e' o USD.

  - build_sop(assign="auto"|"collect"|"vray_"|"renderman_"|"karma_"):
    o wrangle assign_materials ganhou o parametro 'prefix' (menu); Auto =
    "vray_" quando V-Ray esta marcado e carregado, senao "" (collect).
    Trocar na GUI sem rebuild: e' so' mudar o 'prefix' do wrangle.
  - Janela, aba SOP LEVEL: combo "Material assign" (Auto/collect/vray_/
    renderman_/karma_).
  - Medido no hython 21.0.512 + V-Ray 7.20 (VPN fxphd): 6 caminhos do
    Zea resolvendo para vray_vop_builder e o vray_renderer headless
    escrevendo o EXR com folhas texturizadas e opacity cortando.

## Arnold no Houdini 22.0.476 + HtoA 6.5.4.0 (2026-10-23)

Pedido: "nossa ferramenta esta preparada para o arnold? acabei de instalar
no 22 para testar". Medido com hython 22.0.476 + htoa-6.5.4.0_houdini-22.0.466:

- LOP: build do Abies (5 partes) com karma+arnold em 8 s, zero avisos.
  Material USD sai com outputs:arnold:surface + outputs:kma:surface +
  outputs:surface (preview), os tres coexistem no collect.
- Headless: o plugin USD do HtoA (dso/usd_plugins/ArnoldUsdBundle.so) so'
  carrega com LD_LIBRARY_PATH=$HFS/dsolib -- depende de libpxr_garch, que
  na GUI ja' esta' em memoria pelo GL. Sem isso o terminal arnold some do
  USD e o husk diz "Unable to load render plugin: HdArnoldRendererPlugin".
  Com a env certa o husk carrega o HdArnold mas devolve imagem zerada (sem
  log do Arnold), tanto esfera quanto Abies; o mesmo USD renderiza no Karma.
  Suspeita: HDK API mismatch (HtoA p/ 22.0.453, Houdini 22.0.475). Testar
  na GUI (viewport Arnold); se falhar, Houdini 22.0.466 ao lado.
- SOP: Arnold ROP NAO le o collect ("[htoa.material] Invalid shader path",
  render magenta). Com shop_materialpath em arnold_<parte> renderiza com
  textura e opacidade. Luz nativa (envlight/hlight) sai PRETA no HtoA; usar
  arnold_light (skydome). Mudanca: ASSIGN ganhou "arnold_", Auto escolhe
  vray_ > arnold_ > collect, menu do wrangle e combo da aba atualizados.
- Arnold licenciou ("authorizing with license manager: user").
