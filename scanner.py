"""
============================================================
네이버 트렌드 스캐너 v3.1
- 네이버 엔터 JSON API (많이 본 30위)
- 스포츠 JSON API + 연예/스포츠 전용 폴백
- 인물명 정확 감지 (일반 단어 제거)
- 키워드 빈도 기반 통합 주제 (중복 없음)
- 30만+ 영상 제목 패턴
============================================================
"""

import csv, json, re, time, hashlib
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from difflib import SequenceMatcher

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
HISTORY_CSV = ROOT / "channel_history.csv"
DATA_DIR = ROOT / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.now().strftime("%Y%m%d")

# ─────────────────────────────────────────────
# 소스 URL
# ─────────────────────────────────────────────
SOURCES = [
    {
        "name": "엔터 많이 본 뉴스",
        "url": f"https://api-gw.entertain.naver.com/ranking/most-viewed?date={TODAY}&pageSize=30",
        "category": "연예",
        "referer": "https://m.entertain.naver.com/ranking",
        "origin": "https://m.entertain.naver.com",
    },
    {
        "name": "스포츠 많이 본 뉴스",
        "url": f"https://api-gw.sports.naver.com/news/rankings/popular?date={TODAY}",
        "category": "스포츠",
        "referer": "https://m.sports.naver.com/ranking/index",
        "origin": "https://m.sports.naver.com",
    },
]

# 폴백: 연예(106) + 스포츠(107)만. 전체 뉴스 절대 안 씀
FALLBACK_SOURCES = [
    {
        "name": "[폴백] 연예 랭킹",
        "url": "https://news.naver.com/main/ranking/popularDay.naver?mid=etc&sid1=106",
        "category": "연예",
        "encoding": "euc-kr",
    },
    {
        "name": "[폴백] 스포츠 랭킹",
        "url": "https://news.naver.com/main/ranking/popularDay.naver?mid=etc&sid1=107",
        "category": "스포츠",
        "encoding": "euc-kr",
    },
]

MONTHS_THRESHOLD = 3
MIN_VIEWS_FOR_REUSE = 80000

# 타겟 키워드
TARGET_HIGH = set("자산 매출 수입 연봉 몸값 부동산 빌딩 건물 재산 파산 빚 사기 사업 CEO 기업 투자 KBO 야구 축구 월드컵 MLB FA 논란 폭로 충격 적발 고발 입건 도박 탈세 체납 음주".split())
TARGET_MID = set("근황 복귀 은퇴 반전 역대급 드라마 영화 출연료 회당 결혼 이혼 재혼 동갑 혈연 가족".split())
TARGET_LOW = set("아이돌 걸그룹 보이그룹 팬미팅 팬싸 뷰티 메이크업 패션 스타일".split())
TARGET_PEOPLE = set("유재석 강호동 신동엽 이경규 탁재훈 김구라 손흥민 이강인 류현진 이정후 김도영 송강호 이병헌 하정우 마동석 황정민 이상민 임창정 김학래 백종원 이효리 전현무 박나래".split())

# ★ 인물이 아닌 일반 단어 (확장판) — 이걸로 "공개", "만에", "오열" 같은 오탐 방지
NOT_NAMES = set("""
기자 뉴스 속보 단독 종합 포토 영상 사진 제공 이슈 화제 시선 관심 주목
한국 대한 정부 국민 사회 경제 정치 문화 생활 세계 국제 서울 부산 대구 인천 광주 대전 울산 제주
오늘 내일 어제 올해 지난 이번 해당 관련 가운데 사이 이후 이전 당시 현재 최근 과거 미래
전했 밝혔 보도 발표 전한 알려 나타 드러 확인 공개 진행 예정 결정 시작 마감 종료
했다 됐다 있다 없다 된다 한다 왔다 갔다 했는 됐는 있는 없는
라며 라고 에서 으로 까지 부터 에게 한테 보다 처럼 만큼 에서
만에 가량 이상 이하 미만 정도 이래 이후 무렵 때문 덕분 바람 사이
방송 출연 촬영 녹화 생방 프로 다시 함께 모두 처음 마지 나름
논란 충격 경악 오열 분노 환호 감동 반전 역대 최초 최대 최고 최악 최근
공구 등장 활동 참여 운영 개최 주최 진출 합류 탈퇴 복귀 은퇴 전역 입대
결국 결과 원인 이유 배경 과정 상황 실태 현황 전망 분석 평가 비교 순위
연예 스포츠 엔터 가요 드라 영화 예능 리얼 버라 코미 토크 다큐 시사
삼성 현대 하이닉스 네이버 카카오 쿠팡 배민 토스 라인
유조선 호르무즈 성과급 노조 대장동 검사 대통령 국회 여당 야당 총리 장관 의원 후보
주식 코스피 코스닥 환율 금리 물가 부채 적자 흑자 수출 수입
만원대 원대에 억대로 천만원 백만원 십만원
""".split())

# ─────────────────────────────────────────────
# 채널 히스토리
# ─────────────────────────────────────────────
def load_history():
    if not HISTORY_CSV.exists(): return []
    rows = []
    with open(HISTORY_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"title": r["title"], "views": int(r.get("views", 0)), "published": r.get("published", "")})
    return rows

def parse_date(s):
    try: return datetime.strptime(s, "%b %d, %Y")
    except: return None

# ─────────────────────────────────────────────
# 크롤러
# ─────────────────────────────────────────────
class Crawler:
    def __init__(self):
        self.session = requests.Session()

    def fetch_json(self, src):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": src.get("referer", ""),
            "Origin": src.get("origin", ""),
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }
        try:
            r = self.session.get(src["url"], headers=headers, timeout=15)
            r.raise_for_status()
            return self._parse_json(r.json(), src)
        except Exception as e:
            print(f"  ⚠ API 실패: {e}")
            return []

    def _parse_json(self, data, src):
        # 리스트 키 탐색
        items = []
        if isinstance(data, list):
            items = data
        else:
            for key in ["results", "data", "articles", "list", "items", "rankings", "newsList"]:
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    break
            if not items:
                for v in data.values():
                    if isinstance(v, dict):
                        for v2 in v.values():
                            if isinstance(v2, list) and v2: items = v2; break
                    elif isinstance(v, list) and v: items = v; break

        print(f"  📊 JSON: {len(items)}개")
        if items and isinstance(items[0], dict):
            print(f"  📌 키: {list(items[0].keys())[:8]}")

        articles = []
        for item in items[:30]:
            if not isinstance(item, dict): continue
            title = ""
            for tk in ["title", "articleTitle", "newsTitle", "headline", "subject"]:
                if tk in item and item[tk]: title = str(item[tk]).strip(); break
            if not title or len(title) < 8: continue

            url = ""
            for uk in ["articleLink", "link", "url", "articleUrl", "newsUrl", "pcLink", "mobileLink"]:
                if uk in item and item[uk]: url = str(item[uk]).strip(); break

            views = 0
            for vk in ["readCount", "viewCount", "views", "hitCount", "totalCount", "count"]:
                if vk in item:
                    try: views = int(item[vk])
                    except: pass
                    break

            title = re.sub(r"\[.*?\]", "", title).strip()
            articles.append({
                "title": title, "url": url, "source": src["name"],
                "category": src["category"], "views": views, "rank": len(articles)+1,
            })
        return articles

    def fetch_html_fallback(self, src):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            r = self.session.get(src["url"], headers=headers, timeout=15)
            r.raise_for_status()
            text = r.content.decode(src.get("encoding", "utf-8"), errors="replace")
            soup = BeautifulSoup(text, "html.parser")
            articles, seen = [], set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "article" not in href: continue
                title = ""
                for sub in ["strong", "em", "span"]:
                    el = a.find(sub)
                    if el:
                        t = el.get_text(strip=True)
                        if len(t) > len(title): title = t
                if not title: title = a.get_text(strip=True)
                title = re.sub(r"\[.*?\]", "", title).strip()
                if len(title) < 8: continue
                key = hashlib.md5(title.encode()).hexdigest()
                if key in seen: continue
                seen.add(key)
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(src["url"], href)
                articles.append({"title": title, "url": href, "source": src["name"], "category": src["category"], "views": 0, "rank": len(articles)+1})
            return articles[:30]
        except Exception as e:
            print(f"  ⚠ 폴백 실패: {e}")
            return []

# ─────────────────────────────────────────────
# 키워드/인물 분석 → 통합 주제
# ─────────────────────────────────────────────
def extract_real_names(articles):
    """기사 제목에서 실제 인물 이름만 추출 (일반 단어 철저 제거)"""
    name_counter = Counter()
    name_articles = {}

    for art in articles:
        title = art["title"]
        # 따옴표 안의 이름 (높은 신뢰도)
        quoted_names = re.findall(r"['\"]?([가-힣]{2,4})['\"]?\s*[,·]", title)
        # 일반 2~3글자 패턴
        all_names = re.findall(r"[가-힣]{2,3}", title)

        candidates = set(quoted_names + all_names)
        for name in candidates:
            # ★ 일반 단어 필터
            if name in NOT_NAMES:
                continue
            if len(name) < 2:
                continue
            # 1글자+조사 패턴 제거
            if name.endswith(("에서", "으로", "까지", "부터", "라며", "라고", "했다", "됐다", "있다", "없다")):
                continue

            name_counter[name] += 1
            if name not in name_articles:
                name_articles[name] = []
            name_articles[name].append(art)

    return name_counter, name_articles


def analyze_and_generate(articles, history):
    """전체 기사 분석 → 통합 주제 도출"""

    # 1) 앵글 감지
    angle_patterns = {
        "자산·몸값":  r"자산|재산|연봉|몸값|부동산|빌딩|매출|수익|출연료|개런티|\d+억|\d+조",
        "논란·사건":  r"논란|폭로|고발|적발|음주|사기|탈세|도박|갑질|비난|물의|구속|기소",
        "결혼·이혼":  r"결혼|이혼|열애|재혼|파혼|임신|출산|약혼",
        "복귀·근황":  r"복귀|근황|컴백|은퇴|전역|공백",
        "투병·건강":  r"투병|완치|수술|입원|암|희귀병|재활|사망|별세|부고",
        "스포츠":     r"홈런|안타|골|우승|신기록|FA|트레이드|MVP|감독|코치|선발|타순|선수|KBO|K리그",
        "가족·혈연":  r"가족|혈연|동갑|형제|부모|2세|자녀|아들|딸",
    }

    angle_articles = {}
    for angle, pattern in angle_patterns.items():
        matched = [a for a in articles if re.search(pattern, a["title"])]
        if len(matched) >= 2:  # 기사 2개 이상만
            angle_articles[angle] = matched

    # 2) 인물 빈도 분석
    name_counter, name_arts = extract_real_names(articles)
    top_names = [(n, c) for n, c in name_counter.most_common(20) if c >= 2]

    # 3) 통합 주제 생성 (앵글당 1개만)
    topics = []
    used_angles = set()

    for angle, matched in sorted(angle_articles.items(), key=lambda x: len(x[1]), reverse=True):
        if angle in used_angles:
            continue
        used_angles.add(angle)

        # 이 앵글에서 가장 많이 언급된 실제 인물
        angle_names = Counter()
        for a in matched:
            for name in re.findall(r"[가-힣]{2,3}", a["title"]):
                if name not in NOT_NAMES:
                    angle_names[name] += 1

        top_person = ""
        if angle_names:
            best_name, best_count = angle_names.most_common(1)[0]
            if best_count >= 2:
                top_person = best_name

        # 제목 생성 (30만+ 패턴)
        title = _make_title(angle, top_person)
        best_art = max(matched, key=lambda a: a.get("views", 0))

        topics.append({
            "title": title,
            "angle_type": angle,
            "article_count": len(matched),
            "source_article": best_art["title"],
            "source_url": best_art.get("url", ""),
            "source_name": best_art.get("source", ""),
            "related_names": [n for n, _ in angle_names.most_common(5) if n not in NOT_NAMES],
            "template": _get_template_name(angle),
        })

    # 4) 고빈도 인물 기반 주제 (앵글과 별개)
    for name, cnt in top_names:
        if cnt < 3: break
        if name in NOT_NAMES: continue
        if any(name in t.get("title", "") for t in topics): continue  # 이미 포함된 인물 스킵

        person_arts = name_arts.get(name, [])
        context = _detect_context(name, person_arts)

        topics.append({
            "title": context["title"],
            "angle_type": f"👤 {name}",
            "article_count": cnt,
            "source_article": person_arts[0]["title"] if person_arts else "",
            "source_url": person_arts[0].get("url", "") if person_arts else "",
            "source_name": person_arts[0].get("source", "") if person_arts else "",
            "related_names": [name],
            "template": context["template"],
        })

    # 5) 점수 + 중복 체크
    for t in topics:
        t["score"] = _score(t)
        t["dup_check"] = _check_dup(t["title"], history)
        t["table"] = {"headers": list(_headers(t["template"]))}

    topics.sort(key=lambda t: t["score"], reverse=True)
    valid = [t for t in topics if not t["dup_check"]["is_duplicate"]]

    # 키워드 빈도 (일반 단어 제거)
    kw_counter = Counter()
    for art in articles:
        words = set(re.findall(r"[가-힣]{2,}", art["title"])) - NOT_NAMES
        kw_counter.update(words)

    return {
        "topics": valid[:20],
        "keyword_freq": kw_counter.most_common(20),
        "name_freq": top_names[:15],
        "angle_scores": [(a, len(arts)) for a, arts in angle_articles.items()],
    }


# ─────────────────────────────────────────────
# 제목 생성 (30만+ 패턴)
# ─────────────────────────────────────────────
def _make_title(angle, person):
    p = person
    titles = {
        "자산·몸값": [
            f'"{p}, 자산이 이 정도였다고?" 연예인 숨은 자산 서열 TOP10' if p else '"숨은 부자였다고?" 연예인 자산 서열 TOP10',
        ],
        "논란·사건": [
            f'"{p}까지 이럴 줄은..." 올해 팬들 분노 터진 스타 TOP10' if p else '"올해 대체 무슨 일이" 팬들 충격 받은 스타 TOP10',
        ],
        "결혼·이혼": [
            f'"{p} 결혼 상대가 누구?" 화제의 결혼 발표 스타 TOP10' if p else '"남편이 누구길래 난리?" 화제의 결혼 스타 TOP10',
        ],
        "복귀·근황": [
            f'"{p}, 지금 뭐 하고 있을까?" 근황 궁금한 스타 TOP10' if p else '"그때 그 사람, 지금은?" 근황 궁금한 스타 TOP10',
        ],
        "투병·건강": [
            '"죽을 고비 넘기고 돌아왔다" 투병 이겨낸 스타 TOP10',
        ],
        "스포츠": [
            f'"{p}, 역대급 기록?" 스포츠 레전드 기록 TOP10' if p else '"이 기록은 못 깬다" 역대급 스포츠 기록 TOP10',
        ],
        "가족·혈연": [
            f'"{p}이랑 형제였다고?" 놀라운 연예계 가족 TOP10' if p else '"이 둘이 가족이라고?" 놀라운 연예계 혈연 TOP10',
        ],
    }
    return titles.get(angle, ['"화제의 스타" TOP10'])[0]


def _detect_context(name, articles):
    combined = " ".join(a["title"] for a in articles)
    checks = [
        (r"논란|폭로|사건|사고|구속", {"title": f'"{name}, 대체 무슨 일이?" {name} 관련 이슈 총정리', "template": "논란 집합"}),
        (r"결혼|열애|이혼", {"title": f'"{name} 결혼설?" {name} 연애사 총정리', "template": "결혼 화제"}),
        (r"복귀|근황|컴백", {"title": f'"{name}, 지금 어디서 뭐 하나?" {name} 근황 총정리', "template": "장기 공백 복귀"}),
        (r"자산|연봉|몸값|억", {"title": f'"{name} 자산이 얼마?" {name}급 자산가 스타 TOP10', "template": "자산 서열"}),
    ]
    for pat, result in checks:
        if re.search(pat, combined): return result
    return {"title": f'"{name}" 관련 화제 스타 TOP10', "template": "인맥"}


def _get_template_name(angle):
    return {"자산·몸값": "자산 서열", "논란·사건": "논란 집합", "결혼·이혼": "결혼 화제",
            "복귀·근황": "장기 공백 복귀", "투병·건강": "투병 극복", "스포츠": "스포츠 기록",
            "가족·혈연": "동갑내기"}.get(angle, "인맥")


def _headers(template):
    return {"자산 서열": ("이름", "주요 수입원", "추정 자산", "자산 특이점"),
            "논란 집합": ("이름", "소속·직업", "논란 내용", "현재 상황"),
            "결혼 화제": ("이름", "배우자", "결혼 시점", "화제 포인트"),
            "장기 공백 복귀": ("이름", "공백 기간", "공백 사유", "복귀 작품"),
            "투병 극복": ("이름", "투병 질환", "공백기", "복귀 작품"),
            "스포츠 기록": ("선수", "소속팀", "기록 내용", "기록 가치"),
            "동갑내기": ("이름", "나이", "대표작", "현재 활동"),
            "인맥": ("이름", "분류", "이슈 내용", "현재 상황"),
    }.get(template, ("이름", "분류", "내용", "비고"))


def _score(topic):
    score = 5.0
    text = topic["title"] + " " + topic.get("source_article", "")
    for kw in TARGET_HIGH:
        if kw in text: score += 0.5
    for kw in TARGET_MID:
        if kw in text: score += 0.3
    for kw in TARGET_LOW:
        if kw in text: score -= 0.6
    for p in TARGET_PEOPLE:
        if p in text: score += 0.4; break
    cnt = topic.get("article_count", 1)
    if cnt >= 5: score += 1.5
    elif cnt >= 3: score += 1.0
    elif cnt >= 2: score += 0.5
    return max(0, min(10, round(score, 1)))


def _check_dup(title, history):
    now = datetime.now()
    result = {"is_duplicate": False, "status": "통과", "matched_title": "", "matched_views": 0, "reason": ""}
    t_kw = set(re.findall(r"[가-힣]{2,}", title)) - NOT_NAMES
    best, best_sim = None, 0
    for h in history:
        h_kw = set(re.findall(r"[가-힣]{2,}", h["title"])) - NOT_NAMES
        s = SequenceMatcher(None, title, h["title"]).ratio()
        o = len(t_kw & h_kw) / min(len(t_kw), len(h_kw)) if t_kw and h_kw else 0
        c = s * 0.3 + o * 0.7
        if c > best_sim: best_sim = c; best = h
    if best_sim >= 0.55 and best:
        pub = parse_date(best["published"])
        v = best["views"]
        days = (now - pub).days if pub else 0
        if days >= MONTHS_THRESHOLD * 30 and v >= MIN_VIEWS_FOR_REUSE:
            result["status"] = "재활용 가능"
            result["reason"] = f"검증됨 {v:,}회 · {days}일 경과"
        elif days >= MONTHS_THRESHOLD * 30:
            result["status"] = "재활용 가능"
            result["reason"] = f"기간 경과 {days}일"
        else:
            result["is_duplicate"] = True
            result["status"] = "중복 제외"
            result["reason"] = f"{v:,}회 · 최근"
        result["matched_title"] = best["title"]
        result["matched_views"] = v
    return result


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def run_scan():
    t = datetime.now()
    print(f"\n{'='*60}")
    print(f"🔍 트렌드 스캔 v3.1: {t.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    crawler = Crawler()
    history = load_history()
    print(f"📚 히스토리: {len(history)}개")

    all_articles = []
    stats = {}

    # JSON API
    for src in SOURCES:
        print(f"\n📡 {src['name']}...")
        arts = crawler.fetch_json(src)
        stats[src["name"]] = len(arts)
        all_articles.extend(arts)
        print(f"  ✅ {len(arts)}개")
        for a in arts[:3]:
            print(f"  📌 {a['rank']}위 {a['title'][:50]}")
        time.sleep(1)

    # 연예 또는 스포츠 수집 실패 시 해당 섹션만 폴백
    ent_count = sum(1 for a in all_articles if a["category"] == "연예")
    sport_count = sum(1 for a in all_articles if a["category"] == "스포츠")

    if ent_count < 5:
        print(f"\n⚠️ 연예 {ent_count}개 부족. 연예 폴백...")
        fb = FALLBACK_SOURCES[0]
        arts = crawler.fetch_html_fallback(fb)
        stats[fb["name"]] = len(arts)
        all_articles.extend(arts)
        print(f"  ✅ {len(arts)}개")

    if sport_count < 5:
        print(f"\n⚠️ 스포츠 {sport_count}개 부족. 스포츠 폴백...")
        fb = FALLBACK_SOURCES[1]
        arts = crawler.fetch_html_fallback(fb)
        stats[fb["name"]] = len(arts)
        all_articles.extend(arts)
        print(f"  ✅ {len(arts)}개")

    # 중복 제거
    seen = set()
    unique = []
    for a in all_articles:
        if a["title"] not in seen: seen.add(a["title"]); unique.append(a)

    print(f"\n📋 총: {len(unique)}개")

    # 분석 + 주제 생성
    print(f"\n💡 분석 중...")
    analysis = analyze_and_generate(unique, history)
    topics = analysis["topics"]

    print(f"  주제: {len(topics)}개")
    if analysis["keyword_freq"]:
        print(f"  키워드 TOP5: {', '.join(f'{k}({c})' for k,c in analysis['keyword_freq'][:5])}")
    if analysis["name_freq"]:
        print(f"  인물 TOP5: {', '.join(f'{n}({c})' for n,c in analysis['name_freq'][:5])}")

    # 저장
    result = {
        "scan_time": t.strftime("%Y-%m-%d %H:%M:%S"),
        "source_stats": stats,
        "total_articles": len(unique),
        "total_topics_generated": len(topics),
        "excluded_duplicates": sum(1 for tp in topics if tp["dup_check"]["is_duplicate"]),
        "valid_topics": len(topics),
        "articles": unique,
        "topics": topics,
        "all_topics": topics,
        "keyword_freq": analysis["keyword_freq"],
        "name_freq": analysis["name_freq"],
    }

    with open(DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    ts = t.strftime("%Y-%m-%d_%H%M")
    with open(DATA_DIR / f"scan_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log_path = DATA_DIR / "scan_log.json"
    logs = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    logs.insert(0, {"time": result["scan_time"], "articles": len(unique), "topics": len(topics), "file": f"scan_{ts}.json"})
    log_path.write_text(json.dumps(logs[:50], ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"🎯 TOP 5")
    print(f"{'='*60}")
    for i, tp in enumerate(topics[:5], 1):
        print(f"  {i}. [{tp['score']}] {tp['title']}")
        print(f"     기사 {tp['article_count']}건 · 인물: {', '.join(tp.get('related_names',[])[:3])}")
        print(f"     ← {tp['source_article'][:50]}")


if __name__ == "__main__":
    run_scan()
