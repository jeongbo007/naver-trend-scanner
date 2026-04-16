/* ================================
   🦛 정보주는 하마 트렌드 스캐너
   app.js
   ================================ */

// 전역 상태
let STATE = {
  scheduled: null,     // 정기 스캔 데이터
  realtime: null,      // 실시간 분석 결과
  filters: {
    minScore: 6.0,
    angle: "",
    hideDups: true,
  },
};

// ===== 초기화 =====
document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupFilters();
  await loadScheduledData();
  await loadHistory();
});

// ===== 탭 전환 =====
function setupTabs() {
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${target}`).classList.add("active");
    });
  });
}

// ===== 필터 =====
function setupFilters() {
  const minScoreInput = document.getElementById("minScore");
  const minScoreLabel = document.getElementById("minScoreLabel");
  const angleFilter = document.getElementById("angleFilter");
  const hideDups = document.getElementById("hideDups");
  
  minScoreInput.addEventListener("input", () => {
    STATE.filters.minScore = parseFloat(minScoreInput.value);
    minScoreLabel.textContent = minScoreInput.value;
    renderTopics();
  });
  
  angleFilter.addEventListener("change", () => {
    STATE.filters.angle = angleFilter.value;
    renderTopics();
  });
  
  hideDups.addEventListener("change", () => {
    STATE.filters.hideDups = hideDups.checked;
    renderTopics();
  });
}

// ===== 정기 스캔 데이터 로드 =====
async function loadScheduledData() {
  try {
    const res = await fetch("data/latest.json?t=" + Date.now());
    if (!res.ok) throw new Error("no scan data yet");
    const data = await res.json();
    STATE.scheduled = data;
    
    // 헤더 업데이트
    document.getElementById("lastScanTime").textContent = 
      "마지막 스캔: " + data.scan_time;
    document.getElementById("stat-articles").textContent = data.total_articles || 0;
    document.getElementById("stat-topics").textContent = data.total_topics_generated || 0;
    document.getElementById("stat-dups").textContent = data.excluded_duplicates || 0;
    document.getElementById("stat-final").textContent = (data.topics || []).length;
    
    // 앵글 필터 옵션 채우기
    const angles = new Set();
    (data.all_topics || data.topics || []).forEach(t => {
      if (t.angle_type) angles.add(t.angle_type);
    });
    const angleSelect = document.getElementById("angleFilter");
    angleSelect.innerHTML = '<option value="">전체</option>' + 
      [...angles].sort().map(a => `<option value="${a}">${a}</option>`).join("");
    
    renderTopics();
  } catch (e) {
    document.getElementById("lastScanTime").textContent = "스캔 데이터 없음";
    document.getElementById("topicsList").innerHTML = 
      '<div class="empty-state">⏳ 아직 스캔 결과가 없습니다.<br>GitHub Actions가 처음 실행되기를 기다려주세요 (매일 05/09/14/18/23시).</div>';
  }
}

// ===== 주제 리스트 렌더링 =====
function renderTopics() {
  if (!STATE.scheduled) return;
  
  const all = STATE.scheduled.all_topics || STATE.scheduled.topics || [];
  const filtered = all.filter(t => {
    if (t.score < STATE.filters.minScore) return false;
    if (STATE.filters.angle && t.angle_type !== STATE.filters.angle) return false;
    if (STATE.filters.hideDups && t.dup_check && t.dup_check.is_duplicate) return false;
    return true;
  });
  
  const list = document.getElementById("topicsList");
  if (filtered.length === 0) {
    list.innerHTML = '<div class="empty-state">조건에 맞는 주제가 없습니다. 필터를 조정해보세요.</div>';
    return;
  }
  
  list.innerHTML = filtered.map((t, i) => renderTopicCard(t, i)).join("");
}

// ===== 토픽 카드 HTML =====
function renderTopicCard(topic, idx, isCross = false) {
  const score = topic.score || 0;
  const scoreClass = score >= 8 ? "high" : score >= 6.5 ? "medium" : "";
  const cardClass = isCross ? "cross-match" : (score >= 8 ? "high-score" : score >= 6.5 ? "medium-score" : "");
  
  const dup = topic.dup_check || {};
  let dupTag = '<span class="tag dup-pass">✅ 통과</span>';
  if (dup.status === "재활용 가능") {
    dupTag = `<span class="tag dup-reuse">♻️ 재활용 가능 (${dup.reason || '기간·조회수 조건 충족'})</span>`;
  } else if (dup.is_duplicate) {
    dupTag = `<span class="tag dup-excluded">❌ 중복</span>`;
  }
  
  const matchedInfo = dup.matched_title ? 
    `<div class="topic-meta">📎 유사 영상: <strong>${escape(dup.matched_title)}</strong> (${(dup.matched_views || 0).toLocaleString()}회)</div>` : "";
  
  const crossInfo = isCross && topic.cross_reason ? 
    `<div class="topic-meta" style="background:rgba(239,68,68,0.05); padding:8px 12px; border-radius:6px; color:#991b1b; margin-bottom:10px;">🎯 ${escape(topic.cross_reason)}</div>` : "";
  
  const algoBoost = topic.algo_boost ? 
    `<div class="topic-meta" style="color:#7c3aed;">⚡ ${escape(topic.algo_boost)}</div>` : "";
  
  const sourceInfo = topic.source_article ? 
    `<div class="topic-meta">📰 원본 기사: ${escape(topic.source_article)} <span style="color:#aaa">(${escape(topic.source_name || '')})</span></div>` : "";
  
  // 표 미리보기 HTML
  const table = topic.table || {};
  const tableHtml = table.headers ? renderTablePreview(table.headers) : "";
  
  const topicId = `topic-${idx}-${Date.now()}`;
  
  return `
    <div class="topic-card ${cardClass}" id="${topicId}">
      <div class="topic-header">
        <div class="topic-title">${escape(topic.title || topic.topic || "(제목 없음)")}</div>
        <div class="score-badge ${scoreClass}">${score.toFixed(1)}</div>
      </div>
      
      <div class="tags-row">
        ${isCross ? '<span class="tag cross">🎯 교차 추천</span>' : ''}
        <span class="tag angle">📐 ${escape(topic.angle_type || topic.angle || '-')}</span>
        ${dupTag}
      </div>
      
      ${crossInfo}
      ${algoBoost}
      ${sourceInfo}
      ${matchedInfo}
      
      ${tableHtml ? `<div class="table-preview">${tableHtml}</div>` : ""}
      
      <div class="btn-row">
        <button class="btn-copy" onclick="copyTable('${topicId}')">📋 표 복사 (캔바용)</button>
        <button class="btn-copy title-copy" onclick="copyText('${escape(topic.title || topic.topic)}')">📝 제목만 복사</button>
      </div>
    </div>
  `;
}

// ===== 표 미리보기 HTML 생성 =====
function renderTablePreview(headers) {
  let html = "<table><thead><tr>";
  headers.forEach(h => html += `<th>${escape(h)}</th>`);
  html += "</tr></thead><tbody>";
  for (let i = 1; i <= 10; i++) {
    html += "<tr>";
    html += `<td>${i}위</td>`;
    for (let j = 1; j < headers.length; j++) {
      html += "<td></td>";
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  return html;
}

// ===== 클립보드 복사 =====
function copyTable(topicId) {
  const card = document.getElementById(topicId);
  if (!card) return;
  
  // 표 데이터 찾기
  const table = card.querySelector("table");
  if (!table) { showToast("복사할 표가 없습니다"); return; }
  
  // TSV 형식으로 변환
  const rows = [];
  table.querySelectorAll("tr").forEach(tr => {
    const cells = [];
    tr.querySelectorAll("th, td").forEach(cell => {
      cells.push(cell.textContent || "");
    });
    rows.push(cells.join("\t"));
  });
  const tsv = rows.join("\n");
  
  copyToClipboard(tsv, "📋 표가 복사되었습니다! 캔바에 붙여넣으세요");
}

function copyText(text) {
  copyToClipboard(text, "📝 제목이 복사되었습니다");
}

function copyToClipboard(text, successMsg) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(
      () => showToast(successMsg),
      () => fallbackCopy(text, successMsg)
    );
  } else {
    fallbackCopy(text, successMsg);
  }
}

function fallbackCopy(text, successMsg) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    document.execCommand("copy");
    showToast(successMsg);
  } catch (e) {
    showToast("❌ 복사 실패");
  }
  document.body.removeChild(textarea);
}

function showToast(msg) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2400);
}

// ===== 실시간 분석 =====
function clearRealtime() {
  document.getElementById("realtimeInput").value = "";
  document.getElementById("realtimeResult").innerHTML = "";
  STATE.realtime = null;
  renderCrossRecommendations();
}

function showRealtimeSample() {
  const sample = `"지예은♥바타 열애 인정?" 역대 댄서 연애·결혼 이슈 TOP 10 #연예인 #연예계소식
2026. 4. 13.
388,183
8,070

"최충연부터 이종범까지?" 팬들 분통 터진 야구 논란 TOP10 #야구 #스포
2026. 4. 14.
186,169
6,383

"122억에 산 빌딩이 236억?" 나혼산 출연진 시세차익 TOP 10 #연예인 #연예계소식
2026. 4. 14.
420,549
4,589`;
  document.getElementById("realtimeInput").value = sample;
  showToast("샘플이 입력되었습니다. 분석하기 버튼을 눌러보세요.");
}

async function analyzeRealtime() {
  const text = document.getElementById("realtimeInput").value.trim();
  if (!text) {
    showToast("데이터를 먼저 붙여넣어주세요");
    return;
  }
  
  // 클라이언트 사이드 파싱 (GitHub Pages는 서버 실행 불가)
  const videos = parseRealtimeText(text);
  if (videos.length === 0) {
    document.getElementById("realtimeResult").innerHTML = 
      '<div class="empty-state">데이터 파싱에 실패했습니다. 형식을 확인해주세요.</div>';
    return;
  }
  
  const analysis = analyzeAlgorithmSignals(videos);
  STATE.realtime = analysis;
  
  renderRealtimeResult(analysis);
  renderCrossRecommendations();
  showToast(`✅ ${videos.length}개 영상 분석 완료`);
}

function parseRealtimeText(text) {
  const lines = text.split("\n").map(l => l.trim()).filter(l => l);
  const videos = [];
  let i = 0;
  
  while (i < lines.length) {
    if (lines[i].length < 15) { i++; continue; }
    
    const title = lines[i];
    
    // 다음 줄이 날짜?
    if (i + 1 >= lines.length) break;
    const dateMatch = lines[i+1].match(/(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})/);
    if (!dateMatch) { i++; continue; }
    
    let v48 = 0, v60 = 0;
    if (i + 2 < lines.length) {
      const num = lines[i+2].replace(/[^\d]/g, "");
      if (num) v48 = parseInt(num);
    }
    if (i + 3 < lines.length) {
      const num = lines[i+3].replace(/[^\d]/g, "");
      if (num) v60 = parseInt(num);
    }
    
    if (v48 > 0) {
      videos.push({
        title, date: dateMatch[0],
        views_48h: v48, views_60m: v60,
      });
      i += 4;
    } else {
      i++;
    }
  }
  
  return videos;
}

function analyzeAlgorithmSignals(videos) {
  if (!videos.length) return null;
  
  videos.forEach(v => {
    const avgPerHour = v.views_48h / 48;
    v.surge_ratio = avgPerHour > 0 ? v.views_60m / avgPerHour : 0;
    v.surge_score = v.views_60m * Math.min(v.surge_ratio, 3);
  });
  
  const by60m = [...videos].sort((a,b) => b.views_60m - a.views_60m).slice(0, 10);
  const bySurge = [...videos].sort((a,b) => b.surge_score - a.surge_score).slice(0, 10);
  
  const angleKeywords = {
    "몸값·반전": ["몸값", "반전", "회당", "연봉"],
    "자산·금액": ["자산", "매출", "재산", "억", "빚", "빌딩", "부동산"],
    "논란·폭로": ["논란", "폭로", "고발", "적발", "사기"],
    "이혼·결혼": ["이혼", "결혼", "열애", "재혼"],
    "동갑·나이": ["동갑", "살", "세", "년생"],
    "가족·혈연": ["가족", "혈연", "아빠", "엄마"],
    "복귀·근황": ["근황", "복귀", "컴백", "공백"],
    "프로그램·드라마": ["출연진", "드라마", "예능", "1박", "미우새", "나혼산"],
    "스포츠": ["KBO", "야구", "축구", "선수", "골프", "FA", "홈런"],
  };
  
  const angleSignals = {};
  Object.entries(angleKeywords).forEach(([angle, kws]) => {
    const hits = by60m.filter(v => kws.some(k => v.title.includes(k)));
    if (hits.length > 0) {
      angleSignals[angle] = {
        count: hits.length,
        total_views_60m: hits.reduce((s,h) => s + h.views_60m, 0),
        avg_views_60m: hits.reduce((s,h) => s + h.views_60m, 0) / hits.length,
        videos: hits.map(h => ({title: h.title, views_60m: h.views_60m})),
      };
    }
  });
  
  const topAngles = Object.entries(angleSignals)
    .map(([angle, info]) => ({angle, ...info}))
    .sort((a,b) => b.avg_views_60m - a.avg_views_60m)
    .slice(0, 5);
  
  return {
    total_videos: videos.length,
    total_views_60m: videos.reduce((s,v) => s + v.views_60m, 0),
    total_views_48h: videos.reduce((s,v) => s + v.views_48h, 0),
    top_by_60m: by60m,
    top_by_surge: bySurge,
    top_angles: topAngles,
  };
}

function renderRealtimeResult(analysis) {
  const container = document.getElementById("realtimeResult");
  
  const topAnglesHtml = analysis.top_angles.map((a, idx) => `
    <div class="angle-item">
      <div>
        <div class="angle-item-name">${idx+1}. ${escape(a.angle)}</div>
        <div class="angle-item-stats">${a.count}개 영상 · 60분 평균 ${Math.floor(a.avg_views_60m).toLocaleString()}회</div>
      </div>
      <div style="font-size:20px; font-weight:800; color:#b45309;">
        ${a.count >= 3 ? "🔥" : a.count >= 2 ? "⚡" : "✨"}
      </div>
    </div>
  `).join("");
  
  const topVideosHtml = analysis.top_by_60m.slice(0, 5).map((v, idx) => `
    <div style="padding:10px 0; border-bottom:1px solid #eee; font-size:13px;">
      <div style="font-weight:600;">${idx+1}. ${escape(v.title)}</div>
      <div style="font-size:12px; color:#888; margin-top:3px;">
        48h: ${v.views_48h.toLocaleString()}회 / <strong style="color:#d97706;">60분: ${v.views_60m.toLocaleString()}회</strong>
        ${v.surge_ratio > 1.5 ? ` · 🚀 급상승 ${v.surge_ratio.toFixed(1)}x` : ""}
      </div>
    </div>
  `).join("");
  
  container.innerHTML = `
    <div class="realtime-summary">
      <h3>⚡ 지금 알고리즘이 밀어주는 앵글</h3>
      <div class="angle-list">${topAnglesHtml}</div>
    </div>
    
    <div style="background:white; border:1px solid var(--border); border-radius:12px; padding:18px 20px; margin-bottom:20px;">
      <h3 style="margin-bottom:10px; font-size:15px;">🔥 60분 조회수 TOP 5</h3>
      ${topVideosHtml}
    </div>
    
    <div style="color:var(--text-secondary); font-size:13px; text-align:center; padding:10px;">
      💡 <strong>교차 추천</strong> 탭으로 이동하면 네이버 트렌드와 조합된 추천 주제를 볼 수 있습니다
    </div>
  `;
}

// ===== 교차 추천 =====
function renderCrossRecommendations() {
  const container = document.getElementById("crossRecommendations");
  
  if (!STATE.realtime) {
    container.innerHTML = '<div class="empty-state">📊 실시간 채널 데이터를 입력하면 교차 추천이 활성화됩니다.<br><br>⚡ 실시간 채널 분석 탭으로 이동하세요.</div>';
    return;
  }
  
  if (!STATE.scheduled) {
    container.innerHTML = '<div class="empty-state">⏳ 정기 스캔 데이터가 아직 없습니다.</div>';
    return;
  }
  
  const topics = STATE.scheduled.all_topics || STATE.scheduled.topics || [];
  const topAngles = STATE.realtime.top_angles || [];
  
  const angleKeywords = {
    "몸값·반전": ["몸값", "반전", "회당", "연봉"],
    "자산·금액": ["자산", "매출", "재산", "억", "빚"],
    "논란·폭로": ["논란", "폭로", "사기"],
    "이혼·결혼": ["이혼", "결혼", "열애"],
    "동갑·나이": ["동갑", "나이", "세"],
    "가족·혈연": ["가족", "혈연"],
    "복귀·근황": ["근황", "복귀", "공백"],
    "스포츠": ["KBO", "야구", "축구"],
  };
  
  // 교차 매칭
  const crossMatches = [];
  topics.forEach(topic => {
    if (topic.dup_check && topic.dup_check.is_duplicate) return;
    
    const topicText = (topic.title || "") + " " + (topic.source_article || "");
    
    topAngles.slice(0, 3).forEach(angleInfo => {
      const kws = angleKeywords[angleInfo.angle] || [];
      if (kws.some(k => topicText.includes(k))) {
        crossMatches.push({
          ...topic,
          cross_reason: `네이버 기사 노출 + 내 채널 '${angleInfo.angle}' 앵글 알고리즘 호조`,
          algo_boost: `'${angleInfo.angle}' 앵글 영상 ${angleInfo.count}개가 동시 상승 중 (60분 평균 ${Math.floor(angleInfo.avg_views_60m).toLocaleString()}회)`,
          score: (topic.score || 5) + 2,  // 교차 보너스
        });
      }
    });
  });
  
  // 중복 제거
  const seen = new Set();
  const unique = crossMatches.filter(t => {
    if (seen.has(t.title)) return false;
    seen.add(t.title);
    return true;
  });
  
  unique.sort((a,b) => b.score - a.score);
  
  if (unique.length === 0) {
    container.innerHTML = '<div class="empty-state">🔍 지금 네이버 트렌드와 내 채널 알고리즘이 겹치는 주제가 없습니다.<br>잠시 후 다시 시도해보세요.</div>';
    return;
  }
  
  container.innerHTML = `
    <div style="margin-bottom:20px; padding:14px 18px; background:linear-gradient(135deg, rgba(239,68,68,0.05), rgba(245,158,11,0.03)); border-radius:10px; border-left:4px solid var(--danger);">
      <strong>🎯 ${unique.length}개의 교차 추천 주제</strong>
      <div style="font-size:13px; color:var(--text-secondary); margin-top:6px;">
        네이버에서 지금 뜨는 기사 + 내 채널 알고리즘이 지금 밀어주는 앵글 = 즉시 제작 추천
      </div>
    </div>
    ${unique.slice(0, 15).map((t, i) => renderTopicCard(t, i, true)).join("")}
  `;
}

// ===== 히스토리 =====
async function loadHistory() {
  try {
    const res = await fetch("data/scan_log.json?t=" + Date.now());
    if (!res.ok) throw new Error("no log");
    const logs = await res.json();
    
    document.getElementById("historyList").innerHTML = `
      <div style="background:white; border:1px solid var(--border); border-radius:12px; overflow:hidden;">
        ${logs.map(log => `
          <div style="padding:14px 18px; border-bottom:1px solid #eee; display:flex; justify-content:space-between; align-items:center; gap:16px;">
            <div>
              <div style="font-weight:600; font-size:14px;">${escape(log.time)}</div>
              <div style="font-size:12px; color:var(--text-secondary); margin-top:3px;">
                기사 ${log.articles}개 수집 / 추천 주제 ${log.topics}개
              </div>
            </div>
            <a href="data/${escape(log.file)}" target="_blank" style="color:var(--primary); font-size:13px; font-weight:600; text-decoration:none;">JSON 보기 →</a>
          </div>
        `).join("")}
      </div>
    `;
  } catch (e) {
    document.getElementById("historyList").innerHTML = '<div class="empty-state">히스토리가 없습니다.</div>';
  }
}

// ===== 유틸 =====
function escape(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
