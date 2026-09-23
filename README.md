# images — HotS Scrap 아이콘 저장소

[HotS Scrap](https://sin0nis.github.io/hots-scrap/) 이 쓰는 영웅 초상·기술/특성 아이콘을 GitHub Pages 로 내보냅니다.

```
https://sin0nis.github.io/images/abilitytalents/<이름>.png
https://sin0nis.github.io/images/heroportraits/<이름>.png
```

`raw.githubusercontent.com` 은 이미지를 한꺼번에 많이 부르면 429 로 막히므로 **Pages 주소를 씁니다.**
`.nojekyll` 이 있어야 Pages 굽기가 실패하지 않습니다.

## 스스로 채워집니다

[`pick-icons.yml`](.github/workflows/pick-icons.yml) 이 6시간마다(HotS Scrap 자동 갱신 40분 뒤) 돕니다.

1. HotS Scrap 이 `site/images/index.json` 의 `need` 에 적어 둔 것 — 사이트가 부르는데 여기 없는 아이콘 — 을 읽습니다.
2. **그것만** 블리자드 서버(게임 파일)에서 콕 집어 꺼내 PNG 로 넣습니다([`tools/pick_icons.py`](tools/pick_icons.py)).
   테스트 서버를 먼저 보고, 없으면 본 서버를 봅니다.
3. 빠진 게 없으면 블리자드에는 요청을 하나도 하지 않습니다.

- 있는 파일은 **지우지도 덮어쓰지도 않습니다.** 게임에서 빠진 옛 특성 아이콘은 이제 여기에만 남아 있습니다.
- 게임에도 없는 이름은 `manifest.json` 의 `absent` 에 그때의 빌드와 함께 적고, 빌드가 바뀔 때까지 다시 찾지 않습니다.
- 꺼낸 아이콘의 출처(제품·빌드·날짜)는 `manifest.json` 의 `added` 에 있습니다.

## 폴더

사이트가 쓰는 것은 `abilitytalents`·`heroportraits` 두 폴더입니다. 나머지(음성·스프레이·번들 등)는
2026-01 에 통째로 옮겨 온 것으로, 지워도 git 기록에 남아 용량이 줄지 않으므로 그대로 둡니다.

게임 자료 출처: Heroes of the Storm © Blizzard Entertainment. 추출 도구: [HeroesDataParser](https://github.com/HeroesToolChest/HeroesDataParser).
