/* ================================
   🦛 정보주는 하마 트렌드 스캐너 v3.0
   - Gemini API 연동 (표 자동 완성)
   - 원본 기사 링크 클릭
   - 키워드/인물 빈도 분석
   ================================ */

let STATE = { scheduled: null, realtime: null, geminiKey: "", filters: { minScore: 6.0, angle: "", hideDups: true } };

// ===== 초기화 =====
document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupFilters();
  loadGeminiKey();
  await loadScheduledData();
  await loadHistory();
});

// ===== Gemini API 키 관리 =====
function loadGeminiKey() {
  STATE.geminiKey = localStorage.getItem("gemini_api_key") || "";
  const input = document.getElementById("geminiKeyInput");
  if (input && STATE.geminiKey) input.value = STATE.geminiKey;
}

function saveGeminiKey() {
  const input = document.getElementById("geminiKeyInput");
  if (!input) return;
  STATE.geminiKey = input.value.trim();
  localStorage.setItem("gemini_api_key", STATE.geminiKey);
  showToast(STATE.geminiKey ? "✅ API 키 저장 완료" : "API 키 삭제됨");
}

function toggleKeyVisibility() {
  const input = document.getElementById("geminiKeyInput");
  if (!input) return;
  input.type = input.type === "password" ? "text" : "password";
}

// ===== 탭 전환 =====
function setupTabs() {
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

// ===== 필터 =====
function setupFilters() {
  const ms = document.getElementById("minScore"), ml = document.getElementById("minScoreLabel");
  const af = document.getElementById("angleFilter"), hd = document.getElementById("hideDups");
  if (ms) ms.addEventListener("input", () => { STATE.filters.minScore = parseFloat(ms.value); ml.textContent = ms.value; renderTopics(); });
  if (af) af.addEventListener("change", () => { STATE.filters.angle = af.value; renderTopics(); });
  if (hd) hd.addEventListener("change", () => { STATE.filters.hideDups = hd.checked; renderTopics(); });
}

// ===== 정기 스캔 데이터 로드 =====
async function loadScheduledData() {
  try {
    const res = await fetch("data/latest.json?t=" + Date.now());
    if (!res.ok) throw new Error("no data");
    const data = await res.json();
    STATE.scheduled = data;

    document.getElementById("lastScanTime").textContent = "마지막 스캔: " + data.scan_time;
    document.getElementById("stat-articles").textContent = data.total_articles || 0;
    document.getElementById("stat-topics").textContent = data.total_topics_generated || 0;
    document.getElementById("stat-dups").textContent = data.excluded_duplicates || 0;
    document.getElementById("stat-final").textContent = (data.topics || []).length;

    const angles = new Set();
    (data.all_topics || data.topics || []).forEach(t => { if (t.angle_type) angles.add(t.angle_type); });
    const sel = document.getElementById("angleFilter");
    if (sel) sel.innerHTML = '<option value="">전체</option>' + [...angles].sort().map(a => `<option value="${a}">${a}</option>`).join("");

    renderTopics();
    renderKeywordAnalysis();
  } catch (e) {
    document.getElementById("lastScanTime").textContent = "스캔 데이터 없음";
    document.getElementById("topicsList").innerHTML = '<div class="empty-state">⏳ 아직 스캔 결과가 없습니다.</div>';
  }
}

// ===== 키워드/인물 빈도 분석 =====
function renderKeywordAnalysis() {
  if (!STATE.scheduled) return;
  const container = document.getElementById("keywordAnalysis");
  if (!container) return;

  const articles = STATE.scheduled.articles || [];
  const stopwords = new Set(["기자","뉴스","속보","단독","한국","대한","정부","국민","사회","경제","정치","서울","대구","부산","오늘","내일","어제","올해","지난","이번","해당","관련","전했","밝혔","보도","발표"]);

  // 키워드 빈도
  const kwCount = {};
  const nameCount = {};

  articles.forEach(a => {
    const title = (a.title || "").replace(/#\S+/g, "");
    const words = title.match(/[가-힣]{2,}/g) || [];
    words.forEach(w => {
      if (stopwords.has(w) || w.length < 2) return;
      kwCount[w] = (kwCount[w] || 0) + 1;
    });

    // 2~3글자 이름 패턴 (이름은 보통 2~3글자)
    const names = title.match(/[가-힣]{2,3}/g) || [];
    names.forEach(n => {
      if (stopwords.has(n) || n.length < 2) return;
      // 간단한 필터: 조사/동사 어미 제거
      if (["에서","으로","까지","부터","에게","한테","했다","됐다","있다","없다","된다","한다"].includes(n)) return;
      nameCount[n] = (nameCount[n] || 0) + 1;
    });
  });

  const topKw = Object.entries(kwCount).sort((a,b) => b[1]-a[1]).slice(0, 20);
  const topNames = Object.entries(nameCount).filter(([n,c]) => c >= 2).sort((a,b) => b[1]-a[1]).slice(0, 15);

  container.innerHTML = `
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px;">
      <div style="background:white; border:1px solid var(--border); border-radius:12px; padding:16px;">
        <h3 style="font-size:14px; margin-bottom:12px;">🔥 반복 키워드 TOP 20</h3>
        ${topKw.map(([w,c], i) => `
          <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid #f3f4f6; font-size:13px;">
            <span>${i+1}. ${esc(w)}</span>
            <span style="font-weight:700; color:var(--primary);">${c}회</span>
          </div>
        `).join("")}
      </div>
      <div style="background:white; border:1px solid var(--border); border-radius:12px; padding:16px;">
        <h3 style="font-size:14px; margin-bottom:12px;">👤 반복 등장 인물/키워드 (2회+)</h3>
        ${topNames.length ? topNames.map(([n,c], i) => `
          <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid #f3f4f6; font-size:13px;">
            <span>${i+1}. ${esc(n)}</span>
            <span style="font-weight:700; color:#d97706;">${c}회</span>
          </div>
        `).join("") : '<div style="color:#999; font-size:13px;">2회 이상 등장 키워드 없음</div>'}
      </div>
    </div>
  `;
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
  if (!filtered.length) { list.innerHTML = '<div class="empty-state">조건에 맞는 주제가 없습니다.</div>'; return; }
  list.innerHTML = filtered.map((t, i) => renderTopicCard(t, i)).join("");
}

// ===== 토픽 카드 =====
function renderTopicCard(topic, idx, isCross = false) {
  const score = topic.score || 0;
  const scoreClass = score >= 8 ? "high" : score >= 6.5 ? "medium" : "";
  const cardClass = isCross ? "cross-match" : (score >= 8 ? "high-score" : score >= 6.5 ? "medium-score" : "");

  const dup = topic.dup_check || {};
  let dupTag = '<span class="tag dup-pass">✅ 통과</span>';
  if (dup.status === "재활용 가능") dupTag = `<span class="tag dup-reuse">♻️ 재활용 (${esc(dup.reason||'')})</span>`;
  else if (dup.is_duplicate) dupTag = '<span class="tag dup-excluded">❌ 중복</span>';

  const matchInfo = dup.matched_title ? `<div class="topic-meta">📎 유사: <strong>${esc(dup.matched_title)}</strong> (${(dup.matched_views||0).toLocaleString()}회)</div>` : "";

  // 원본 기사 링크 (클릭 가능)
  const articleUrl = topic.source_url || topic.url || "";
  const sourceInfo = topic.source_article ? `<div class="topic-meta">📰 원본: ${articleUrl ? `<a href="${esc(articleUrl)}" target="_blank" style="color:var(--primary); text-decoration:underline;">${esc(topic.source_article)}</a>` : esc(topic.source_article)} <span style="color:#aaa">(${esc(topic.source_name||'')})</span></div>` : "";

  const topicId = `topic-${idx}-${Date.now()}`;
  const table = topic.table || {};
  const tableHtml = table.headers ? renderTablePreview(table.headers, topic._filled_data) : "";

  return `
    <div class="topic-card ${cardClass}" id="${topicId}">
      <div class="topic-header">
        <div class="topic-title">${esc(topic.title || "(제목 없음)")}</div>
        <div class="score-badge ${scoreClass}">${score.toFixed(1)}</div>
      </div>
      <div class="tags-row">
        <span class="tag angle">📐 ${esc(topic.angle_type || '-')}</span>
        ${dupTag}
      </div>
      ${sourceInfo}
      ${matchInfo}
      <div class="table-preview" id="table-${topicId}" style="display:none;"></div>
      <div class="btn-row">
        <button class="btn-copy gemini-btn" onclick="fillTableWithGemini('${topicId}', '${esc(topic.title||'')}', '${esc((topic.table||{}).headers?.join(',')||'')}')">🤖 표 채우기 (Gemini)</button>
        <button class="btn-copy" onclick="copyTable('${topicId}')">📋 표 복사 (캔바용)</button>
        <button class="btn-copy title-copy" onclick="copyText('${esc(topic.title||'')}')">📝 제목 복사</button>
      </div>
    </div>
  `;
}

function renderTablePreview(headers, filledData = null) {
  let html = "<table><thead><tr>";
  headers.forEach(h => html += `<th>${esc(h)}</th>`);
  html += "</tr></thead><tbody>";

  if (filledData && filledData.top10) {
    filledData.top10.forEach((row, i) => {
      html += "<tr>";
      html += `<td>${i + 1}</td>`;
      for (let j = 1; j < headers.length; j++) {
        html += `<td>${esc(row[j] || "")}</td>`;
      }
      html += "</tr>";
    });
  } else {
    for (let i = 1; i <= 10; i++) {
      html += "<tr>";
      html += `<td>${i}</td>`;
      for (let j = 1; j < headers.length; j++) html += "<td></td>";
      html += "</tr>";
    }
  }
  html += "</tbody></table>";

  // 후보 5명 (채워진 경우)
  if (filledData && filledData.candidates && filledData.candidates.length) {
    html += `<div style="margin-top:14px; padding-top:12px; border-top:2px dashed #e5e7eb;">
      <div style="font-weight:700; font-size:13px; margin-bottom:8px; color:#d97706;">🎯 후보 5명 (대체 가능)</div>
      <table><thead><tr>`;
    headers.forEach(h => html += `<th>${esc(h)}</th>`);
    html += `<th>후보 사유</th></tr></thead><tbody>`;
    filledData.candidates.forEach((row, i) => {
      html += "<tr>";
      html += `<td style="color:#d97706; font-weight:600;">후보${i+1}</td>`;
      for (let j = 1; j < headers.length; j++) html += `<td>${esc(row[j] || "")}</td>`;
      html += `<td style="font-size:11px; color:#888;">${esc(row.reason || "")}</td>`;
      html += "</tr>";
    });
    html += "</tbody></table></div>";
  }

  return html;
}

// ===== Gemini API로 표 채우기 =====
async function fillTableWithGemini(topicId, topicTitle, headersStr) {
  if (!STATE.geminiKey) {
    showToast("⚠️ 먼저 설정 탭에서 Gemini API 키를 입력하세요");
    return;
  }

  const headers = headersStr.split(",").filter(Boolean);
  const btn = event.target;
  const origText = btn.textContent;
  btn.textContent = "⏳ 생성 중...";
  btn.disabled = true;

  const prompt = `당신은 한국 연예/스포츠 전문 리서처입니다.

주제: "${topicTitle}"

이 주제에 맞는 실제 인물 TOP 10명과 후보 5명을 선정하세요.

규칙:
1. 반드시 실제로 존재하는 한국 연예인/스포츠 선수만 포함
2. 각 인물에 대해 검증된 사실만 기재
3. 30~50대 한국 남성이 관심 가질 인물 우선
4. 확실하지 않은 금액은 "약 ○○억"으로 표기
5. 후보 5명은 TOP10에 넣지 못한 이유를 1줄로 설명

표 컬럼: ${headers.join(" | ")}

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만:
{
  "top10": [
    ["1", "값1", "값2", "값3"],
    ["2", "값1", "값2", "값3"],
    ... (10개)
  ],
  "candidates": [
    {"row": ["후보1", "값1", "값2", "값3"], "reason": "TOP10에 못 든 이유"},
    ... (5개)
  ]
}`;

  try {
    const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${STATE.geminiKey}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { temperature: 0.7, maxOutputTokens: 4096 }
      })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error?.message || `HTTP ${res.status}`);
    }

    const data = await res.json();
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text || "";

    // JSON 파싱 (```json ``` 감싸기 제거)
    const clean = text.replace(/```json\s*/g, "").replace(/```/g, "").trim();
    const parsed = JSON.parse(clean);

    // 표 업데이트
    const tableContainer = document.getElementById(`table-${topicId}`);
    if (tableContainer) tableContainer.style.display = "block";
    if (tableContainer) {
      const filledData = {
        top10: parsed.top10 || [],
        candidates: (parsed.candidates || []).map(c => {
          const row = c.row || c;
          row.reason = c.reason || "";
          return row;
        })
      };
      tableContainer.innerHTML = renderTablePreview(headers, filledData);
    }

    btn.textContent = "✅ 완성!";
    setTimeout(() => { btn.textContent = origText; btn.disabled = false; }, 3000);
    showToast("🤖 표가 자동 완성되었습니다! 확인 후 복사하세요");

  } catch (e) {
    console.error("Gemini API error:", e);
    btn.textContent = origText;
    btn.disabled = false;
    if (e.message.includes("API key")) {
      showToast("❌ API 키가 잘못되었습니다. 설정을 확인하세요");
    } else if (e.message.includes("JSON")) {
      showToast("⚠️ AI 응답 파싱 실패. 다시 시도해주세요");
    } else {
      showToast("❌ " + e.message);
    }
  }
}

// ===== 복사 =====
function copyTable(topicId) {
  const card = document.getElementById(topicId);
  if (!card) return;
  const tables = card.querySelectorAll("table");
  if (!tables.length) { showToast("복사할 표가 없습니다"); return; }

  const rows = [];
  tables.forEach(table => {
    table.querySelectorAll("tr").forEach(tr => {
      const cells = [];
      tr.querySelectorAll("th, td").forEach(cell => cells.push(cell.textContent || ""));
      rows.push(cells.join("\t"));
    });
    rows.push(""); // 표 사이 빈 줄
  });

  copyToClipboard(rows.join("\n").trim(), "📋 표가 복사되었습니다! 캔바에 붙여넣으세요");
}

function copyText(text) { copyToClipboard(text, "📝 제목이 복사되었습니다"); }

function copyToClipboard(text, msg) {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(() => showToast(msg), () => fallbackCopy(text, msg));
  } else fallbackCopy(text, msg);
}

function fallbackCopy(text, msg) {
  const ta = document.createElement("textarea");
  ta.value = text; ta.style.position = "fixed"; ta.style.left = "-9999px";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); showToast(msg); } catch { showToast("❌ 복사 실패"); }
  document.body.removeChild(ta);
}

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2400);
}

// ===== 실시간 분석 =====
function clearRealtime() {
  document.getElementById("realtimeInput").value = "";
  document.getElementById("realtimeResult").innerHTML = "";
  STATE.realtime = null;
  renderCrossRecommendations();
}

function showRealtimeSample() {
  document.getElementById("realtimeInput").value = `"지예은♥바타 열애 인정?" 역대 댄서 연애·결혼 이슈 TOP 10 #연예인 #연예계소식
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
  showToast("샘플 입력됨. 분석하기 버튼을 눌러보세요.");
}

async function analyzeRealtime() {
  const text = document.getElementById("realtimeInput").value.trim();
  if (!text) { showToast("데이터를 먼저 붙여넣어주세요"); return; }

  const videos = parseRealtimeText(text);
  if (!videos.length) {
    document.getElementById("realtimeResult").innerHTML = '<div class="empty-state">파싱 실패. 형식을 확인해주세요.</div>';
    return;
  }

  STATE.realtime = analyzeAlgorithmSignals(videos);
  renderRealtimeResult(STATE.realtime);
  renderCrossRecommendations();
  showToast(`✅ ${videos.length}개 영상 분석 완료`);
}

function parseRealtimeText(text) {
  const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
  const videos = [];
  let i = 0;
  while (i < lines.length) {
    if (lines[i].length < 15) { i++; continue; }
    const title = lines[i];
    if (i + 1 >= lines.length) break;
    const dm = lines[i+1].match(/(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})/);
    if (!dm) { i++; continue; }
    let v48 = 0, v60 = 0;
    if (i+2 < lines.length) { const n = lines[i+2].replace(/[^\d]/g,""); if (n) v48 = parseInt(n); }
    if (i+3 < lines.length) { const n = lines[i+3].replace(/[^\d]/g,""); if (n) v60 = parseInt(n); }
    if (v48 > 0) { videos.push({title, date:dm[0], views_48h:v48, views_60m:v60}); i+=4; } else i++;
  }
  return videos;
}

function analyzeAlgorithmSignals(videos) {
  videos.forEach(v => {
    const avg = v.views_48h / 48;
    v.surge_ratio = avg > 0 ? v.views_60m / avg : 0;
  });
  const by60m = [...videos].sort((a,b) => b.views_60m - a.views_60m).slice(0,10);
  const angleKw = {
    "몸값·반전":["몸값","반전","회당","연봉","상승률"], "자산·금액":["자산","매출","재산","억","빚","빌딩"],
    "논란·폭로":["논란","폭로","고발","적발","사기"], "이혼·결혼":["이혼","결혼","열애","재혼"],
    "동갑·나이":["동갑","살","세","년생"], "가족·혈연":["가족","혈연","아빠","엄마"],
    "복귀·근황":["근황","복귀","컴백","공백"], "프로그램·드라마":["출연진","드라마","예능","1박","미우새","나혼산"],
    "스포츠":["KBO","야구","축구","선수","골프","FA","홈런"],
  };
  const signals = {};
  Object.entries(angleKw).forEach(([angle, kws]) => {
    const hits = by60m.filter(v => kws.some(k => v.title.includes(k)));
    if (hits.length) signals[angle] = { count:hits.length, avg:hits.reduce((s,h)=>s+h.views_60m,0)/hits.length, videos:hits.map(h=>({title:h.title,views_60m:h.views_60m})) };
  });
  return {
    total_videos:videos.length, total_views_60m:videos.reduce((s,v)=>s+v.views_60m,0),
    top_by_60m:by60m, top_angles:Object.entries(signals).map(([a,i])=>({angle:a,...i})).sort((a,b)=>b.avg-a.avg).slice(0,5),
  };
}

function renderRealtimeResult(a) {
  document.getElementById("realtimeResult").innerHTML = `
    <div class="realtime-summary"><h3>⚡ 지금 알고리즘이 밀어주는 앵글</h3><div class="angle-list">
    ${a.top_angles.map((x,i)=>`<div class="angle-item"><div><div class="angle-item-name">${i+1}. ${esc(x.angle)}</div><div class="angle-item-stats">${x.count}개 영상 · 60분 평균 ${Math.floor(x.avg).toLocaleString()}회</div></div><div style="font-size:20px">${x.count>=3?"🔥":"⚡"}</div></div>`).join("")}
    </div></div>
    <div style="background:white;border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin-bottom:20px;">
    <h3 style="margin-bottom:10px;font-size:15px;">🔥 60분 조회수 TOP 5</h3>
    ${a.top_by_60m.slice(0,5).map((v,i)=>`<div style="padding:10px 0;border-bottom:1px solid #eee;font-size:13px;"><div style="font-weight:600;">${i+1}. ${esc(v.title)}</div><div style="font-size:12px;color:#888;margin-top:3px;">48h: ${v.views_48h.toLocaleString()} / <strong style="color:#d97706;">60분: ${v.views_60m.toLocaleString()}</strong>${v.surge_ratio>1.5?` · 🚀 ${v.surge_ratio.toFixed(1)}x`:""}</div></div>`).join("")}
    </div>
    <div style="color:var(--text-secondary);font-size:13px;text-align:center;padding:10px;">💡 <strong>교차 추천</strong> 탭에서 조합 추천을 확인하세요</div>`;
}

function renderCrossRecommendations() {
  const c = document.getElementById("crossRecommendations");
  if (!STATE.realtime) { c.innerHTML = '<div class="empty-state">📊 실시간 데이터를 입력하면 교차 추천이 활성화됩니다.</div>'; return; }
  if (!STATE.scheduled) { c.innerHTML = '<div class="empty-state">⏳ 정기 스캔 데이터 없음</div>'; return; }
  const topics = STATE.scheduled.all_topics || [];
  const angles = STATE.realtime.top_angles || [];
  const akw = {"몸값·반전":["몸값","반전","회당"],"자산·금액":["자산","매출","억","빚"],"논란·폭로":["논란","폭로","사기"],"이혼·결혼":["이혼","결혼","열애"],"복귀·근황":["근황","복귀"],"스포츠":["KBO","야구","축구"]};
  const matches = [];
  topics.forEach(t => {
    if (t.dup_check?.is_duplicate) return;
    const txt = (t.title||"")+" "+(t.source_article||"");
    angles.slice(0,3).forEach(ai => {
      const kws = akw[ai.angle]||[];
      if (kws.some(k => txt.includes(k))) matches.push({...t, cross_reason:`네이버 + '${ai.angle}' 앵글 알고리즘 호조`, algo_boost:`${ai.count}개 영상 상승 중 (60분 평균 ${Math.floor(ai.avg).toLocaleString()}회)`, score:(t.score||5)+2});
    });
  });
  const seen = new Set();
  const unique = matches.filter(t => { if (seen.has(t.title)) return false; seen.add(t.title); return true; }).sort((a,b)=>b.score-a.score);
  c.innerHTML = unique.length ? `<div style="margin-bottom:20px;padding:14px 18px;background:linear-gradient(135deg,rgba(239,68,68,0.05),rgba(245,158,11,0.03));border-radius:10px;border-left:4px solid var(--danger);"><strong>🎯 ${unique.length}개 교차 추천</strong></div>${unique.slice(0,15).map((t,i)=>renderTopicCard(t,i,true)).join("")}` : '<div class="empty-state">🔍 교차 매칭 주제 없음</div>';
}

// ===== 히스토리 =====
async function loadHistory() {
  try {
    const res = await fetch("data/scan_log.json?t="+Date.now());
    if (!res.ok) throw new Error("no log");
    const logs = await res.json();
    document.getElementById("historyList").innerHTML = `<div style="background:white;border:1px solid var(--border);border-radius:12px;overflow:hidden;">
    ${logs.map(l=>`<div style="padding:14px 18px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center;gap:16px;"><div><div style="font-weight:600;font-size:14px;">${esc(l.time)}</div><div style="font-size:12px;color:var(--text-secondary);margin-top:3px;">기사 ${l.articles}개 / 추천 ${l.topics}개</div></div><a href="data/${esc(l.file)}" target="_blank" style="color:var(--primary);font-size:13px;font-weight:600;text-decoration:none;">JSON →</a></div>`).join("")}
    </div>`;
  } catch { document.getElementById("historyList").innerHTML = '<div class="empty-state">히스토리 없음</div>'; }
}

function esc(s) { return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
