"""
============================================================
네이버 트렌드 스캐너 v2.1 (서버사이드 랭킹 페이지 사용)
- 네이버 뉴스 랭킹 (popularDay) / 스포츠 랭킹 크롤링
- 기사에서 파생 TOP10 주제 자동 생성
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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# 경로 설정
# ─────────────────────────────────────────────
ROOT = Path(__file__).parent
HISTORY_CSV = ROOT / "channel_history.csv"
DOCS = ROOT / "docs"
DATA_DIR = DOCS / "data"
ARCHIVE_DIR = DOCS / "archive"

DATA_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
# 서버사이드 렌더링되는 네이버 랭킹 페이지 (안정적)
SOURCES = [
    {
        "name": "네이버 뉴스 랭킹 (전체 많이 본)",
        "url": "https://news.naver.com/main/ranking/popularDay.naver",
        "category": "종합",
        "parser": "ranking_page",
    },
    {
        "name": "네이버 엔터 랭킹",
        "url": "https://m.entertain.naver.com/ranking",
        "category": "연예",
        "parser": "entertain_mobile",
    },
    {
        "name": "네이버 엔터 5분 랭킹",
        "url": "https://m.entertain.naver.com/ranking/five",
        "category": "연예",
        "parser": "entertain_mobile",
    },
    {
        "name": "네이버 스포츠 랭킹",
        "url": "https://m.sports.naver.com/ranking/index",
        "category": "스포츠",
        "parser": "sports_mobile",
    },
    {
        "name": "네이버 스포츠 메인",
        "url": "https://m.sports.naver.com/index",
        "category": "스포츠",
        "parser": "sports_mobile",
    },
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# 타겟층: 30~50대 한국 남성
MALE_TARGET_KEYWORDS = {
    "high": [
        "자산", "매출", "수입", "연봉", "몸값", "부동산", "빌딩", "건물", "재산",
        "억", "조원", "천만",
        "파산", "빚", "사기", "사업", "CEO", "기업", "회사", "투자", "주식",
        "KBO", "야구", "축구", "월드컵", "국대", "프리미어", "MLB", "FA",
        "이강인", "손흥민", "류현진", "이정후",
        "논란", "폭로", "충격", "적발", "고발", "조사", "입건",
        "도박", "탈세", "체납", "음주",
    ],
    "mid": [
        "근황", "복귀", "은퇴", "반전", "역대급", "충격",
        "1박", "무한도전", "런닝맨", "나혼산", "미우새",
        "드라마", "영화", "출연료", "회당",
        "결혼", "이혼", "재혼",
        "동갑", "혈연", "가족", "형제",
    ],
    "low": [
        "아이돌", "걸그룹", "보이그룹", "팬미팅", "팬싸",
        "뷰티", "메이크업", "패션", "스타일", "코디", "OOTD",
        "브이로그", "데일리",
    ],
    "people_high": [
        "유재석", "강호동", "신동엽", "이경규", "탁재훈", "김구라",
        "차범근", "홍명보", "박지성", "손흥민", "이강인", "이승우",
        "류현진", "김광현", "양현종", "오타니", "이정후", "김도영",
        "송강호", "이병헌", "하정우", "마동석", "황정민",
        "이상민", "이진호", "김학래",
    ],
}

MONTHS_THRESHOLD = 4
MIN_VIEWS_FOR_REUSE = 80000


# ─────────────────────────────────────────────
# 채널 히스토리 로드
# ─────────────────────────────────────────────
def load_channel_history():
    if not HISTORY_CSV.exists():
        print(f"⚠️ {HISTORY_CSV} 없음 - 중복 체크 비활성화")
        return []
    history = []
    with open(HISTORY_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            history.append({
                "title": row["title"],
                "views": int(row.get("views", 0)),
                "published": row.get("published", ""),
            })
    return history


def parse_published_date(date_str):
    if not date_str: return None
    try:
        return datetime.strptime(date_str, "%b %d, %Y")
    except:
        return None


# ─────────────────────────────────────────────
# 크롤러 (v2 - 유연한 파싱)
# ─────────────────────────────────────────────
class NaverCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })
    
    def fetch(self, url):
        try:
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text, r.status_code
        except requests.HTTPError as e:
            code = e.response.status_code if e.response else 0
            print(f"  ⚠ HTTP {code}: {url}")
            return None, code
        except Exception as e:
            print(f"  ⚠ 오류: {url} → {e}")
            return None, 0
    
    def extract_articles(self, html, source):
        """소스 타입에 따라 적절한 파서 선택 + 범용 파서로 폴백"""
        parser_type = source.get("parser", "generic")
        
        articles = []
        if parser_type == "ranking_page":
            articles = self._parse_ranking_page(html, source)
        elif parser_type == "entertain_mobile":
            articles = self._parse_entertain_mobile(html, source)
        elif parser_type == "sports_mobile":
            articles = self._parse_sports_mobile(html, source)
        
        # 결과 없으면 범용 파서로 폴백
        if not articles:
            print(f"  🔄 범용 파서로 재시도...")
            articles = self._parse_generic(html, source)
        
        return articles[:50]
    
    def _parse_ranking_page(self, html, source):
        """네이버 뉴스 랭킹 페이지 (popularDay.naver) - 섹션별 TOP5 리스트"""
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        seen = set()
        
        # 랭킹 페이지의 기사 리스트 셀렉터들
        selectors = [
            "div.rankingnews_box ul.rankingnews_list li a",
            "ul.rankingnews_list li a.list_title",
            "div.rankingnews_box a[href*='/article/']",
            "ul li a[href*='news.naver.com/mnews']",
            "a[href*='/article/']",
        ]
        
        for selector in selectors:
            for a in soup.select(selector):
                href = a.get("href", "").strip()
                title = a.get_text(strip=True)
                
                if not title or len(title) < 10:
                    continue
                if href.startswith("/"):
                    href = urljoin(source["url"], href)
                
                # 네이버 기사 URL 필터
                if not re.search(r"(news\.naver\.com|n\.news\.naver\.com|entertain\.naver|sports\.news\.naver)", href):
                    continue
                
                key = hashlib.md5(title.encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                
                articles.append({
                    "title": self.clean_title(title),
                    "url": href,
                    "source": source["name"],
                })
        
        return articles
    
    def _parse_entertain_mobile(self, html, source):
        """m.entertain.naver.com 파서 (여러 구조 시도)"""
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        seen = set()
        
        selectors = [
            "a.NewsItem_link__qbw2e",          # 2024~ 네이버 엔터 모바일
            "a[class*='NewsItem']",
            "a[class*='ItemList']",
            "li[class*='list_item'] a",
            "a[href*='entertain.naver.com/read']",
            "a[href*='entertain.naver.com/now/read']",
            "a[href*='entertain.naver.com/home/read']",
        ]
        
        for selector in selectors:
            for a in soup.select(selector):
                href = a.get("href", "").strip()
                
                # 제목 추출 (다양한 내부 요소)
                title = ""
                for sub in ["strong", "h3", "h4", "span", "em"]:
                    el = a.find(sub)
                    if el:
                        t = el.get_text(strip=True)
                        if len(t) > len(title):
                            title = t
                if not title:
                    title = a.get_text(strip=True)
                
                if not title or len(title) < 10:
                    continue
                if href.startswith("/"):
                    href = urljoin(source["url"], href)
                
                key = hashlib.md5(title.encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                
                articles.append({
                    "title": self.clean_title(title),
                    "url": href,
                    "source": source["name"],
                })
        
        return articles
    
    def _parse_sports_mobile(self, html, source):
        """m.sports.naver.com 파서"""
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        seen = set()
        
        selectors = [
            "a[class*='NewsItem']",
            "a[class*='PromotionNews']",
            "a[class*='PopularNews']",
            "a[class*='list_item']",
            "a[href*='sports.news.naver.com/news']",
            "a[href*='m.sports.naver.com']",
        ]
        
        for selector in selectors:
            for a in soup.select(selector):
                href = a.get("href", "").strip()
                
                title = ""
                for sub in ["strong", "h3", "h4", "span.text", "span.title", "em"]:
                    el = a.select_one(sub)
                    if el:
                        t = el.get_text(strip=True)
                        if len(t) > len(title):
                            title = t
                if not title:
                    title = a.get_text(strip=True)
                
                if not title or len(title) < 10:
                    continue
                if href.startswith("/"):
                    href = urljoin(source["url"], href)
                
                key = hashlib.md5(title.encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                
                articles.append({
                    "title": self.clean_title(title),
                    "url": href,
                    "source": source["name"],
                })
        
        return articles
    
    def _parse_generic(self, html, source):
        """범용 파서: 모든 <a> 태그에서 네이버 뉴스 링크 추출"""
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        seen = set()
        
        # 네이버 뉴스 URL 패턴
        news_patterns = [
            re.compile(r"entertain\.naver\.com/(read|now/read|home/read)"),
            re.compile(r"m\.entertain\.naver\.com/(read|article)"),
            re.compile(r"sports\.news\.naver\.com/news"),
            re.compile(r"m\.sports\.naver\.com/.+/article"),
            re.compile(r"news\.naver\.com/.*article"),
            re.compile(r"n\.news\.naver\.com/mnews/article"),
        ]
        
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("/"):
                href = urljoin(source["url"], href)
            
            if not any(p.search(href) for p in news_patterns):
                continue
            
            # 제목 추출
            title = ""
            for sub in ["strong", "h3", "h4", "em"]:
                el = a.find(sub)
                if el:
                    t = el.get_text(strip=True)
                    if len(t) > len(title):
                        title = t
            if not title:
                title = a.get_text(strip=True)
            
            title = self.clean_title(title)
            if len(title) < 10:
                continue
            
            key = hashlib.md5(title.encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            
            articles.append({
                "title": title,
                "url": href,
                "source": source["name"],
            })
        
        return articles
    
    @staticmethod
    def clean_title(title):
        title = re.sub(r"\[.*?\]", "", title)
        title = re.sub(r"<[^>]+>", "", title)
        title = re.split(r"[|···…]", title)[0]
        title = title.strip()
        return title
    
    def debug_html(self, html, source_name):
        """디버깅 정보 출력"""
        if not html:
            return
        soup = BeautifulSoup(html, "html.parser")
        all_links = soup.find_all("a", href=True)
        news_links = [a for a in all_links if re.search(r"(naver\.com.*article|naver\.com.*read)", a.get("href", ""))]
        
        print(f"  📊 디버그: HTML {len(html):,}자, <a> {len(all_links)}개, 네이버 뉴스 링크 {len(news_links)}개")
        
        # 네이버 뉴스 링크 샘플 3개
        if news_links:
            print(f"  📌 샘플 링크:")
            for a in news_links[:3]:
                title = a.get_text(strip=True)[:40]
                href = a.get("href", "")[:60]
                print(f"     - {title} | {href}")


# ─────────────────────────────────────────────
# 앵글 추출기
# ─────────────────────────────────────────────
class AngleExtractor:
    AGE_PATTERN = re.compile(r"(\d{2})살|(\d{2})세|마흔|쉰|예순|(\d{2})대")
    MONEY_PATTERN = re.compile(r"(\d+[,.]?\d*)\s*(억|조|천만|백만|만원)")
    ILLNESS_PATTERN = re.compile(r"(완치|투병|수술|입원|병|암|희귀|재활|회복)")
    COMEBACK_PATTERN = re.compile(r"(복귀|컴백|귀환|돌아|근황|공백|\d+\s*년\s*만)")
    SCANDAL_PATTERN = re.compile(r"(논란|폭로|고발|적발|입건|조사|벌금|기소|음주|사기|탈세|도박)")
    MARRIAGE_PATTERN = re.compile(r"(결혼|이혼|재혼|열애|연애|파혼)")
    SPORT_PATTERN = re.compile(r"(KBO|MLB|월드컵|골|홈런|우승|금메달|은메달|FA|트레이드|연봉)")
    
    CELEBRITIES = {
        "문근영", "이정재", "정우성", "김태희", "전지현", "송혜교", "송중기",
        "공유", "공효진", "박서준", "이종석", "김수현", "수지", "아이유",
        "유재석", "강호동", "신동엽", "박나래", "김종국", "이광수",
        "손흥민", "이강인", "류현진", "이정후", "오타니", "김연경", "박지성",
        "정형돈", "정준하", "박명수", "하하", "노홍철",
        "이상민", "탁재훈", "김구라", "이진호", "임창정",
        "방시혁", "이수만", "박진영", "양현석",
        "BTS", "블랙핑크", "뉴진스", "아이브", "르세라핌",
        "지드래곤", "태양", "빅뱅", "정국", "뷔", "지민", "RM",
    }
    
    def extract(self, article):
        title = article["title"]
        angles = {
            "title": title,
            "source": article["source"],
            "url": article.get("url", ""),
            "people": [],
            "ages": [],
            "moneys": [],
            "nicknames": [],
            "tags": [],
            "sport_keywords": [],
        }
        
        for person in self.CELEBRITIES:
            if person in title:
                angles["people"].append(person)
        
        quoted = re.findall(r"['\"]([가-힣]{2,4})['\"]", title)
        for q in quoted:
            if q not in angles["people"] and len(q) >= 2:
                angles["people"].append(q)
        
        for m in self.AGE_PATTERN.finditer(title):
            age_str = m.group(0)
            if "마흔" in age_str: angles["ages"].append(40)
            elif "쉰" in age_str: angles["ages"].append(50)
            elif "예순" in age_str: angles["ages"].append(60)
            else:
                for g in m.groups():
                    if g and g.isdigit():
                        angles["ages"].append(int(g))
                        break
        
        for m in self.MONEY_PATTERN.finditer(title):
            angles["moneys"].append(m.group(0))
        
        if self.ILLNESS_PATTERN.search(title): angles["tags"].append("질병·건강")
        if self.COMEBACK_PATTERN.search(title): angles["tags"].append("공백·복귀")
        if self.SCANDAL_PATTERN.search(title): angles["tags"].append("논란·폭로")
        if self.MARRIAGE_PATTERN.search(title): angles["tags"].append("결혼·이혼")
        if self.SPORT_PATTERN.search(title): angles["tags"].append("스포츠")
        if self.MONEY_PATTERN.search(title): angles["tags"].append("금액·자산")
        if self.AGE_PATTERN.search(title): angles["tags"].append("나이")
        
        nick_matches = re.findall(r"['\"]([^'\"]{2,15})['\"]", title)
        angles["nicknames"] = [n for n in nick_matches if "국민" in n or "원조" in n or "미녀" in n]
        
        sport_matches = self.SPORT_PATTERN.findall(title)
        angles["sport_keywords"] = sport_matches
        
        return angles


# ─────────────────────────────────────────────
# 파생 주제 생성기
# ─────────────────────────────────────────────
class TopicGenerator:
    def __init__(self):
        self.history = load_channel_history()
    
    def generate(self, angle):
        topics = []
        title = angle["title"]
        people = angle["people"]
        tags = angle["tags"]
        ages = angle["ages"]
        moneys = angle["moneys"]
        
        main_person = people[0] if people else ""
        
        if ages:
            age = ages[0]
            decade = (age // 10) * 10
            topics.append({
                "title": f"올해 {age}세 동갑 톱스타 자산 TOP10",
                "angle_type": "나이", "seed": f"{main_person} {age}세 언급" if main_person else f"{age}세",
                "template": "동갑내기",
            })
            topics.append({
                "title": f"{decade}대 맞은 스타들, 지금 몸값과 근황 TOP10",
                "angle_type": "나이", "seed": f"{age}대 진입", "template": "연령대 근황",
            })
        
        if "질병·건강" in tags:
            topics.append({
                "title": f"희귀병·중병 이겨내고 복귀한 스타 TOP10",
                "angle_type": "질병·복귀", "seed": f"{main_person} 완치" if main_person else "완치",
                "template": "투병 극복",
            })
            topics.append({
                "title": f"건강 때문에 장기 공백 거친 스타들 현재는? TOP10",
                "angle_type": "질병·근황", "seed": "투병 후 근황", "template": "투병 근황",
            })
        
        if "공백·복귀" in tags and "질병·건강" not in tags:
            topics.append({
                "title": f"긴 공백 깨고 돌아온 스타 TOP10",
                "angle_type": "복귀", "seed": f"{main_person} 복귀" if main_person else "복귀",
                "template": "장기 공백 복귀",
            })
        
        if moneys and main_person:
            money_str = moneys[0]
            topics.append({
                "title": f"{money_str} 넘는 스타들 자산 서열 TOP10",
                "angle_type": "금액·자산", "seed": f"{main_person} {money_str}", "template": "자산 서열",
            })
        elif "금액·자산" in tags:
            topics.append({
                "title": f"알려지지 않은 연예인 숨은 자산 TOP10",
                "angle_type": "금액·자산", "seed": "자산 언급", "template": "자산 서열",
            })
        
        if "논란·폭로" in tags:
            scandal_type = "음주" if "음주" in title else "도박" if "도박" in title else "사기" if "사기" in title else "논란"
            topics.append({
                "title": f"연예계 {scandal_type} 사건 연루된 스타 TOP10",
                "angle_type": "논란", "seed": f"{main_person} {scandal_type}" if main_person else scandal_type,
                "template": "논란 집합",
            })
        
        if "결혼·이혼" in tags:
            if "이혼" in title or "재혼" in title:
                topics.append({
                    "title": f"이혼 후 더 잘된 스타 TOP10",
                    "angle_type": "결혼·이혼", "seed": f"{main_person} 이혼" if main_person else "이혼",
                    "template": "이혼 반전",
                })
            elif "열애" in title or "공개" in title:
                topics.append({
                    "title": f"공개 열애 후 결별한 스타 커플 TOP10",
                    "angle_type": "결혼·이혼", "seed": f"{main_person} 열애" if main_person else "열애",
                    "template": "열애 결별",
                })
        
        if "스포츠" in tags:
            sport_kw = angle["sport_keywords"][0] if angle["sport_keywords"] else "스포츠"
            if "FA" in sport_kw or "연봉" in sport_kw or "MLB" in sport_kw:
                topics.append({
                    "title": f"{sport_kw} 대박 vs 쪽박 선수 몸값 반전 TOP10",
                    "angle_type": "스포츠·몸값", "seed": f"{main_person} {sport_kw}" if main_person else sport_kw,
                    "template": "선수 몸값",
                })
            elif "홈런" in sport_kw or "골" in sport_kw or "우승" in sport_kw:
                topics.append({
                    "title": f"{sport_kw} 관련 역대급 기록 TOP10",
                    "angle_type": "스포츠·기록", "seed": f"{sport_kw} 기록", "template": "스포츠 기록",
                })
        
        if angle["nicknames"]:
            nick = angle["nicknames"][0]
            topics.append({
                "title": f"역대 '{nick}' 계보 현재 근황 TOP10",
                "angle_type": "별명·계보", "seed": f"{nick} 계보", "template": "별명 계보",
            })
        
        if main_person and not topics:
            topics.append({
                "title": f"{main_person}과 연결된 연예계 인맥·관계 TOP10",
                "angle_type": "인물 인맥", "seed": main_person, "template": "인맥",
            })
        
        return topics[:5]
    
    def score_topic(self, topic, original_article_title=""):
        score = 5.0
        text = topic["title"] + " " + original_article_title
        
        for kw in MALE_TARGET_KEYWORDS["high"]:
            if kw in text: score += 0.5
        for kw in MALE_TARGET_KEYWORDS["mid"]:
            if kw in text: score += 0.3
        for kw in MALE_TARGET_KEYWORDS["low"]:
            if kw in text: score -= 0.6
        
        angle_boost = {
            "금액·자산": 1.5, "논란": 1.3, "스포츠·몸값": 1.5, "스포츠·기록": 1.2,
            "나이": 0.8, "결혼·이혼": 0.5, "질병·복귀": 1.0, "복귀": 0.9,
            "별명·계보": 0.7, "인물 인맥": 0.6,
        }
        score += angle_boost.get(topic["angle_type"], 0)
        
        for p in MALE_TARGET_KEYWORDS["people_high"]:
            if p in text:
                score += 0.4
                break
        
        return max(0, min(10, round(score, 1)))
    
    def check_duplicate(self, topic_title):
        from difflib import SequenceMatcher
        now = datetime.now()
        
        result = {
            "is_duplicate": False, "status": "통과",
            "matched_title": "", "matched_views": 0, "reason": "",
        }
        
        topic_keywords = set(re.findall(r"[가-힣]{2,}", topic_title))
        topic_keywords = {k for k in topic_keywords if k not in {"연예인", "연예계", "소식", "TOP", "TOP10"}}
        
        best_match = None
        best_sim = 0
        
        for hist in self.history:
            hist_title = hist["title"]
            str_sim = SequenceMatcher(None, topic_title, hist_title).ratio()
            hist_kw = set(re.findall(r"[가-힣]{2,}", hist_title))
            hist_kw = {k for k in hist_kw if k not in {"연예인", "연예계", "소식", "TOP", "TOP10"}}
            
            overlap = 0
            if topic_keywords and hist_kw:
                overlap = len(topic_keywords & hist_kw) / min(len(topic_keywords), len(hist_kw))
            
            combined_sim = str_sim * 0.3 + overlap * 0.7
            if combined_sim > best_sim:
                best_sim = combined_sim
                best_match = hist
        
        if best_sim >= 0.55 and best_match:
            pub_date = parse_published_date(best_match["published"])
            views = best_match["views"]
            can_reuse = False
            
            if pub_date and (now - pub_date).days >= MONTHS_THRESHOLD * 30:
                can_reuse = True
                result["reason"] = f"4개월+ 경과 ({(now - pub_date).days}일 전)"
            if views < MIN_VIEWS_FOR_REUSE:
                can_reuse = True
                result["reason"] = f"조회수 {views:,} (8만 미달)"
            
            if can_reuse:
                result["status"] = "재활용 가능"
                result["matched_title"] = best_match["title"]
                result["matched_views"] = views
            else:
                result["is_duplicate"] = True
                result["status"] = "중복 제외"
                result["matched_title"] = best_match["title"]
                result["matched_views"] = views
                result["reason"] = f"{views:,}회, 최근 업로드"
        
        return result


# ─────────────────────────────────────────────
# 표 템플릿
# ─────────────────────────────────────────────
def generate_table_template(topic):
    template = topic["template"]
    templates = {
        "동갑내기": ("이름", "나이", "대표작", "추정 자산"),
        "연령대 근황": ("이름", "나이", "데뷔년도", "현재 활동"),
        "투병 극복": ("이름", "투병 질환", "공백기", "복귀 작품"),
        "투병 근황": ("이름", "투병 질환", "당시 상황", "현재 근황"),
        "장기 공백 복귀": ("이름", "공백 기간", "공백 사유", "복귀 작품"),
        "자산 서열": ("이름", "주요 수입원", "추정 자산", "자산 특이점"),
        "논란 집합": ("이름", "소속·직업", "논란 내용", "현재 상황"),
        "이혼 반전": ("이름", "이혼 시점", "이혼 전 상황", "이혼 후 성과"),
        "열애 결별": ("여자 스타", "남자 스타", "열애 기간", "결별 후 근황"),
        "선수 몸값": ("선수", "소속팀", "당시 몸값", "현재 평가"),
        "스포츠 기록": ("선수", "소속팀", "기록 내용", "기록 가치"),
        "별명 계보": ("이름", "활동 시기", "대표작", "현재 근황"),
        "인맥": ("인물A", "인물B", "관계", "연결 에피소드"),
    }
    headers = templates.get(template, ("이름", "분류", "내용", "비고"))
    rows = [[f"{i}위", "", "", ""] for i in range(1, 11)]
    tsv_lines = ["\t".join(headers)]
    for row in rows:
        tsv_lines.append("\t".join(row))
    return {"headers": list(headers), "tsv": "\n".join(tsv_lines)}


# ─────────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────────
def run_scan():
    scan_time = datetime.now()
    print(f"\n{'='*60}")
    print(f"🔍 네이버 트렌드 스캔 시작: {scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    crawler = NaverCrawler()
    extractor = AngleExtractor()
    generator = TopicGenerator()
    
    print(f"📚 채널 히스토리 로드: {len(generator.history)}개 영상")
    
    all_articles = []
    source_stats = {}
    
    for src in SOURCES:
        print(f"\n📡 {src['name']} 크롤링...")
        print(f"   URL: {src['url']}")
        html, status = crawler.fetch(src["url"])
        
        if not html:
            print(f"   ❌ 실패 (HTTP {status})")
            source_stats[src["name"]] = 0
            continue
        
        # 디버그 정보
        crawler.debug_html(html, src["name"])
        
        # 파싱
        articles = crawler.extract_articles(html, src)
        for a in articles:
            a["category"] = src["category"]
        
        all_articles.extend(articles)
        source_stats[src["name"]] = len(articles)
        print(f"  ✅ {len(articles)}개 기사 수집")
        time.sleep(1.5)
    
    # 중복 제거
    seen = set()
    unique_articles = []
    for a in all_articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique_articles.append(a)
    
    print(f"\n📋 중복 제거 후: {len(unique_articles)}개 고유 기사")
    
    # 파생 주제 생성
    print(f"\n💡 파생 주제 생성 중...")
    all_topics = []
    for article in unique_articles:
        angle = extractor.extract(article)
        topics = generator.generate(angle)
        for topic in topics:
            topic["score"] = generator.score_topic(topic, article["title"])
            topic["dup_check"] = generator.check_duplicate(topic["title"])
            topic["source_article"] = article["title"]
            topic["source_name"] = article["source"]
            topic["table"] = generate_table_template(topic)
            all_topics.append(topic)
    
    print(f"  생성된 주제: {len(all_topics)}개")
    
    valid_topics = [t for t in all_topics if not t["dup_check"]["is_duplicate"]]
    valid_topics.sort(key=lambda t: t["score"], reverse=True)
    excluded = len(all_topics) - len(valid_topics)
    print(f"  중복 제외: {excluded}개 / 통과: {len(valid_topics)}개")
    
    top_topics = [t for t in valid_topics if t["score"] >= 6.0][:30]
    print(f"  최종 추천: {len(top_topics)}개 (점수 6.0+)")
    
    result = {
        "scan_time": scan_time.strftime("%Y-%m-%d %H:%M:%S"),
        "scan_time_iso": scan_time.isoformat(),
        "source_stats": source_stats,
        "total_articles": len(unique_articles),
        "total_topics_generated": len(all_topics),
        "excluded_duplicates": excluded,
        "valid_topics": len(valid_topics),
        "articles": unique_articles,
        "topics": top_topics,
        "all_topics": valid_topics,
    }
    
    latest_path = DATA_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    archive_name = scan_time.strftime("%Y-%m-%d_%H%M")
    archive_path = DATA_DIR / f"scan_{archive_name}.json"
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    log_path = DATA_DIR / "scan_log.json"
    logs = []
    if log_path.exists():
        with open(log_path, encoding="utf-8") as f:
            logs = json.load(f)
    logs.insert(0, {
        "time": scan_time.strftime("%Y-%m-%d %H:%M:%S"),
        "articles": len(unique_articles),
        "topics": len(top_topics),
        "file": f"scan_{archive_name}.json",
    })
    logs = logs[:50]
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 저장 완료: {latest_path}")
    print(f"\n{'='*60}")
    print(f"🎯 TOP 5 추천")
    print(f"{'='*60}")
    for i, t in enumerate(top_topics[:5], 1):
        print(f"  {i}. [{t['score']}] {t['title']}")
        print(f"     원본: {t['source_article'][:50]}")
    
    return result


if __name__ == "__main__":
    run_scan()
