"""
============================================================
네이버 트렌드 스캐너 v4.0 — Gemini AI 분석 통합
- 네이버 엔터 JSON API (많이 본 30위)
- 스포츠 JSON API (많이 본 20위)
- 폴백: 연예/스포츠 전용 HTML 크롤링
- ★ Gemini API로 50개 기사 종합 분석 → 5~8개 구체 주제 자동 생성
- 중복 체크 (channel_history.csv)
============================================================
"""

import csv, json, os, re, time, hashlib
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

# Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# ─────────────────────────────────────────────
# 채널 히스토리
# ─────────────────────────────────────────────
def load_history():
    if not HISTORY_CSV.exists():
        return []
    rows = []
    with open(HISTORY_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "title": r["title"],
                "views": int(r.get("views", 0)),
                "published": r.get("published", ""),
            })
    return rows


def parse_date(s):
    try:
        return datetime.strptime(s, "%b %d, %Y")
    except:
        return None


# ─────────────────────────────────────────────
# 중복 체크
# ─────────────────────────────────────────────
NOT_NAMES = set("""
기자 뉴스 속보 단독 종합 포토 영상 사진 제공 이슈 화제 시선 관심 주목
한국 대한 정부 국민 사회 경제 정치 문화 생활 세계 국제 서울 부산 대구 인천 광주 대전 울산 제주
오늘 내일 어제 올해 지난 이번 해당 관련 가운데 사이 이후 이전 당시 현재 최근 과거 미래
전했 밝혔 보도 발표 전한 알려 나타 드러 확인 공개 진행 예정 결정 시작 마감 종료
했다 됐다 있다 없다 된다 한다 왔다 갔다 했는 됐는 있는 없는
라며 라고 에서 으로 까지 부터 에게 한테 보다 처럼 만큼
만에 가량 이상 이하 미만 정도 이래 이후 무렵 때문 덕분 바람
방송 출연 촬영 녹화 생방 프로 다시 함께 모두 처음 마지 나름
논란 충격 경악 오열 분노 환호 감동 반전 역대 최초 최대 최고 최악
공구 등장 활동 참여 운영 개최 주최 진출 합류 탈퇴 복귀 은퇴 전역 입대
결국 결과 원인 이유 배경 과정 상황 실태 현황 전망 분석 평가 비교 순위
연예 스포츠 엔터 가요 드라 영화 예능 리얼 버라 코미 토크 다큐 시사
삼성 현대 하이닉스 네이버 카카오 쿠팡 배민 토스 라인
유조선 호르무즈 성과급 노조 대장동 검사 대통령 국회 여당 야당 총리 장관 의원 후보
주식 코스피 코스닥 환율 금리 물가 부채 적자 흑자 수출 수입
만원대 원대에 억대로 천만원 백만원 십만원
""".split())


def check_dup(title, history):
    now = datetime.now()
    result = {
        "is_duplicate": False,
        "status": "통과",
        "matched_title": "",
        "matched_views": 0,
        "reason": "",
    }
    t_kw = set(re.findall(r"[가-힣]{2,}", title)) - NOT_NAMES
    best, best_sim = None, 0
    for h in history:
        h_kw = set(re.findall(r"[가-힣]{2,}", h["title"])) - NOT_NAMES
        s = SequenceMatcher(None, title, h["title"]).ratio()
        o = len(t_kw & h_kw) / min(len(t_kw), len(h_kw)) if t_kw and h_kw else 0
        c = s * 0.3 + o * 0.7
        if c > best_sim:
            best_sim = c
            best = h

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
                            if isinstance(v2, list) and v2:
                                items = v2
                                break
                    elif isinstance(v, list) and v:
                        items = v
                        break

        print(f"  📊 JSON: {len(items)}개")
        if items and isinstance(items[0], dict):
            print(f"  📌 키: {list(items[0].keys())[:8]}")

        articles = []
        for item in items[:30]:
            if not isinstance(item, dict):
                continue
            title = ""
            for tk in ["title", "articleTitle", "newsTitle", "headline", "subject"]:
                if tk in item and item[tk]:
                    title = str(item[tk]).strip()
                    break
            if not title or len(title) < 8:
                continue

            url = ""
            for uk in ["articleLink", "link", "url", "articleUrl", "newsUrl", "pcLink", "mobileLink"]:
                if uk in item and item[uk]:
                    url = str(item[uk]).strip()
                    break

            views = 0
            for vk in ["readCount", "viewCount", "views", "hitCount", "totalCount", "count"]:
                if vk in item:
                    try:
                        views = int(item[vk])
                    except:
                        pass
                    break

            title = re.sub(r"\[.*?\]", "", title).strip()
            articles.append({
                "title": title,
                "url": url,
                "source": src["name"],
                "category": src["category"],
                "views": views,
                "rank": len(articles) + 1,
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
                if "article" not in href:
                    continue
                title = ""
                for sub in ["strong", "em", "span"]:
                    el = a.find(sub)
                    if el:
                        t = el.get_text(strip=True)
                        if len(t) > len(title):
                            title = t
                if not title:
                    title = a.get_text(strip=True)
                title = re.sub(r"\[.*?\]", "", title).strip()
                if len(title) < 8:
                    continue
                key = hashlib.md5(title.encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(src["url"], href)
                articles.append({
                    "title": title,
                    "url": href,
                    "source": src["name"],
                    "category": src["category"],
                    "views": 0,
                    "rank": len(articles) + 1,
                })
            return articles[:30]
        except Exception as e:
            print(f"  ⚠ 폴백 실패: {e}")
            return []


# ─────────────────────────────────────────────
# ★ Gemini API 종합 분석
# ─────────────────────────────────────────────
def build_gemini_prompt(articles, history_titles):
    """기사 목록 + 채널 히스토리를 Gemini에게 보낼 프롬프트 생성"""
    # 기사 목록 텍스트
    ent_articles = [a for a in articles if a["category"] == "연예"]
    sport_articles = [a for a in articles if a["category"] == "스포츠"]

    article_text = "## 연예 기사 (많이 본 순)\n"
    for i, a in enumerate(ent_articles, 1):
        views_str = f" ({a['views']:,}회)" if a['views'] else ""
        article_text += f"{i}. {a['title']}{views_str}\n"

    article_text += "\n## 스포츠 기사 (많이 본 순)\n"
    for i, a in enumerate(sport_articles, 1):
        views_str = f" ({a['views']:,}회)" if a['views'] else ""
        article_text += f"{i}. {a['title']}{views_str}\n"

    # 최근 히스토리 (중복 방지용)
    recent_titles = history_titles[:30] if history_titles else []
    history_text = "\n".join(f"- {t}" for t in recent_titles) if recent_titles else "(없음)"

    prompt = f"""당신은 유튜브 채널 "정보주는 하마"의 콘텐츠 기획자입니다.

## 채널 정보
- 형식: TOP10 숏츠 (세로 영상, 표 기반 정보 전달)
- 타겟: 30~50대 한국 남성
- 히트 제목 패턴: "따옴표 인용" + 구체 숫자/금액 + 의문문(?)
- 30만+ 조회수 영상 200개 이상 보유
- A등급 카테고리: 드라마 출연료 역전, 연예인 스캔들/논란, 연예인 재산/자산 공개, KBO/스포츠 기록

## 오늘 네이버 랭킹 기사
{article_text}

## 최근 제작한 영상 (중복 피해야 함)
{history_text}

## 지시사항
위 기사들을 종합 분석해서, TOP10 숏츠 영상 주제를 5~8개 추천해주세요.

**중요 규칙:**
1. 같은 인물/팀이 여러 기사에 등장하면 하나의 주제로 통합
2. 단순 기사 요약이 아니라, 기사에서 파생되는 구체적 "TOP10 앵글"을 만들어야 함
   (예: "음주운전 기사" → "KBO 선수 음주운전 징계 TOP10")
3. 최근 제작한 영상과 겹치는 주제는 피하기 (또는 다른 앵글로)
4. 30~50대 남성이 궁금해할 돈/스포츠/논란/반전 앵글 우선

**반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력:**

```json
{{
  "topics": [
    {{
      "title": "30만+ 찍을 영상 제목 (따옴표 인용 + 숫자 + 의문문 패턴)",
      "angle": "이 주제의 핵심 앵글 한줄 설명",
      "research_instruction": "리서치할 때 구체적으로 뭘 찾아야 하는지 지시",
      "table_columns": ["컬럼1", "컬럼2", "컬럼3", "컬럼4"],
      "source_articles": ["관련 기사 제목1", "관련 기사 제목2"],
      "category": "연예" 또는 "스포츠" 또는 "혼합",
      "confidence": 1~10 (이 주제가 터질 확률)
    }}
  ]
}}
```"""
    return prompt


def call_gemini(prompt):
    """Gemini API 호출"""
    if not GEMINI_API_KEY:
        print("  ⚠ GEMINI_API_KEY 없음 — AI 분석 건너뜀")
        return None

    url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }

    try:
        r = requests.post(url, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()

        # 응답에서 텍스트 추출
        text = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                text = parts[0].get("text", "")

        if not text:
            print("  ⚠ Gemini 응답 비어있음")
            return None

        # JSON 파싱 (```json ... ``` 제거)
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)

        result = json.loads(text)
        return result

    except requests.exceptions.HTTPError as e:
        print(f"  ⚠ Gemini HTTP 에러: {e}")
        print(f"  응답: {e.response.text[:500] if e.response else 'N/A'}")
        return None
    except json.JSONDecodeError as e:
        print(f"  ⚠ Gemini JSON 파싱 실패: {e}")
        print(f"  원본: {text[:500]}")
        return None
    except Exception as e:
        print(f"  ⚠ Gemini 호출 실패: {e}")
        return None


def gemini_analyze(articles, history):
    """Gemini로 기사 종합 분석 → 주제 생성"""
    history_titles = [h["title"] for h in history]
    prompt = build_gemini_prompt(articles, history_titles)

    print("\n🤖 Gemini AI 분석 중...")
    print(f"  📨 기사 {len(articles)}개 전송 (연예 {sum(1 for a in articles if a['category']=='연예')}개 + 스포츠 {sum(1 for a in articles if a['category']=='스포츠')}개)")

    result = call_gemini(prompt)

    if not result or "topics" not in result:
        print("  ⚠ AI 분석 실패 — 폴백 (기본 키워드 분석)")
        return fallback_analyze(articles, history)

    topics = result["topics"]
    print(f"  ✅ AI 주제 {len(topics)}개 생성")

    # 중복 체크 + 관련 기사 URL 매핑
    enriched = []
    for t in topics:
        # 관련 기사에서 URL 찾기
        source_articles_with_url = []
        for src_title in t.get("source_articles", []):
            matched = None
            best_sim = 0
            for a in articles:
                sim = SequenceMatcher(None, src_title, a["title"]).ratio()
                if sim > best_sim:
                    best_sim = sim
                    matched = a
            if matched and best_sim > 0.4:
                source_articles_with_url.append({
                    "title": matched["title"],
                    "url": matched.get("url", ""),
                    "category": matched.get("category", ""),
                    "views": matched.get("views", 0),
                })

        dup = check_dup(t["title"], history)

        enriched.append({
            "title": t["title"],
            "angle": t.get("angle", ""),
            "research_instruction": t.get("research_instruction", ""),
            "table_columns": t.get("table_columns", ["이름", "분류", "내용", "비고"]),
            "source_articles": source_articles_with_url,
            "category": t.get("category", "연예"),
            "confidence": t.get("confidence", 5),
            "dup_check": dup,
            "ai_generated": True,
        })

    # 중복 아닌 것만
    valid = [t for t in enriched if not t["dup_check"]["is_duplicate"]]
    excluded = len(enriched) - len(valid)

    # confidence 순 정렬
    valid.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    print(f"  🎯 유효 주제: {len(valid)}개 (중복 제외: {excluded}개)")
    return valid, excluded


# ─────────────────────────────────────────────
# 폴백: Gemini 없을 때 기본 키워드 분석
# ─────────────────────────────────────────────
def fallback_analyze(articles, history):
    """Gemini 실패 시 기존 키워드 기반 분석"""
    print("  📊 키워드 빈도 기반 폴백 분석...")

    # 간단 키워드 카운팅
    kw_counter = Counter()
    for art in articles:
        words = set(re.findall(r"[가-힣]{2,}", art["title"])) - NOT_NAMES
        kw_counter.update(words)

    top_kw = kw_counter.most_common(10)
    topics = []
    for kw, cnt in top_kw[:5]:
        if cnt < 2:
            continue
        related = [a for a in articles if kw in a["title"]]
        best = max(related, key=lambda a: a.get("views", 0))
        title = f'"{kw}" 관련 화제 스타 TOP10'
        dup = check_dup(title, history)
        topics.append({
            "title": title,
            "angle": f"{kw} 관련 기사 {cnt}건에서 파생",
            "research_instruction": f"{kw} 관련 인물/사건 10개 조사",
            "table_columns": ["이름", "분류", "내용", "비고"],
            "source_articles": [{
                "title": best["title"],
                "url": best.get("url", ""),
                "category": best.get("category", ""),
                "views": best.get("views", 0),
            }],
            "category": best.get("category", "연예"),
            "confidence": min(cnt, 10),
            "dup_check": dup,
            "ai_generated": False,
        })

    valid = [t for t in topics if not t["dup_check"]["is_duplicate"]]
    excluded = len(topics) - len(valid)
    return valid, excluded


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def run_scan():
    t = datetime.now()
    print(f"\n{'='*60}")
    print(f"🔍 트렌드 스캔 v4.0 (Gemini AI): {t.strftime('%Y-%m-%d %H:%M:%S')}")
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
            print(f"    📌 {a['rank']}위 {a['title'][:50]}")
        time.sleep(1)

    # 폴백 체크
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
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)
    print(f"\n📋 총: {len(unique)}개")

    # ★ Gemini AI 분석
    topics, excluded = gemini_analyze(unique, history)

    # 키워드 빈도 (참고용)
    kw_counter = Counter()
    for art in unique:
        words = set(re.findall(r"[가-힣]{2,}", art["title"])) - NOT_NAMES
        kw_counter.update(words)

    name_counter = Counter()
    for art in unique:
        names = re.findall(r"[가-힣]{2,3}", art["title"])
        for n in names:
            if n not in NOT_NAMES:
                name_counter[n] += 1

    # 저장
    result = {
        "scan_time": t.strftime("%Y-%m-%d %H:%M:%S"),
        "scanner_version": "4.0",
        "source_stats": stats,
        "total_articles": len(unique),
        "total_topics_generated": len(topics) + excluded,
        "excluded_duplicates": excluded,
        "valid_topics": len(topics),
        "ai_analyzed": bool(GEMINI_API_KEY),
        "articles": unique,
        "topics": topics,
        "keyword_freq": kw_counter.most_common(20),
        "name_freq": name_counter.most_common(15),
    }

    # latest.json
    with open(DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 아카이브
    ts = t.strftime("%Y-%m-%d_%H%M")
    with open(DATA_DIR / f"scan_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 로그
    log_path = DATA_DIR / "scan_log.json"
    logs = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    logs.insert(0, {
        "time": result["scan_time"],
        "articles": len(unique),
        "topics": len(topics),
        "ai": result["ai_analyzed"],
        "file": f"scan_{ts}.json",
    })
    log_path.write_text(json.dumps(logs[:50], ensure_ascii=False, indent=2), encoding="utf-8")

    # 결과 출력
    print(f"\n{'='*60}")
    print(f"🎯 AI 추천 TOP 주제")
    print(f"{'='*60}")
    for i, tp in enumerate(topics[:8], 1):
        conf = tp.get('confidence', 0)
        marker = "🔥" if conf >= 8 else "✅" if conf >= 5 else "📌"
        print(f"  {i}. {marker} [{conf}/10] {tp['title']}")
        print(f"     앵글: {tp.get('angle', '')}")
        print(f"     컬럼: {' | '.join(tp.get('table_columns', []))}")
        src_arts = tp.get('source_articles', [])
        if src_arts:
            print(f"     ← {src_arts[0].get('title', '')[:50]}")
        print()

    if kw_counter:
        print(f"📊 키워드 TOP5: {', '.join(f'{k}({c})' for k,c in kw_counter.most_common(5))}")
    if name_counter:
        print(f"👤 인물 TOP5: {', '.join(f'{n}({c})' for n,c in name_counter.most_common(5))}")

    print(f"\n✅ 완료! latest.json 저장됨")


if __name__ == "__main__":
    run_scan()
