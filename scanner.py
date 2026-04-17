"""
============================================================
네이버 트렌드 스캐너 v3.0
- 네이버 엔터/스포츠 JSON API 직접 호출
- 전체 기사 키워드/인물 빈도 분석 → 통합 주제 도출
- 30만+ 영상 제목 패턴 적용
- 30~50대 남성 타겟 가중치
- 3개월 + 8만회 이상 재활용
============================================================
"""

import csv
import json
import re
import time
import hashlib
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
HISTORY_CSV = ROOT / "channel_history.csv"
DATA_DIR = ROOT / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.now().strftime("%Y%m%d")

# ─────────────────────────────────────────────
# 소스: 네이버 JSON API
# ─────────────────────────────────────────────
SOURCES = [
    {
        "name": "엔터 많이 본 뉴스",
        "url": f"https://api-gw.entertain.naver.com/ranking/most-viewed?date={TODAY}&pageSize=30",
        "category": "연예",
        "referer": "https://m.entertain.naver.com/ranking",
    },
    {
        "name": "스포츠 많이 본 뉴스",
        "url": f"https://api-gw.sports.naver.com/news/rankings/popular?date={TODAY}",
        "category": "스포츠",
        "referer": "https://m.sports.naver.com/ranking/index",
    },
]

# 폴백: JSON API 실패 시 HTML 크롤링
FALLBACK_SOURCES = [
    {
        "name": "네이버 뉴스 랭킹 (연예)",
        "url": "https://news.naver.com/main/ranking/popularDay.naver?mid=etc&sid1=106",
        "category": "연예",
        "encoding": "euc-kr",
    },
    {
        "name": "네이버 뉴스 랭킹 (스포츠)",
        "url": "https://news.naver.com/main/ranking/popularDay.naver?mid=etc&sid1=107",
        "category": "스포츠",
        "encoding": "euc-kr",
    },
]

MONTHS_THRESHOLD = 3
MIN_VIEWS_FOR_REUSE = 80000

# 30~50대 남성 타겟 키워드
TARGET_HIGH = set("자산 매출 수입 연봉 몸값 부동산 빌딩 건물 재산 억 조원 천만 파산 빚 사기 사업 CEO 기업 투자 KBO 야구 축구 월드컵 MLB FA 논란 폭로 충격 적발 고발 입건 도박 탈세 체납 음주 이강인 손흥민 류현진 이정후".split())
TARGET_MID = set("근황 복귀 은퇴 반전 역대급 드라마 영화 출연료 회당 결혼 이혼 재혼 동갑 혈연 가족".split())
TARGET_LOW = set("아이돌 걸그룹 보이그룹 팬미팅 팬싸 뷰티 메이크업 패션 스타일".split())
TARGET_PEOPLE = set("유재석 강호동 신동엽 이경규 탁재훈 김구라 손흥민 이강인 류현진 이정후 김도영 송강호 이병헌 하정우 마동석 황정민 이상민 임창정 김학래".split())

# 제목에서 제거할 불용어
STOP_WORDS = set("기자 뉴스 속보 단독 한국 대한 정부 국민 사회 경제 정치 서울 부산 오늘 내일 어제 올해 지난 이번 해당 관련 전했 밝혔 보도 발표 기사 네이버 스포츠 연예인 연예계 소식 TOP TOP10 스타 스타들 종합 이슈 라며 했다 됐다 있다 없다 된다 한다 시선 화제 세계 국제 뉴시스 데일리 조선 일보 시사 포토 영상".split())


# ─────────────────────────────────────────────
# 채널 히스토리
# ─────────────────────────────────────────────
def load_history():
    if not HISTORY_CSV.exists():
        return []
    rows = []
    with open(HISTORY_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"title": r["title"], "views": int(r.get("views", 0)), "published": r.get("published", "")})
    return rows


def parse_date(s):
    try:
        return datetime.strptime(s, "%b %d, %Y")
    except:
        return None


# ─────────────────────────────────────────────
# API 크롤러
# ─────────────────────────────────────────────
class Crawler:
    def __init__(self):
        self.session = requests.Session()

    def fetch_json(self, src):
        """JSON API 호출"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": src.get("referer", "https://m.entertain.naver.com/"),
            "Origin": src.get("referer", "https://m.entertain.naver.com").rsplit("/", 1)[0],
        }
        try:
            r = self.session.get(src["url"], headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            return self._extract_from_json(data, src)
        except Exception as e:
            print(f"  ⚠ API 실패: {e}")
            return []

    def _extract_from_json(self, data, src):
        """JSON 응답에서 기사 목록 추출 (여러 구조 대응)"""
        articles = []

        # 가능한 리스트 키들 탐색
        items = []
        if isinstance(data, list):
            items = data
        else:
            for key in ["results", "data", "articles", "list", "items", "rankings", "newsList"]:
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    break
            # 중첩 구조 탐색
            if not items:
                for k, v in data.items():
                    if isinstance(v, dict):
                        for k2, v2 in v.items():
                            if isinstance(v2, list) and len(v2) > 0:
                                items = v2
                                break
                    elif isinstance(v, list) and len(v) > 0:
                        items = v
                        break

        print(f"  📊 JSON 파싱: {len(items)}개 항목 발견")
        if items and isinstance(items[0], dict):
            print(f"  📌 키 구조: {list(items[0].keys())[:10]}")

        for item in items[:30]:
            if not isinstance(item, dict):
                continue

            # 제목 추출 (여러 키 시도)
            title = ""
            for tk in ["title", "articleTitle", "newsTitle", "headline", "subject"]:
                if tk in item and item[tk]:
                    title = str(item[tk]).strip()
                    break

            if not title or len(title) < 8:
                continue

            # URL 추출
            url = ""
            for uk in ["articleLink", "link", "url", "articleUrl", "newsUrl", "pcLink", "mobileLink"]:
                if uk in item and item[uk]:
                    url = str(item[uk]).strip()
                    break

            # 조회수
            views = 0
            for vk in ["readCount", "viewCount", "views", "hitCount", "totalCount"]:
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
        """HTML 크롤링 폴백"""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            r = self.session.get(src["url"], headers=headers, timeout=15)
            r.raise_for_status()
            text = r.content.decode(src.get("encoding", "utf-8"), errors="replace")

            soup = BeautifulSoup(text, "html.parser")
            articles = []
            seen = set()
            news_re = re.compile(r"(n\.news\.naver\.com|news\.naver\.com.*article)")

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not news_re.search(href):
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
                articles.append({"title": title, "url": href, "source": src["name"], "category": src["category"], "views": 0, "rank": len(articles)+1})

            return articles[:30]
        except Exception as e:
            print(f"  ⚠ 폴백 실패: {e}")
            return []


# ─────────────────────────────────────────────
# 핵심: 키워드/인물 빈도 분석 → 통합 주제 도출
# ─────────────────────────────────────────────
def analyze_and_generate_topics(articles, history):
    """전체 기사에서 키워드·인물 빈도 분석 → 통합 주제 생성"""

    # 1) 전체 키워드 빈도 분석
    kw_counter = Counter()
    name_counter = Counter()  # 2~3글자 인물 이름 후보
    article_by_keyword = {}  # 키워드 → 원본 기사 매핑

    for art in articles:
        title = art["title"]
        words = set(re.findall(r"[가-힣]{2,}", title))
        words -= STOP_WORDS

        for w in words:
            kw_counter[w] += 1
            if w not in article_by_keyword:
                article_by_keyword[w] = art

        # 이름 후보 (2~3글자, 특히 고빈도)
        names = re.findall(r"[가-힣]{2,3}", title)
        for n in names:
            if n not in STOP_WORDS and len(n) >= 2:
                name_counter[n] += 1

    # 2) 앵글 감지 (기사 전체에서 어떤 주제가 많은지)
    angle_patterns = {
        "자산·몸값":   (r"자산|재산|연봉|몸값|부동산|빌딩|매출|수익|출연료|개런티", "💰"),
        "논란·사건":   (r"논란|폭로|고발|적발|음주|사기|탈세|도박|갑질|비난|물의", "😱"),
        "결혼·이혼":   (r"결혼|이혼|열애|재혼|파혼|임신|출산", "💍"),
        "복귀·근황":   (r"복귀|근황|컴백|돌아|은퇴|전역|공백", "🔄"),
        "투병·건강":   (r"투병|완치|수술|입원|암|희귀병|재활", "🏥"),
        "스포츠기록":  (r"홈런|안타|골|우승|신기록|FA|트레이드|MVP|연봉", "⚾"),
        "가족·혈연":   (r"가족|혈연|동갑|형제|부모|2세|자녀", "👨‍👩‍👧"),
    }

    angle_scores = {}
    angle_articles = {}
    for angle, (pattern, emoji) in angle_patterns.items():
        matched = [a for a in articles if re.search(pattern, a["title"])]
        if matched:
            angle_scores[angle] = len(matched)
            angle_articles[angle] = matched

    # 3) 통합 주제 생성 (빈도 기반)
    topics = []
    used_angles = set()

    # 상위 빈도 인물로 주제 생성
    top_names = name_counter.most_common(10)
    top_keywords = kw_counter.most_common(30)

    # 앵글별로 하나의 통합 주제만 생성
    sorted_angles = sorted(angle_scores.items(), key=lambda x: x[1], reverse=True)

    for angle, count in sorted_angles:
        if count < 2:
            continue  # 기사 2개 이상이어야 주제 생성

        pattern, emoji = angle_patterns[angle]
        matched_arts = angle_articles[angle]

        # 해당 앵글에서 가장 많이 언급된 인물 찾기
        angle_names = Counter()
        for a in matched_arts:
            names = re.findall(r"[가-힣]{2,3}", a["title"])
            for n in names:
                if n not in STOP_WORDS:
                    angle_names[n] += 1

        top_person = angle_names.most_common(1)[0][0] if angle_names else ""

        # 채널 제목 패턴 적용 (30만+ 영상 패턴)
        title = _make_title(angle, top_person, top_keywords, matched_arts)

        # 원본 기사 (가장 조회수 높은 것)
        best_art = max(matched_arts, key=lambda a: a.get("views", 0))

        topics.append({
            "title": title,
            "angle_type": f"{emoji} {angle}",
            "article_count": count,
            "source_article": best_art["title"],
            "source_url": best_art.get("url", ""),
            "source_name": best_art.get("source", ""),
            "related_names": [n for n, c in angle_names.most_common(5)],
            "template": _angle_to_template(angle),
        })

    # 4) 고빈도 인물 기반 주제 (앵글과 별개로)
    for name, cnt in top_names:
        if cnt < 3:
            break  # 3회 이상 등장한 인물만

        # 이 인물이 어떤 맥락에서 언급되는지 파악
        person_articles = [a for a in articles if name in a["title"]]
        context = _detect_person_context(name, person_articles)

        if context and len(topics) < 20:
            best_art = max(person_articles, key=lambda a: a.get("views", 0))
            topics.append({
                "title": context["title"],
                "angle_type": f"👤 인물 화제 ({name})",
                "article_count": cnt,
                "source_article": best_art["title"],
                "source_url": best_art.get("url", ""),
                "source_name": best_art.get("source", ""),
                "related_names": [name],
                "template": context["template"],
            })

    # 5) 점수 매기기 + 중복 체크
    for topic in topics:
        topic["score"] = _score(topic)
        topic["dup_check"] = _check_dup(topic["title"], history)
        topic["table"] = {"headers": list(_get_headers(topic["template"])), "tsv": ""}

    # 정렬 + 필터
    topics.sort(key=lambda t: t["score"], reverse=True)
    valid = [t for t in topics if not t["dup_check"]["is_duplicate"]]

    return {
        "topics": valid[:20],
        "keyword_freq": top_keywords,
        "name_freq": top_names,
        "angle_scores": sorted_angles,
    }


def _make_title(angle, person, top_kw, articles):
    """30만+ 영상 제목 패턴 적용"""
    # 채널 히트 패턴: "따옴표 인용" + 구체 금액 + 의문문(?) + 반전
    templates = {
        "자산·몸값": [
            f'"{person}, 자산이 이 정도였다고?" 연예인 숨은 자산 서열 TOP10' if person else '"숨은 부자였다고?" 연예인 자산 서열 TOP10',
            f'"{person} 빌딩만 몇 채?" 연예계 부동산 부자 TOP10' if person else '"빌딩이 몇 채야?" 연예계 부동산 갑부 TOP10',
        ],
        "논란·사건": [
            f'"{person}까지 이럴 줄은..." 올해 팬들 분노 터진 스타 TOP10' if person else '"이럴 줄은 몰랐다" 올해 팬들 충격 받은 스타 TOP10',
        ],
        "결혼·이혼": [
            f'"{person} 결혼 상대가 누구?" 화제의 결혼 발표 스타 TOP10' if person else '"남편이 누구길래?" 화제의 결혼 스타 TOP10',
        ],
        "복귀·근황": [
            f'"{person}, 지금 뭐하고 있을까?" 근황 궁금한 스타 TOP10' if person else '"그때 그 사람, 지금은?" 근황 궁금한 스타 TOP10',
        ],
        "투병·건강": [
            '"죽을 고비 넘기고 돌아왔다" 투병 이겨낸 스타 TOP10',
        ],
        "스포츠기록": [
            f'"{person}, 역대급 기록 갱신?" 역대 레전드 기록 TOP10' if person else '"이 기록은 깨질 수 없다" 역대급 스포츠 기록 TOP10',
        ],
        "가족·혈연": [
            f'"{person}이랑 형제였다고?" 알고 보니 놀라운 연예계 가족 TOP10' if person else '"이 둘이 가족이라고?" 놀라운 연예계 혈연 TOP10',
        ],
    }

    options = templates.get(angle, [f'화제의 스타 TOP10'])
    return options[0]


def _detect_person_context(name, articles):
    """인물이 어떤 맥락에서 언급되는지 파악"""
    combined = " ".join(a["title"] for a in articles)

    contexts = [
        (r"논란|폭로|사건|사고", {"title": f'"{name}, 대체 무슨 일이?" {name} 관련 이슈 총정리', "template": "논란 집합"}),
        (r"결혼|열애|이혼", {"title": f'"{name} 결혼설?" {name} 연애사 총정리 TOP10', "template": "결혼 화제"}),
        (r"복귀|근황|컴백", {"title": f'"{name}, 지금 어디서 뭐 하나?" {name} 근황과 비슷한 스타들', "template": "장기 공백 복귀"}),
        (r"자산|연봉|몸값|억", {"title": f'"{name} 자산이 얼마?" {name}급 자산가 스타 TOP10', "template": "자산 서열"}),
    ]

    for pattern, result in contexts:
        if re.search(pattern, combined):
            return result

    return {"title": f'"{name}" 관련 화제 스타 TOP10', "template": "인맥"}


def _angle_to_template(angle):
    mapping = {
        "자산·몸값": "자산 서열",
        "논란·사건": "논란 집합",
        "결혼·이혼": "결혼 화제",
        "복귀·근황": "장기 공백 복귀",
        "투병·건강": "투병 극복",
        "스포츠기록": "스포츠 기록",
        "가족·혈연": "동갑내기",
    }
    return mapping.get(angle, "인맥")


def _get_headers(template):
    templates = {
        "자산 서열": ("이름", "주요 수입원", "추정 자산", "자산 특이점"),
        "논란 집합": ("이름", "소속·직업", "논란 내용", "현재 상황"),
        "결혼 화제": ("이름", "배우자", "결혼 시점", "화제 포인트"),
        "장기 공백 복귀": ("이름", "공백 기간", "공백 사유", "복귀 작품"),
        "투병 극복": ("이름", "투병 질환", "공백기", "복귀 작품"),
        "스포츠 기록": ("선수", "소속팀", "기록 내용", "기록 가치"),
        "동갑내기": ("이름", "나이", "대표작", "현재 활동"),
        "인맥": ("이름", "분류", "이슈 내용", "현재 상황"),
    }
    return templates.get(template, ("이름", "분류", "내용", "비고"))


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

    # 기사 수 보너스 (많이 언급된 주제일수록)
    count = topic.get("article_count", 1)
    if count >= 5: score += 1.5
    elif count >= 3: score += 1.0
    elif count >= 2: score += 0.5

    return max(0, min(10, round(score, 1)))


def _check_dup(title, history):
    from difflib import SequenceMatcher
    now = datetime.now()
    result = {"is_duplicate": False, "status": "통과", "matched_title": "", "matched_views": 0, "reason": ""}

    title_kw = set(re.findall(r"[가-힣]{2,}", title)) - STOP_WORDS
    best, best_sim = None, 0

    for h in history:
        h_kw = set(re.findall(r"[가-힣]{2,}", h["title"])) - STOP_WORDS
        s1 = SequenceMatcher(None, title, h["title"]).ratio()
        overlap = len(title_kw & h_kw) / min(len(title_kw), len(h_kw)) if title_kw and h_kw else 0
        combined = s1 * 0.3 + overlap * 0.7
        if combined > best_sim:
            best_sim = combined
            best = h

    if best_sim >= 0.55 and best:
        pub = parse_date(best["published"])
        views = best["views"]
        days = (now - pub).days if pub else 0

        if days >= MONTHS_THRESHOLD * 30 and views >= MIN_VIEWS_FOR_REUSE:
            result["status"] = "재활용 가능"
            result["reason"] = f"검증됨 {views:,}회 · {days}일 경과"
        elif days >= MONTHS_THRESHOLD * 30:
            result["status"] = "재활용 가능"
            result["reason"] = f"기간 경과 {days}일"
        else:
            result["is_duplicate"] = True
            result["status"] = "중복 제외"
            result["reason"] = f"{views:,}회 · 최근"

        result["matched_title"] = best["title"]
        result["matched_views"] = views

    return result


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def run_scan():
    scan_time = datetime.now()
    print(f"\n{'='*60}")
    print(f"🔍 트렌드 스캔 v3.0: {scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    crawler = Crawler()
    history = load_history()
    print(f"📚 히스토리: {len(history)}개 영상")

    all_articles = []
    stats = {}

    # JSON API 시도
    for src in SOURCES:
        print(f"\n📡 {src['name']}...")
        print(f"   {src['url']}")
        arts = crawler.fetch_json(src)
        stats[src["name"]] = len(arts)
        all_articles.extend(arts)
        print(f"  ✅ {len(arts)}개")
        if arts:
            for a in arts[:3]:
                print(f"  📌 {a['rank']}위 [{a.get('views',0):,}회] {a['title'][:50]}")
        time.sleep(1)

    # JSON 실패 시 폴백
    total_json = sum(stats.values())
    if total_json < 10:
        print(f"\n⚠️ JSON API 수집 부족 ({total_json}개). HTML 폴백 시도...")
        for src in FALLBACK_SOURCES:
            print(f"\n📡 [폴백] {src['name']}...")
            arts = crawler.fetch_html_fallback(src)
            stats[src["name"]] = len(arts)
            all_articles.extend(arts)
            print(f"  ✅ {len(arts)}개")
            time.sleep(1)

    # 중복 제거
    seen = set()
    unique = []
    for a in all_articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)

    print(f"\n📋 총 수집: {len(unique)}개 고유 기사")

    # 핵심: 키워드 분석 → 통합 주제 생성
    print(f"\n💡 키워드 분석 + 통합 주제 생성 중...")
    analysis = analyze_and_generate_topics(unique, history)

    topics = analysis["topics"]
    print(f"  생성 주제: {len(topics)}개")
    print(f"  키워드 TOP5: {', '.join(f'{k}({c})' for k, c in analysis['keyword_freq'][:5])}")
    print(f"  인물 TOP5: {', '.join(f'{n}({c})' for n, c in analysis['name_freq'][:5])}")

    # 결과 저장
    result = {
        "scan_time": scan_time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_stats": stats,
        "total_articles": len(unique),
        "total_topics_generated": len(topics),
        "excluded_duplicates": sum(1 for t in topics if t["dup_check"]["is_duplicate"]),
        "valid_topics": len([t for t in topics if not t["dup_check"]["is_duplicate"]]),
        "articles": unique,
        "topics": topics,
        "all_topics": topics,
        "keyword_freq": analysis["keyword_freq"],
        "name_freq": analysis["name_freq"],
        "angle_scores": analysis["angle_scores"],
    }

    with open(DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    ts = scan_time.strftime("%Y-%m-%d_%H%M")
    with open(DATA_DIR / f"scan_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log_path = DATA_DIR / "scan_log.json"
    logs = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    logs.insert(0, {"time": result["scan_time"], "articles": len(unique), "topics": len(topics), "file": f"scan_{ts}.json"})
    log_path.write_text(json.dumps(logs[:50], ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"🎯 TOP 5")
    print(f"{'='*60}")
    for i, t in enumerate(topics[:5], 1):
        dup = t["dup_check"]["status"]
        print(f"  {i}. [{t['score']}] {t['title']}")
        print(f"     기사 {t['article_count']}건 | {dup}")
        print(f"     ← {t['source_article'][:50]}")


if __name__ == "__main__":
    run_scan()
