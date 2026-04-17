"""
============================================================
네이버 트렌드 스캐너 v2.2
- 인코딩 자동 감지 (EUC-KR/UTF-8)
- 범용 키워드 기반 파생 주제 생성 (유명인 없어도 생성)
- 30~50대 한국 남성 타겟 가중치 적용
- 455개 기존 영상 중복 체크 (4개월 / 8만회 기준)
============================================================
"""

import csv
import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
HISTORY_CSV = ROOT / "channel_history.csv"
DOCS = ROOT / "docs"
DATA_DIR = DOCS / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# 소스 URL (작동 확인된 것만)
# ─────────────────────────────────────────────
SOURCES = [
    {
        "name": "네이버 뉴스 랭킹 (전체)",
        "url": "https://news.naver.com/main/ranking/popularDay.naver",
        "category": "종합",
        "encoding": "euc-kr",
    },
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

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

MALE_TARGET_KEYWORDS = {
    "high": [
        "자산", "매출", "수입", "연봉", "몸값", "부동산", "빌딩", "건물", "재산",
        "억", "조원", "천만", "파산", "빚", "사기", "사업", "CEO", "기업", "투자",
        "KBO", "야구", "축구", "월드컵", "국대", "MLB", "FA",
        "이강인", "손흥민", "류현진", "이정후",
        "논란", "폭로", "충격", "적발", "고발", "입건",
        "도박", "탈세", "체납", "음주",
    ],
    "mid": [
        "근황", "복귀", "은퇴", "반전", "역대급",
        "드라마", "영화", "출연료", "회당",
        "결혼", "이혼", "재혼",
        "동갑", "혈연", "가족",
    ],
    "low": [
        "아이돌", "걸그룹", "보이그룹", "팬미팅", "팬싸",
        "뷰티", "메이크업", "패션", "스타일",
    ],
    "people_high": [
        "유재석", "강호동", "신동엽", "이경규", "탁재훈", "김구라",
        "손흥민", "이강인", "류현진", "이정후", "김도영",
        "송강호", "이병헌", "하정우", "마동석", "황정민",
        "이상민", "임창정", "김학래",
    ],
}

MONTHS_THRESHOLD = 3
MIN_VIEWS_FOR_REUSE = 80000


# ─────────────────────────────────────────────
# 채널 히스토리
# ─────────────────────────────────────────────
def load_channel_history():
    if not HISTORY_CSV.exists():
        return []
    history = []
    with open(HISTORY_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            history.append({
                "title": row["title"],
                "views": int(row.get("views", 0)),
                "published": row.get("published", ""),
            })
    return history


def parse_published_date(s):
    if not s: return None
    try: return datetime.strptime(s, "%b %d, %Y")
    except: return None


# ─────────────────────────────────────────────
# 크롤러
# ─────────────────────────────────────────────
class NaverCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Connection": "keep-alive",
        })

    def fetch(self, url, encoding="utf-8"):
        try:
            r = self.session.get(url, timeout=15)
            r.raise_for_status()

            # ★ 핵심 수정: 인코딩 자동 감지
            # 1) 소스에서 지정한 인코딩 시도
            try:
                text = r.content.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                pass
            else:
                return text, r.status_code

            # 2) HTML meta charset 확인
            meta_match = re.search(rb'charset=["\']?([a-zA-Z0-9_-]+)', r.content[:2000])
            if meta_match:
                charset = meta_match.group(1).decode("ascii", errors="ignore")
                try:
                    text = r.content.decode(charset)
                    return text, r.status_code
                except (UnicodeDecodeError, LookupError):
                    pass

            # 3) UTF-8 폴백
            text = r.content.decode("utf-8", errors="replace")
            return text, r.status_code

        except requests.HTTPError as e:
            code = e.response.status_code if e.response else 0
            print(f"  ⚠ HTTP {code}: {url}")
            return None, code
        except Exception as e:
            print(f"  ⚠ 오류: {url} → {e}")
            return None, 0

    def extract_articles(self, html, source):
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        seen = set()

        # 네이버 기사 URL 패턴
        news_re = re.compile(r"(n\.news\.naver\.com|news\.naver\.com.*article|entertain\.naver\.com.*read|sports\.news\.naver)")

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("/"):
                href = urljoin(source["url"], href)
            if not news_re.search(href):
                continue

            # 제목 추출
            title = ""
            for sub in ["strong", "em", "span"]:
                el = a.find(sub)
                if el:
                    t = el.get_text(strip=True)
                    if len(t) > len(title):
                        title = t
            if not title:
                title = a.get_text(strip=True)

            title = self._clean(title)
            if len(title) < 8:
                continue

            key = hashlib.md5(title.encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)

            articles.append({
                "title": title,
                "url": href,
                "source_url": href,
                "source": source["name"],
                "category": source["category"],
            })

        return articles[:60]

    @staticmethod
    def _clean(t):
        t = re.sub(r"\[.*?\]", "", t)
        t = re.sub(r"<[^>]+>", "", t)
        t = re.split(r"[|···…]", t)[0]
        return t.strip()


# ─────────────────────────────────────────────
# 앵글 추출 + 파생 주제 생성 (v2.2 - 공격적)
# ─────────────────────────────────────────────
# 키워드 → 파생 주제 매핑 (유명인 없어도 키워드만으로 생성)
KEYWORD_TOPIC_MAP = [
    # (키워드 패턴, 파생 주제 제목, 앵글 타입, 표 템플릿)
    (r"음주.?운전|음주.?적발|음주.?사고", "연예계 음주운전 적발 스타 TOP10", "논란", "논란 집합"),
    (r"이혼|파경|결별", "이혼 후 더 잘된 스타 TOP10", "결혼·이혼", "이혼 반전"),
    (r"결혼|웨딩|혼인", "화제의 결혼 발표 스타 TOP10", "결혼·이혼", "결혼 화제"),
    (r"열애|연인|교제", "공개 열애 후 결별한 스타 커플 TOP10", "결혼·이혼", "열애 결별"),
    (r"사기|횡령|배임|편취", "사기 피해 거액 날린 스타 TOP10", "논란", "논란 집합"),
    (r"탈세|체납|세금", "세금 논란 휘말린 스타 TOP10", "논란", "논란 집합"),
    (r"도박|불법\s?도박", "도박 논란 스타 TOP10", "논란", "논란 집합"),
    (r"복귀|컴백|돌아오", "긴 공백 깨고 돌아온 스타 TOP10", "복귀", "장기 공백 복귀"),
    (r"은퇴|마지막|고별", "은퇴 후 반전 인생 스타 TOP10", "복귀", "장기 공백 복귀"),
    (r"투병|완치|수술|입원|병원", "투병 이겨내고 복귀한 스타 TOP10", "질병·복귀", "투병 극복"),
    (r"자산|재산|부동산|빌딩|건물주", "연예인 숨은 부동산 자산 TOP10", "금액·자산", "자산 서열"),
    (r"\d+억|\d+조|매출|수익|연봉", "연예인 자산 서열 TOP10", "금액·자산", "자산 서열"),
    (r"몸값|출연료|회당|개런티", "드라마 출연료 역대급 스타 TOP10", "금액·자산", "자산 서열"),
    (r"FA|트레이드|이적", "역대 FA 대박 vs 쪽박 TOP10", "스포츠·몸값", "선수 몸값"),
    (r"홈런|안타|삼진|타율", "KBO 역대급 기록 TOP10", "스포츠·기록", "스포츠 기록"),
    (r"골|어시|해트트릭|클린시트", "축구 역대급 기록 TOP10", "스포츠·기록", "스포츠 기록"),
    (r"동갑|동기|같은\s?나이", "의외의 동갑 스타 TOP10", "나이", "동갑내기"),
    (r"근황|현재|지금", "화제의 스타 근황 TOP10", "복귀", "장기 공백 복귀"),
    (r"논란|물의|비난|비판|갑질", "올해 최대 논란 스타 TOP10", "논란", "논란 집합"),
    (r"학력|서울대|연세대|고려대|SKY", "의외의 SKY 출신 스타 TOP10", "학력", "학력 서열"),
    (r"군대|전역|입대|군복무", "전역 후 대박 난 스타 TOP10", "복귀", "장기 공백 복귀"),
]

# 표 템플릿 정의
TABLE_TEMPLATES = {
    "동갑내기": ("이름", "나이", "대표작", "추정 자산"),
    "연령대 근황": ("이름", "나이", "데뷔년도", "현재 활동"),
    "투병 극복": ("이름", "투병 질환", "공백기", "복귀 작품"),
    "장기 공백 복귀": ("이름", "공백 기간", "공백 사유", "복귀 작품"),
    "자산 서열": ("이름", "주요 수입원", "추정 자산", "자산 특이점"),
    "논란 집합": ("이름", "소속·직업", "논란 내용", "현재 상황"),
    "이혼 반전": ("이름", "이혼 시점", "이혼 전 상황", "이혼 후 성과"),
    "결혼 화제": ("이름", "배우자", "결혼 시점", "화제 포인트"),
    "열애 결별": ("스타A", "스타B", "열애 기간", "결별 후 근황"),
    "선수 몸값": ("선수", "소속팀", "당시 몸값", "현재 평가"),
    "스포츠 기록": ("선수", "소속팀", "기록 내용", "기록 가치"),
    "별명 계보": ("이름", "활동 시기", "대표작", "현재 근황"),
    "학력 서열": ("이름", "학교·전공", "대표작", "현재 활동"),
    "인맥": ("인물A", "인물B", "관계", "에피소드"),
}


def generate_topics_from_article(article):
    """기사 제목에서 키워드 기반으로 파생 주제 생성 (v2.2)"""
    title = article["title"]
    topics = []
    matched = set()

    # 1) 키워드 매핑으로 주제 생성
    for pattern, topic_title, angle_type, template in KEYWORD_TOPIC_MAP:
        if re.search(pattern, title) and topic_title not in matched:
            matched.add(topic_title)
            topics.append({
                "title": topic_title,
                "angle_type": angle_type,
                "template": template,
                "seed": f"'{title[:30]}' 에서 파생",
            })

    # 2) 금액 추출해서 자산 주제 생성
    money_match = re.search(r"(\d+[,.]?\d*)\s*(억|조|천만)", title)
    if money_match and "자산 서열" not in [t["title"] for t in topics]:
        amount = money_match.group(0)
        topics.append({
            "title": f"{amount} 넘는 스타들 자산 서열 TOP10",
            "angle_type": "금액·자산",
            "template": "자산 서열",
            "seed": f"{amount} 언급",
        })

    # 3) 유명인 이름 기반 주제 (다른 주제가 없을 때 폴백)
    if not topics:
        # 2~4글자 한글 이름 패턴
        names = re.findall(r"[가-힣]{2,4}", title)
        names = [n for n in names if n not in {"기자", "뉴스", "속보", "단독", "한국", "대한", "정부", "국민", "사회", "경제", "정치", "문화", "생활", "세계", "국제", "사건", "사고", "오늘", "내일", "어제"}]
        if names:
            main = names[0]
            topics.append({
                "title": f"{main} 관련 화제 스타 TOP10",
                "angle_type": "인물 화제",
                "template": "인맥",
                "seed": f"{main} 언급",
            })

    return topics[:4]


def score_topic(topic, article_title=""):
    """30~50대 남성 타겟 적합도 점수"""
    score = 5.0
    text = topic["title"] + " " + article_title

    for kw in MALE_TARGET_KEYWORDS["high"]:
        if kw in text: score += 0.5
    for kw in MALE_TARGET_KEYWORDS["mid"]:
        if kw in text: score += 0.3
    for kw in MALE_TARGET_KEYWORDS["low"]:
        if kw in text: score -= 0.6

    angle_boost = {
        "금액·자산": 1.5, "논란": 1.3, "스포츠·몸값": 1.5, "스포츠·기록": 1.2,
        "나이": 0.8, "결혼·이혼": 0.5, "질병·복귀": 1.0, "복귀": 0.9,
        "별명·계보": 0.7, "인물 화제": 0.5, "학력": 0.9,
    }
    score += angle_boost.get(topic["angle_type"], 0)

    for p in MALE_TARGET_KEYWORDS["people_high"]:
        if p in text:
            score += 0.4
            break

    return max(0, min(10, round(score, 1)))


def check_duplicate(topic_title, history):
    """455개 영상과 비교"""
    from difflib import SequenceMatcher
    now = datetime.now()

    result = {"is_duplicate": False, "status": "통과", "matched_title": "", "matched_views": 0, "reason": ""}

    topic_kw = set(re.findall(r"[가-힣]{2,}", topic_title))
    topic_kw -= {"연예인", "연예계", "소식", "TOP", "TOP10", "스타", "스타들"}

    best_match, best_sim = None, 0
    for hist in history:
        hist_kw = set(re.findall(r"[가-힣]{2,}", hist["title"]))
        hist_kw -= {"연예인", "연예계", "소식", "TOP", "TOP10", "스타", "스타들"}
        str_sim = SequenceMatcher(None, topic_title, hist["title"]).ratio()
        overlap = len(topic_kw & hist_kw) / min(len(topic_kw), len(hist_kw)) if topic_kw and hist_kw else 0
        combined = str_sim * 0.3 + overlap * 0.7
        if combined > best_sim:
            best_sim = combined
            best_match = hist

    if best_sim >= 0.55 and best_match:
        pub_date = parse_published_date(best_match["published"])
        views = best_match["views"]
        can_reuse = False
        days_passed = (now - pub_date).days if pub_date else 0
        # 3개월+ 경과 AND 8만+ 조회 → 재활용 (검증된 주제, 다시 터질 가능성 높음)
        if days_passed >= MONTHS_THRESHOLD * 30 and views >= MIN_VIEWS_FOR_REUSE:
            can_reuse = True
            result["reason"] = f"검증됨 {views:,}회, {days_passed}일 경과"
        # 3개월+ 경과 AND 8만 미만 → 재활용 (실패했지만 기간 지남)
        elif days_passed >= MONTHS_THRESHOLD * 30:
            can_reuse = True
            result["reason"] = f"기간 경과 {days_passed}일 (조회 {views:,})"
        if can_reuse:
            result["status"] = "재활용 가능"
        else:
            result["is_duplicate"] = True
            result["status"] = "중복 제외"
            result["reason"] = f"{views:,}회, 최근"
        result["matched_title"] = best_match["title"]
        result["matched_views"] = views

    return result


def make_table(template_name):
    """캔바 복사용 TSV 표 생성"""
    headers = TABLE_TEMPLATES.get(template_name, ("이름", "분류", "내용", "비고"))
    lines = ["\t".join(headers)]
    for i in range(1, 11):
        lines.append(f"{i}위\t\t\t")
    return {"headers": list(headers), "tsv": "\n".join(lines)}


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def run_scan():
    scan_time = datetime.now()
    print(f"\n{'='*60}")
    print(f"🔍 네이버 트렌드 스캔 v2.2: {scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    crawler = NaverCrawler()
    history = load_channel_history()
    print(f"📚 채널 히스토리: {len(history)}개 영상")

    all_articles = []
    source_stats = {}

    for src in SOURCES:
        print(f"\n📡 {src['name']}...")
        print(f"   URL: {src['url']}")
        enc = src.get("encoding", "utf-8")
        html, status = crawler.fetch(src["url"], encoding=enc)

        if not html:
            source_stats[src["name"]] = 0
            continue

        # 디버그
        soup_debug = BeautifulSoup(html, "html.parser")
        all_a = soup_debug.find_all("a", href=True)
        news_a = [a for a in all_a if "article" in a.get("href", "")]
        print(f"  📊 HTML {len(html):,}자 | <a> {len(all_a)}개 | 뉴스링크 {len(news_a)}개")

        # 샘플 제목 (한글 인코딩 확인용)
        for a in news_a[:3]:
            t = a.get_text(strip=True)[:50]
            print(f"  📌 샘플: {t}")

        articles = crawler.extract_articles(html, src)
        all_articles.extend(articles)
        source_stats[src["name"]] = len(articles)
        print(f"  ✅ {len(articles)}개 수집")
        time.sleep(1.5)

    # 중복 제거
    seen = set()
    unique = []
    for a in all_articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)

    print(f"\n📋 중복 제거 후: {len(unique)}개")

    # 파생 주제 생성
    print(f"\n💡 파생 주제 생성 중...")
    all_topics = []
    for article in unique:
        topics = generate_topics_from_article(article)
        for topic in topics:
            topic["score"] = score_topic(topic, article["title"])
            topic["dup_check"] = check_duplicate(topic["title"], history)
            topic["source_article"] = article["title"]
            topic["source_name"] = article["source"]
            topic["source_url"] = article.get("source_url", article.get("url", ""))
            topic["table"] = make_table(topic["template"])
            all_topics.append(topic)

    print(f"  생성: {len(all_topics)}개")

    # 중복 제거 + 같은 제목 합치기
    seen_titles = set()
    deduped = []
    for t in all_topics:
        if t["title"] not in seen_titles:
            seen_titles.add(t["title"])
            deduped.append(t)

    valid = [t for t in deduped if not t["dup_check"]["is_duplicate"]]
    valid.sort(key=lambda t: t["score"], reverse=True)
    excluded = len(deduped) - len(valid)
    print(f"  고유 주제: {len(deduped)}개 | 중복 제외: {excluded}개 | 통과: {len(valid)}개")

    top = [t for t in valid if t["score"] >= 5.5][:30]
    print(f"  최종 추천: {len(top)}개 (5.5+)")

    result = {
        "scan_time": scan_time.strftime("%Y-%m-%d %H:%M:%S"),
        "scan_time_iso": scan_time.isoformat(),
        "source_stats": source_stats,
        "total_articles": len(unique),
        "total_topics_generated": len(all_topics),
        "excluded_duplicates": excluded,
        "valid_topics": len(valid),
        "articles": unique,
        "topics": top,
        "all_topics": valid,
    }

    # 저장
    with open(DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    archive_name = scan_time.strftime("%Y-%m-%d_%H%M")
    with open(DATA_DIR / f"scan_{archive_name}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 로그
    log_path = DATA_DIR / "scan_log.json"
    logs = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    logs.insert(0, {"time": result["scan_time"], "articles": len(unique), "topics": len(top), "file": f"scan_{archive_name}.json"})
    log_path.write_text(json.dumps(logs[:50], ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"🎯 TOP 5 추천")
    print(f"{'='*60}")
    for i, t in enumerate(top[:5], 1):
        print(f"  {i}. [{t['score']}] {t['title']}")
        print(f"     ← {t['source_article'][:50]}")
        print(f"     {t['dup_check']['status']}")

    return result


if __name__ == "__main__":
    run_scan()
