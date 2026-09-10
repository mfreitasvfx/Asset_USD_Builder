# Estado — max2solaris

Atualizado: 2026-09-09

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

`src/max2solaris/lops/` monta o componente: `componentgeometry` (File SOP +
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

## Próximo passo

1. O lote dos 79 do KitBash (loop hython ou TOPs).
2. Duplicados entre kits (detectar no scan, antes de construir).
3. LAMA como quinto renderer do collect (receitas prontas no max2lama).
4. Lado Max: janela nunca aberta na UI; variantes VarA/VarB por definir.
