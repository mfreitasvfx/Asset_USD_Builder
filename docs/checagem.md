# Lista de checagem — pendências do Matheus no viewport/render

O que a ferramenta garantiu por medição (USD conferido) mas ainda
espera o OLHO do artista. Marcar e anotar o resultado aqui.

## Maxtree — Zea mays (`Testes/zea`, build com os 4 renderers)

- [ ] **RenderMan**: viewport/render — PxrSurface com metallic via
      PxrMetallicWorkflow, linearize desligado, folhas com
      diffuseTransmit. (`outputs:ri:surface` conferido no USD, 6
      materiais bindados.) Opcional: religar com "Converter .tex
      ACEScg" ligado e comparar.
- [ ] **Arnold**: só constrói na GUI — no hython o HDA
      arnold_materialbuilder não carrega (medido; shaders registram,
      HDA não). Rodar o build pela JANELA com arnold marcado e conferir
      viewport. Se o tipo não existir nem na GUI, o htoa.json precisa
      de revisão de path.
- [ ] **V-Ray**: look final das folhas (fog_color_tex como cor da
      translucency, amount 0.25, BRDFBump) — ajustar e SAVE PRESET
      (leaf/trunk/default).
- [ ] **Karma**: já visto verde no headless; conferir folhas com SSS no
      XPU.

## Branches de planta (proxy/simproxy do SEU hip, 2026-09-12)

A ferramenta agora replica o seu setup do Zea (delete_small_parts →
lowres_geo 2% → cor aleatória por asset → Cd no detail; simproxy =
assemble → convexdecomposition). Conferido por diff contra o
`asst builder.hiplc`: mesma topologia, mesmos parms, mesma cor final
(magenta 0.61/0.02/0.90) e mesma contagem (493 prims / 368 pontos).

- [ ] SCAN no Zea pela janela: Branches proxy+simproxy devem acender
      sozinhos (perfil maxtree); BUILD e conferir o roxo no GL.
- [ ] Simproxy: hulls do convexdecomposition no viewport (Edit/Drop LOP).
- [ ] Export: USD ganha os purposes proxy/guide sem tocar no render geo
      ("acréscimo de exports, não sobrescreve").

## Gerais (de rodadas anteriores)

- [ ] Post Apocalypse: look no V-Ray com MetaImageFile+OCIO (rebuild
      pós-conserto do bind).
- [ ] Asset Gallery incremental: exportar aos poucos pela janela e ver
      o banco somando (thumbnail GL implícito).
- [ ] Presets: ciclo real na GUI — caprichar folha, SAVE PRESET,
      UPDATE MATERIALS, export.

## Two-sided (frente/verso, vídeo das folhas do Jonas)

Duas fontes: parte `<Nome>_Back` nas texturas vira papéis `back_*` da
parte-base; e (novo, 2026-09-12) folha SEM verso próprio usa a MESMA
textura dos dois lados quando o box está ligado — dá pra checar no
Zea direto: Leaf/Bud/Flower ganham o two-sided, Fruit/Trunk não.

- [ ] V-Ray: `Mtl2Sided` (front/back/translucency_tex) — conferido no
      USD com mapa sintético; falta render real.
- [ ] Karma: `twosided` chaveia o basecolor por facing; traduz como
      shader sourceAsset com nome `_undefined` — conferir se o XPU
      renderiza (suspeita: sim, é implementação embutida).
- [ ] Arnold: `arnold::two_sided` (front/back) — wiring pronto, sem
      render ainda.
- [ ] RenderMan (novo 2026-09-12): PxrSurface `diffuseDoubleSided` +
      `specularDoubleSided`; verso espelhado usa a cor da frente,
      `_Back` real entra em `diffuseBackColor` — conferir no viewport.

## Arnold via Houdini 22 (`Testes/zea_h22`)

- [x] Build headless no 22.0.368: 12 materiais, outputs:arnold:surface
      + kma + preview no USD.
- [ ] Conferir no viewport do H22 (Arnold render delegate).

## BigMediumSmall — CP_Vehicles (2026-09-13)

- [ ] Rebuild pela janela (SCAN + BUILD dos 10 fbx): cada veículo deve
      logar "own texture parts" e sair com 6 materiais bindados.
- [ ] Preview no GL: textura visível SEM Karma marcado (usdpreviewsurface
      explícito, `outputs:surface` conferido no USD).
- [ ] Janela: encolher à vontade (combos não travam mais a largura);
      botões OPEN nos três campos abrem o Explorer.

## Janela na sua escala de UI 1.5 (2026-09-13)

O `ui.pref` está em `general.ui.scale := 1.5` e o `base.qss` do Houdini
põe 22px de padding de cada lado em todo botão — por isso o OPEN saía
vazio dentro dos 48px fixos. Agora quem manda é o texto na fonte
corrente (medido: precisa 92px, ficou 100).

- [ ] **OPEN legível** nos três campos (Asset / Textures / Output) e o
      botão de pasta com o ícone nativo do Houdini no lugar do "...".
      Se aparecer "..." em vez do ícone, o `canCreateIcon` recusou —
      me avise.
- [ ] **Janela encolhe**: mínimo caiu de 852x811 para ~151x206 (cada aba
      ganhou rolagem). Puxe a borda até o limite e veja se incomoda a
      barra de rolagem aparecer.
- [ ] **Triângulo de recentes no Output Folder** (novo) e, nos três
      campos, as pastas do próprio Houdini (`dir.history`) junto com as
      nossas. O Output NÃO se auto-preenche com pasta do histórico.
- [ ] Rótulos encurtados na aba SETTINGS (Shared textures / Asset
      Gallery on export / Convert .tex (RenderMan) / Two-Sided leaves) —
      a explicação foi para o tooltip; confira se ficou claro.
- [ ] Botões de ação (BUILD/EXPORT/UPDATE/SAVE PRESET) e as setas dos
      spinboxes agora escalam com a UI: ver se a altura ficou boa.
