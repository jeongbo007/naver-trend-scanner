# 🦛 정보주는 하마 · 네이버 트렌드 스캐너

> 네이버 엔터/스포츠 랭킹을 하루 5회 자동 크롤링해서 TOP10 콘텐츠 주제를 자동 추천하는 시스템

---

## 📌 주요 기능

### 1. 🕐 정기 자동 스캔 (GitHub Actions)
- **하루 5회 자동 실행**: 05시 / 09시 / 14시 / 18시 / 23시 (KST)
- **수집 대상**:
  - 네이버 엔터 랭킹 (많이 본 뉴스)
  - 네이버 엔터 랭킹 (5분 많이 본)
  - 네이버 스포츠 메인
- **파생 주제 자동 생성**: 각 기사에서 3~5개 TOP10 주제 자동 도출
- **중복 체크**: 455개 기존 영상과 비교 (4개월 경과 OR 조회수 8만 미만이면 재활용 허용)

### 2. ⚡ 실시간 채널 분석
- YouTube Studio의 **"실시간 업데이트 중"** 데이터를 붙여넣기만 하면
- 현재 알고리즘이 밀어주는 앵글을 자동 분석
- 60분 조회수 급상승 영상 감지

### 3. 🎯 교차 추천 (핵심!)
- **네이버 트렌드 × 내 채널 알고리즘 신호**를 조합
- "지금 네이버에 핫한 기사 + 내 채널에서도 지금 뜨는 앵글" = 즉시 제작 추천

### 4. 📋 원클릭 표 복사 (캔바용)
- 각 주제마다 **"표 복사" 버튼**
- 탭 구분(TSV) 형식으로 클립보드에 복사 → 캔바에 붙여넣으면 자동으로 표 생성

### 5. 🎯 30~50대 남성 타겟 가중치
- 주제 추천 시 타겟층 친화도 점수 자동 반영
- 돈/스포츠/논란/반전 등 남성 관심 앵글 우선 추천

---

## 🚀 설치 및 실행 방법

### 1단계: GitHub 저장소 생성

1. [GitHub](https://github.com/)에 새 계정으로 로그인
2. 우상단 `+` → `New repository` 클릭
3. 저장소 이름: `naver-trend-scanner` (원하는 이름)
4. **Public** 선택 (GitHub Pages 무료 사용하려면)
5. `Create repository` 클릭

### 2단계: 파일 업로드

1. 제공된 ZIP 파일을 압축 해제
2. 생성한 저장소 페이지에서 `uploading an existing file` 클릭
3. 모든 파일을 드래그 앤 드롭 (⚠️ `.github` 폴더 포함 필수)
4. `Commit changes` 클릭

**주의**: 웹 UI로 업로드할 때 `.github/workflows/auto_scan.yml` 파일은 보안상 자동 무시될 수 있습니다. 이 경우 저장소에 직접 들어가서 `Add file → Create new file`로 `.github/workflows/auto_scan.yml` 경로를 직접 입력한 후 내용을 붙여넣어주세요.

### 3단계: GitHub Pages 활성화

1. 저장소 → `Settings` 탭
2. 왼쪽 메뉴 `Pages`
3. **Source**: `Deploy from a branch` 선택
4. **Branch**: `main` / **Folder**: `/docs`
5. `Save` 클릭

몇 분 뒤 대시보드 주소가 생성됩니다:
```
https://[GitHub계정명].github.io/naver-trend-scanner/
```

**이 주소를 북마크**해두세요! 이게 메인 대시보드입니다.

### 4단계: 첫 스캔 수동 실행

GitHub Actions는 스케줄에 따라 자동 실행되지만, 첫 실행은 수동으로 해야 합니다.

1. 저장소 → `Actions` 탭
2. 좌측에서 `Naver Trend Scanner` 선택
3. `Run workflow` 버튼 → `Run workflow` 클릭
4. 1~2분 후 완료

### 5단계: 대시보드 접속

`https://[계정명].github.io/naver-trend-scanner/` 열면 끝!

---

## 📊 사용 방법

### 💡 하루 루틴 예시

**아침 (09시 스캔 후):**
1. 대시보드 열기 (북마크 클릭)
2. **🕐 정기 스캔 결과** 탭에서 TOP 주제 확인
3. 점수 8.0 이상 주제 중 마음에 드는 것 **표 복사** → 캔바에 붙여넣기
4. 표 채워서 영상 제작

**YouTube Studio 열었을 때:**
1. "실시간 업데이트 중" 영역 복사 (제목/날짜/48h/60분 조회수 4줄씩)
2. 대시보드 **⚡ 실시간 채널 분석** 탭에 붙여넣기
3. **🔍 분석하기** 클릭
4. **🎯 교차 추천** 탭 확인 → 지금 제작하면 터질 확률 높은 주제 발견

---

## 🛠️ 유지보수

### 새 영상 올린 뒤 히스토리 업데이트

`channel_history.csv` 파일에 새 줄 추가:
```csv
title,views,published
새 영상 제목,0,"Apr 17, 2026"
```

조회수는 나중에 업데이트해도 되고, 일정 조회수 이상 영상만 중복 체크에 사용되니 초기에는 0이어도 괜찮습니다.

### 스캔 시각 변경

`.github/workflows/auto_scan.yml` 파일의 `cron` 부분 수정:
- `'0 20 * * *'` = UTC 20:00 = **KST 05:00**
- UTC에 9시간 더하면 KST

### 파생 주제 로직 변경

`scanner.py`의 `TopicGenerator.generate()` 메서드 수정.

### 타겟 키워드 조정

`scanner.py`의 `MALE_TARGET_KEYWORDS` 딕셔너리에서 추가/삭제.

---

## 🐞 트러블슈팅

### GitHub Actions가 실패해요
- **Actions 탭**에서 실패한 실행 클릭 → 오류 로그 확인
- 대부분의 경우: 네이버 페이지 구조 변경 → `scanner.py`의 CSS 셀렉터 수정 필요

### 대시보드에 데이터가 안 보여요
- `docs/data/latest.json`이 있는지 확인 (없으면 아직 첫 스캔 안 된 상태)
- 브라우저 하드 리프레시: `Ctrl+Shift+R`

### 복사 버튼이 동작 안 해요
- HTTPS(`github.io`)에서만 동작함 (클립보드 API 제약)
- 로컬에서 열면 Fallback 방식으로 동작

---

## 📁 파일 구조

```
naver-trend-scanner/
├── scanner.py                ← 메인 스캐너
├── realtime_analyzer.py      ← 실시간 분석 (로컬 테스트용)
├── channel_history.csv       ← 455개 기존 영상 (중복 체크용)
├── requirements.txt          ← Python 패키지
├── README.md                 ← 이 파일
│
├── .github/workflows/
│   └── auto_scan.yml         ← 자동 스케줄러
│
└── docs/                     ← GitHub Pages 공개 폴더
    ├── index.html            ← 대시보드
    ├── assets/
    │   ├── style.css
    │   └── app.js
    └── data/
        ├── latest.json       ← 최신 스캔 결과
        ├── scan_log.json     ← 스캔 이력
        └── scan_*.json       ← 각 스캔별 아카이브
```

---

## 💬 문의

코드 수정이나 기능 추가가 필요하면 Claude에게 요청하세요!
