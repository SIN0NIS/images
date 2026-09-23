# -*- coding: utf-8 -*-
"""빠진 아이콘만 게임에서 꺼내 채운다.

HotS Scrap(SIN0NIS/hots-scrap)은 자기가 부르는 아이콘 중 이 저장소에 없는 것을
site/images/index.json 의 `need` 에 적어 둔다. 이 도구는 그 목록을 읽어서 **그것만**
블리자드 서버(게임 파일, CASC)에서 콕 집어 꺼내 PNG 로 바꿔 넣는다.

  · 전부 다시 뽑지 않는다. 목록에 있는데 여기 없는 것만 꺼낸다.
  · 빠진 게 없으면 블리자드에는 요청을 하나도 안 한다(GitHub API 1개 + 버전 확인 2개로 끝).
  · 있는 파일은 **지우지도 덮어쓰지도 않는다.** 옛 특성 아이콘은 이제 여기에만 남아 있다.
  · 게임에도 없는 이름은 manifest.json 의 `absent` 에 그때의 빌드와 함께 적어 둔다.
    빌드가 바뀌기 전에는 다시 찾지 않는다 — 안 그러면 없는 이름 하나 때문에
    6시간마다 블리자드 파일 목록(약 250MB)을 헛받는다.
  · 테스트 서버(herot)를 먼저 본다. 새 영웅은 거기에 먼저 나오기 때문이고, 한 번만 받으면 끝나는 경우가 많다.
    거기 없으면 본 서버(hero)를 본다. (테스트 서버가 본 서버보다 뒤처진 동안이라면 옛 그림을 가져올 수 있지만,
    없던 이름을 새로 넣을 때만 쓰므로 실제로 겹칠 일이 거의 없다. 어디서 꺼냈는지는 manifest 에 남는다)
  · 한쪽 서버를 못 보면 다른 쪽은 계속한다. 못 본 서버에는 '없다'고 적지 않는다(다음에 다시 찾는다, 종료 코드 3).

꺼내는 도구: HeroesDataParser(`dotnet-heroes-data-parser casc-extract online`).
그림 변환은 Pillow. 게임의 DDS 를 그대로 풀어 PNG 로 저장한다(HeroesToolChest 본과 픽셀 차이 0~1).

사용
  python tools/pick_icons.py --plan                 # 무엇을 꺼낼지만 본다(블리자드에 요청 안 함)
  python tools/pick_icons.py                        # 꺼내서 넣는다(커밋은 워크플로가 한다)
  python tools/pick_icons.py --need-file need.json  # 목록을 파일로 줄 때(시험용)
  python tools/pick_icons.py --game-ptr "C:/Program Files (x86)/Heroes of the Storm Public Test"
                                                    # 블리자드 서버 대신 PC 설치본에서(시험용, 받는 것 없음)
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"
FOLDERS = ("abilitytalents", "heroportraits")
NEED_API = "https://api.github.com/repos/SIN0NIS/hots-scrap/contents/site/images/index.json"
VERSIONS = "https://us.version.battle.net/v2/products/{}/versions"
# (블리자드 제품 코드, 테스트 서버인가) — 앞에서부터 본다
PRODUCTS = (("herot", True), ("hero", False))
# 이름에 아포스트로피가 실제로 쓰인다(storm_ui_icon_kel'thuzad_chains.png). 점은 허용하지 않는다(.. 로 빠져나갈 수 없게).
NAME_RE = re.compile(r"^(abilitytalents|heroportraits)/[A-Za-z0-9_'\-]+\.png$")
UA = "hots-scrap-images/1.0 (+https://github.com/SIN0NIS/images)"


def say(*a):
    print(*a, flush=True)


def out(key, val):
    """워크플로의 다음 단계에 넘긴다."""
    p = os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{key}={val}\n")


def http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_need(a):
    """HotS Scrap 이 적어 둔 `need` — 사이트가 부르는데 여기 없는 아이콘."""
    if a.need_file:
        raw = json.loads(Path(a.need_file).read_text(encoding="utf-8-sig"))
    else:
        h = {"Accept": "application/vnd.github.raw+json"}
        tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if tok:
            h["Authorization"] = "Bearer " + tok
        raw = json.loads(http_get(NEED_API, h).decode("utf-8-sig"))
    lst = raw.get("need", []) if isinstance(raw, dict) else raw
    good, bad = [], []
    for n in lst:
        (good if isinstance(n, str) and NAME_RE.match(n) else bad).append(n)
    for n in bad:
        say(f"  ! 이름 모양이 이상해서 건너뜀: {n!r}")
    return sorted(set(good))


def have_files():
    """이 저장소에 이미 있는 아이콘. 일부만 받아 둔 사본(sparse·blobless)이라도 git 목록으로 안다."""
    have = set()
    r = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD", "--", *FOLDERS],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if r.returncode == 0:
        have.update(x.strip() for x in r.stdout.splitlines() if x.strip())
    for d in FOLDERS:
        have.update(f"{d}/{p.name}" for p in (ROOT / d).glob("*.png"))
    return have


def game_versions():
    """블리자드가 지금 내놓은 빌드 — {제품: '2.57.0.98182'}"""
    v = {}
    for prod, _ in PRODUCTS:
        txt = http_get(VERSIONS.format(prod)).decode("utf-8", "replace").splitlines()
        head = [c.split("!")[0] for c in txt[0].split("|")] if txt else []
        for line in txt[1:]:
            row = dict(zip(head, line.split("|")))
            if row.get("Region") == "us" and row.get("VersionsName"):
                v[prod] = row["VersionsName"]
                break
    return v


def load_manifest():
    if MANIFEST.exists():
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    else:
        m = {}
    m.setdefault("about", "tools/pick_icons.py 가 게임에서 꺼내 넣은 아이콘의 기록. "
                          "added = 언제 어느 빌드에서 꺼냈나, absent = 게임에도 없어 그 빌드에서는 다시 찾지 않는 이름.")
    m.setdefault("added", {})
    m.setdefault("absent", {})
    return m


def save_manifest(m):
    m["added"] = dict(sorted(m["added"].items()))
    m["absent"] = dict(sorted(m["absent"].items()))
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, MANIFEST)


def extract(a, prod, is_ptr, names, work):
    """블리자드 서버(또는 PC 설치본)에서 이름들만 꺼낸다. 돌려주는 것: {이름: dds 경로}"""
    dest = Path(work) / prod
    dest.mkdir(parents=True, exist_ok=True)
    game = a.game_ptr if is_ptr else a.game_live
    cmd = [a.hdp, "casc-extract"]
    if game:
        cmd += ["game", "-s", game]
    else:
        cmd += ["online"] + (["--download-ptr"] if is_ptr else [])
    cmd += ["-t", str(a.threads), "-o", str(dest)]
    for n in names:
        cmd += ["-i", f"mods/**/assets/textures/{Path(n).stem}.dds"]
    say(f"  [{prod}] {len(names)}개 꺼내는 중 ({'PC 설치본' if game else '블리자드 서버'}) …")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    log = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"Total files to extract:\s*(\d+)", log)
    say(f"  [{prod}] 끝 (rc={r.returncode}, 찾은 파일 {m.group(1) if m else '?'}개)")
    if r.returncode != 0:
        say(log[-1500:])
        raise RuntimeError(f"{prod} 꺼내기 실패 (rc={r.returncode})")
    found = {}
    for n in names:
        stem = Path(n).stem
        hits = sorted(glob.glob(str(dest / "mods" / "*" / "base.stormassets" / "assets" / "textures" / f"{stem}.dds")))
        # heroes.stormmod 를 먼저(영웅 자산이 모이는 곳), 없으면 다른 모드
        hits.sort(key=lambda p: (0 if os.sep + "heroes.stormmod" + os.sep in p else 1, p))
        if hits:
            found[n] = hits[0]
    return found


def to_png(dds, png):
    from PIL import Image
    im = Image.open(dds).convert("RGBA")
    png.parent.mkdir(parents=True, exist_ok=True)
    tmp = png.with_name(png.name + ".tmp")
    im.save(tmp, format="PNG", optimize=True)
    os.replace(tmp, png)
    h = hashlib.sha1(f"{im.size[0]}x{im.size[1]}".encode() + im.tobytes()).hexdigest()[:16]
    return im.size, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="무엇을 꺼낼지만 본다(블리자드에 요청 안 함)")
    ap.add_argument("--need-file", help="need 목록을 파일로(시험용). 기본은 HotS Scrap 저장소에서 읽는다")
    ap.add_argument("--hdp", default=shutil.which("dotnet-heroes-data-parser") or "dotnet-heroes-data-parser")
    ap.add_argument("--game-ptr", help="블리자드 서버 대신 이 PC 설치본(테스트 서버)에서")
    ap.add_argument("--game-live", help="블리자드 서버 대신 이 PC 설치본(본 서버)에서")
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()

    try:
        need = load_need(a)
    except Exception as e:
        say(f"need 목록을 못 읽었습니다 — {e}")
        return 2
    have = have_files()
    todo = [n for n in need if n not in have]
    say(f"HotS Scrap 이 부르는데 여기 없는 것 {len(need)}개 · 그새 들어온 것 {len(need) - len(todo)}개 · 남은 것 {len(todo)}개")

    man = load_manifest()
    try:
        ver = game_versions() if todo else {}
    except Exception as e:
        say(f"블리자드 빌드 번호를 못 읽었습니다 — {e}")
        return 2
    if todo:
        say("지금 빌드: " + " · ".join(f"{p} {ver.get(p, '?')}" for p, _ in PRODUCTS))
    # 게임에도 없다고 이미 확인했고 그 뒤로 빌드가 안 바뀐 이름은 건너뛴다.
    # **서버별로** 따진다 — 한쪽 빌드만 바뀌었으면 그쪽만 다시 찾는다(반대쪽 파일 목록을 헛받지 않는다).
    def todo_for(prod, names):
        return [n for n in names if man["absent"].get(n, {}).get(prod) != ver.get(prod)]

    waiting = [n for n in todo if not any(todo_for(p, [n]) for p, _ in PRODUCTS)]
    todo = [n for n in todo if n not in waiting]
    if waiting:
        say(f"게임에도 없어 새 빌드를 기다리는 것 {len(waiting)}개 (다시 찾지 않음)")
    for n in todo:
        say(f"   꺼낼 것  {n}")
    out("todo", len(todo))
    if a.plan or not todo:
        out("added", 0)
        say("할 일 없음." if not todo else "(--plan: 여기까지)")
        return 0

    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d")
    left, added, failed = list(todo), [], []
    with tempfile.TemporaryDirectory(prefix="pick_icons_") as work:
        for prod, is_ptr in PRODUCTS:
            if not left:
                break
            mine = todo_for(prod, left)          # 이 서버에서 아직 안 찾아본 것만
            if not mine:
                continue
            if (a.game_ptr or a.game_live) and not (a.game_ptr if is_ptr else a.game_live):
                say(f"  [{prod}] 설치본 경로를 안 줘서 건너뜀 (시험 모드)")   # 시험 중에 몰래 인터넷을 쓰지 않게
                failed.append(prod)
                continue
            if not ver.get(prod):
                say(f"  [{prod}] 빌드 번호를 몰라서 건너뜀")                 # None 으로 적으면 기억이 영영 안 풀린다
                failed.append(prod)
                continue
            try:
                found = extract(a, prod, is_ptr, mine, work)
            except Exception as e:
                # 한쪽이 막혀도 다른 쪽은 해 본다. 실패한 서버에는 '없다'고 적지 않는다(다음에 다시 찾게).
                say(f"  ! [{prod}] 꺼내지 못했습니다 — {str(e)[:200]}")
                failed.append(prod)
                continue
            for n in mine:                       # 이 서버에는 없더라 — 그 빌드에서는 다시 안 찾는다
                if n not in found:
                    man["absent"].setdefault(n, {})[prod] = ver.get(prod)
                    man["absent"][n]["date"] = today
            for n, dds in sorted(found.items()):
                png = ROOT / n
                if png.exists():                      # 그새 누가 넣었으면 건드리지 않는다
                    left.remove(n)
                    continue
                try:
                    size, px = to_png(dds, png)
                except Exception as e:
                    say(f"   ! 그림으로 못 바꿈 {n}: {e}")
                    continue
                man["added"][n] = {"from": prod, "version": ver.get(prod), "date": today,
                                   "size": f"{size[0]}x{size[1]}", "px": px}
                man["absent"].pop(n, None)
                added.append(n)
                left.remove(n)
                say(f"   + {n}  ({size[0]}x{size[1]}, {prod} {ver.get(prod)})")
    for n in left:
        say(f"   - 게임에도 없음: {n}")
    save_manifest(man)                      # 한 것은 반드시 남긴다(실패해도 헛수고가 되지 않게)
    out("added", len(added))
    say(f"넣음 {len(added)}개 · 게임에도 없음 {len(left)}개"
        + (f" · 못 본 서버 {', '.join(failed)}" if failed else ""))
    return 3 if failed else 0               # 3 = 일부 서버를 못 봤다(다음 회차에 다시 찾는다)


if __name__ == "__main__":
    sys.exit(main())
