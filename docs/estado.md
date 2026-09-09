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

## Próximo passo

1. O builder em LOPs: `componentgeometry` (File SOP + split por asset) →
   material por parte → `componentoutput`.
2. Abrir a janela no Max e conferir o layout (nunca rodou com UI).
3. Variantes: hoje o export não gera `VarA/VarB`. O que numa cena do Max
   define uma variante — objetos de topo? layers? convenção de nome?
