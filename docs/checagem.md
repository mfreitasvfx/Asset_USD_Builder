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

## Gerais (de rodadas anteriores)

- [ ] Post Apocalypse: look no V-Ray com MetaImageFile+OCIO (rebuild
      pós-conserto do bind).
- [ ] Asset Gallery incremental: exportar aos poucos pela janela e ver
      o banco somando (thumbnail GL implícito).
- [ ] Presets: ciclo real na GUI — caprichar folha, SAVE PRESET,
      UPDATE MATERIALS, export.
