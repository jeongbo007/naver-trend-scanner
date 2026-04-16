"""
============================================================
실시간 채널 데이터 분석기
- 사용자가 붙여넣은 "실시간 업데이트 중" 데이터 파싱
- 60분 조회수 급상승 영상 = 현재 알고리즘이 밀어주는 영상
- 유사 앵글로 파생 주제 추천
============================================================
"""

import re
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "docs" / "data"


def parse_realtime_text(text):
    """
    사용자가 붙여넣은 실시간 데이터 파싱
    
    예상 입력 형식:
    "지예은♥바타 열애 인정?" 역대 댄서 연애·결혼 이슈 TOP 10 #연예인 #연예계소식
    2026. 4. 13.
    388,183
    8,070
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    
    videos = []
    i = 0
    while i < len(lines):
        # 제목 찾기 (일정 길이 이상)
        if len(lines[i]) < 15:
            i += 1
            continue
        
        title = lines[i]
        
        # 날짜 찾기 (다음 줄이 날짜 형식?)
        date_match = None
        if i + 1 < len(lines):
            date_match = re.match(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", lines[i+1])
        
        if not date_match:
            i += 1
            continue
        
        # 48시간 조회수 + 60분 조회수
        views_48h = 0
        views_60m = 0
        
        if i + 2 < len(lines):
            v48 = re.sub(r"[^\d]", "", lines[i+2])
            if v48: views_48h = int(v48)
        
        if i + 3 < len(lines):
            v60 = re.sub(r"[^\d]", "", lines[i+3])
            if v60: views_60m = int(v60)
        
        if views_48h > 0:
            videos.append({
                "title": title,
                "date": date_match.group(0),
                "views_48h": views_48h,
                "views_60m": views_60m,
            })
            i += 4
        else:
            i += 1
    
    return videos


def analyze_algorithm_signals(videos):
    """
    알고리즘 신호 분석
    - 60분 조회수 / 48시간 조회수 비율로 급상승도 측정
    - 급상승 영상의 공통 키워드/앵글 추출
    """
    if not videos:
        return {}
    
    # 급상승도 점수 계산
    for v in videos:
        # 최근 60분 = 1시간. 48시간 = 48시간.
        # 시간당 평균 조회수 대비 현재 60분 조회수의 배율
        avg_per_hour_48 = v["views_48h"] / 48 if v["views_48h"] else 0
        v["surge_ratio"] = (v["views_60m"] / avg_per_hour_48) if avg_per_hour_48 > 0 else 0
        v["surge_score"] = v["views_60m"] * min(v["surge_ratio"], 3)  # 급상승 보정
    
    # 급상승 TOP 10 (60분 조회수 기준)
    by_60m = sorted(videos, key=lambda v: v["views_60m"], reverse=True)[:10]
    
    # 지금 밀리고 있는 영상 (60분 기준 가속도 높음)
    by_surge = sorted(videos, key=lambda v: v["surge_score"], reverse=True)[:10]
    
    # 공통 키워드 추출
    from collections import Counter
    all_words = []
    
    # 상위 10개에서 키워드 추출
    for v in by_60m:
        title = v["title"]
        # 해시태그 제거
        title = re.sub(r"#\S+", "", title)
        # 따옴표 속 문구 추출
        quoted = re.findall(r'"([^"]+)"', title)
        for q in quoted:
            all_words.extend([w for w in q.split() if len(w) >= 2])
        # 일반 단어
        words = re.findall(r"[가-힣A-Za-z]{2,}", title)
        all_words.extend(words)
    
    stopwords = {"연예인", "연예계소식", "연예계", "TOP", "TOP10", "TOP 10", "스타", "스타들"}
    keyword_freq = Counter([w for w in all_words if w not in stopwords])
    
    # 앵글 키워드 감지
    angle_signals = {}
    angle_keywords = {
        "몸값·반전": ["몸값", "반전", "회당", "연봉", "변화", "상승률"],
        "자산·금액": ["자산", "매출", "재산", "억", "빚", "빌딩", "부동산"],
        "논란·폭로": ["논란", "폭로", "고발", "적발", "사기"],
        "이혼·결혼": ["이혼", "결혼", "열애", "재혼"],
        "동갑·나이": ["동갑", "살", "세", "년생"],
        "가족·혈연": ["가족", "혈연", "아빠", "엄마", "형제", "자매"],
        "복귀·근황": ["근황", "복귀", "컴백", "공백"],
        "프로그램·드라마": ["출연진", "드라마", "예능", "1박", "미우새", "나혼산"],
        "스포츠": ["KBO", "야구", "축구", "선수", "골프", "FA"],
    }
    
    for angle, kws in angle_keywords.items():
        hits = []
        for v in by_60m:
            if any(kw in v["title"] for kw in kws):
                hits.append(v)
        if hits:
            angle_signals[angle] = {
                "count": len(hits),
                "total_views_60m": sum(h["views_60m"] for h in hits),
                "avg_views_60m": sum(h["views_60m"] for h in hits) / len(hits),
                "videos": [{"title": h["title"], "views_60m": h["views_60m"]} for h in hits],
            }
    
    # 가장 알고리즘이 밀어주는 앵글
    top_angles = sorted(angle_signals.items(), key=lambda x: x[1]["avg_views_60m"], reverse=True)
    
    return {
        "total_videos": len(videos),
        "total_views_60m": sum(v["views_60m"] for v in videos),
        "total_views_48h": sum(v["views_48h"] for v in videos),
        "top_by_60m": by_60m,
        "top_by_surge": by_surge,
        "top_keywords": keyword_freq.most_common(20),
        "angle_signals": angle_signals,
        "top_angles": [{"angle": a, **info} for a, info in top_angles[:5]],
    }


def generate_recommendations(analysis, naver_topics=None):
    """
    알고리즘 신호 + 네이버 트렌드 교차 분석해서 추천 주제 생성
    """
    if not analysis or not analysis.get("top_angles"):
        return []
    
    recommendations = []
    
    # 1) 알고리즘이 밀어주는 앵글 × 네이버 최신 트렌드 교차
    top_angles = analysis["top_angles"]
    
    if naver_topics:
        for topic in naver_topics[:20]:  # 네이버 TOP20
            topic_text = topic["title"]
            
            # 어느 앵글과 매칭되는지 확인
            for angle_info in top_angles[:3]:  # 상위 3개 앵글
                angle = angle_info["angle"]
                angle_kws = {
                    "몸값·반전": ["몸값", "반전", "회당", "연봉"],
                    "자산·금액": ["자산", "매출", "재산", "억", "빚"],
                    "논란·폭로": ["논란", "폭로", "사기"],
                    "이혼·결혼": ["이혼", "결혼", "열애"],
                    "동갑·나이": ["동갑", "나이", "세"],
                    "가족·혈연": ["가족", "혈연"],
                    "복귀·근황": ["근황", "복귀", "공백"],
                    "스포츠": ["KBO", "야구", "축구"],
                }.get(angle, [])
                
                if any(kw in topic_text for kw in angle_kws):
                    # 교차 히트!
                    recommendations.append({
                        "type": "교차 추천",
                        "topic": topic_text,
                        "reason": f"📡 네이버에서 '{topic.get('source_article', '')[:30]}' 기사 노출 + ⚡ 내 채널 '{angle}' 앵글이 지금 알고리즘 호조",
                        "angle": angle,
                        "score": topic.get("score", 5) + 2,  # 교차 보너스
                        "algo_boost": f"{angle} 앵글 영상 평균 60분 조회 {int(angle_info['avg_views_60m']):,}회",
                    })
    
    # 2) 알고리즘 앵글 단독 추천 (네이버와 매칭 안 된 경우 보완)
    if len(recommendations) < 5:
        for angle_info in top_angles[:3]:
            angle = angle_info["angle"]
            sample_video = angle_info["videos"][0] if angle_info["videos"] else None
            
            suggestions = {
                "몸값·반전": [
                    "드라마 출연진 10년 뒤 몸값 대반전 TOP10",
                    "아이돌 출신 연기 전향, 몸값 역전 스타 TOP10",
                ],
                "자산·금액": [
                    "알려지지 않은 숨은 부자 스타 자산 서열 TOP10",
                    "연예인 빌딩 투자 시세차익 TOP10",
                ],
                "논란·폭로": [
                    "2026년 올해 최대 논란 휘말린 스타 TOP10",
                    "팬들 분노 폭발한 연예계 발언 TOP10",
                ],
                "이혼·결혼": [
                    "이혼 후 자산·몸값 수직 상승한 스타 TOP10",
                    "비연예인과 결혼한 스타 커플 근황 TOP10",
                ],
                "동갑·나이": [
                    "같은 해 데뷔 동기, 지금 위상 차이 TOP10",
                    "의외의 연예계 동갑 콤비 TOP10",
                ],
                "가족·혈연": [
                    "연예계 숨겨진 사촌·삼촌 관계 TOP10",
                    "스타 집안 3대 계보 총정리 TOP10",
                ],
                "복귀·근황": [
                    "10년 만에 돌아온 스타들, 지금 근황 TOP10",
                    "은퇴 선언 후 번복한 스타 TOP10",
                ],
                "스포츠": [
                    "KBO 레전드 2세 근황 총정리 TOP10",
                    "메이저리그 도전 한국 선수 성적 TOP10",
                ],
            }
            
            for sugg in suggestions.get(angle, []):
                recommendations.append({
                    "type": "알고리즘 단독",
                    "topic": sugg,
                    "reason": f"⚡ '{angle}' 앵글이 지금 알고리즘이 밀어주는 주제 (60분 평균 {int(angle_info['avg_views_60m']):,}회)",
                    "angle": angle,
                    "score": 7.5,
                    "algo_boost": f"{angle_info['count']}개 영상 동시 상승 중",
                })
    
    # 점수 순 정렬, 중복 제거
    seen = set()
    final = []
    for r in sorted(recommendations, key=lambda x: x["score"], reverse=True):
        if r["topic"] not in seen:
            seen.add(r["topic"])
            final.append(r)
    
    return final[:10]


def save_realtime_analysis(analysis, recommendations):
    """실시간 분석 결과 저장"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    result = {
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "analysis": analysis,
        "recommendations": recommendations,
    }
    
    with open(DATA_DIR / "realtime_latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return result


# 테스트용 entrypoint
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # 파일에서 읽기
        with open(sys.argv[1], encoding="utf-8") as f:
            text = f.read()
    else:
        # stdin에서 읽기
        text = sys.stdin.read()
    
    videos = parse_realtime_text(text)
    print(f"파싱된 영상 수: {len(videos)}")
    
    analysis = analyze_algorithm_signals(videos)
    
    print(f"\n🔥 60분 조회수 TOP 5:")
    for v in analysis.get("top_by_60m", [])[:5]:
        print(f"  {v['views_60m']:,}회 | {v['title'][:50]}")
    
    print(f"\n📊 알고리즘이 밀어주는 앵글 TOP 3:")
    for a in analysis.get("top_angles", [])[:3]:
        print(f"  [{a['angle']}] {a['count']}개 영상 / 평균 60분 {int(a['avg_views_60m']):,}회")
    
    # 네이버 데이터와 교차
    latest_naver = DATA_DIR / "latest.json"
    naver_topics = []
    if latest_naver.exists():
        with open(latest_naver, encoding="utf-8") as f:
            naver_data = json.load(f)
            naver_topics = naver_data.get("topics", [])
    
    recs = generate_recommendations(analysis, naver_topics)
    
    print(f"\n💡 교차 추천 주제:")
    for r in recs:
        print(f"  [{r['type']}][{r['angle']}] {r['topic']}")
        print(f"     {r['reason']}")
    
    save_realtime_analysis(analysis, recs)
    print(f"\n✅ 저장 완료: docs/data/realtime_latest.json")
