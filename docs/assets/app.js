/* 정보주는 하마 트렌드 스캐너 v4.0 - 기사 기반 주제 제작 */

var STATE = { data: null, geminiKey: "" };

document.addEventListener("DOMContentLoaded", function() {
  setupTabs();
  loadGeminiKey();
  loadData();
  loadHistory();
});

function setupTabs() {
  var tabs = document.querySelectorAll(".tab");
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].addEventListener("click", function() {
      var t = this.dataset.tab;
      var all = document.querySelectorAll(".tab");
      var pans = document.querySelectorAll(".tab-panel");
      for (var j = 0; j < all.length; j++) all[j].classList.remove("active");
      for (var j = 0; j < pans.length; j++) pans[j].classList.remove("active");
      this.classList.add("active");
      document.getElementById("tab-" + t).classList.add("active");
    });
  }
}

function loadGeminiKey() {
  try { STATE.geminiKey = localStorage.getItem("gemini_api_key") || ""; } catch(e) {}
  var inp = document.getElementById("geminiKeyInput");
  if (inp && STATE.geminiKey) inp.value = STATE.geminiKey;
}
function saveGeminiKey() {
  var inp = document.getElementById("geminiKeyInput");
  if (!inp) return;
  STATE.geminiKey = inp.value.trim();
  try { localStorage.setItem("gemini_api_key", STATE.geminiKey); } catch(e) {}
  showToast(STATE.geminiKey ? "✅ API 키 저장" : "삭제됨");
}
function toggleKeyVisibility() {
  var inp = document.getElementById("geminiKeyInput");
  if (inp) inp.type = (inp.type === "password") ? "text" : "password";
}

/* ========== 데이터 로드 ========== */
function loadData() {
  fetch("data/latest.json?t=" + Date.now())
    .then(function(r) { if (!r.ok) throw new Error(); return r.json(); })
    .then(function(d) {
      STATE.data = d;
      document.getElementById("lastScanTime").textContent = "마지막 스캔: " + (d.scan_time || "-");
      document.getElementById("stat-articles").textContent = d.total_articles || 0;
      document.getElementById("stat-topics").textContent = d.total_topics_generated || 0;
      document.getElementById("stat-dups").textContent = d.excluded_duplicates || 0;
      document.getElementById("stat-final").textContent = (d.topics || []).length;
      renderArticles();
      renderThemeAnalysis();
    })
    .catch(function() {
      document.getElementById("lastScanTime").textContent = "데이터 없음";
      document.getElementById("articlesList").innerHTML = '<div class="empty-state">⏳ 스캔 결과 없음</div>';
    });
}

/* ========== 탭1: 기사 랭킹 + 주제 제작 ========== */
function renderArticles() {
  if (!STATE.data) return;
  var arts = STATE.data.articles || [];
  if (!arts.length) { document.getElementById("articlesList").innerHTML = '<div class="empty-state">기사 없음</div>'; return; }

  // 카테고리 분리
  var entArts = [], sportArts = [];
  for (var i = 0; i < arts.length; i++) {
    if (arts[i].category === "스포츠") sportArts.push(arts[i]);
    else entArts.push(arts[i]);
  }

  var html = '';

  // 연예
  html += '<h3 style="font-size:16px;margin-bottom:12px;">🎬 연예 많이 본 뉴스 (' + entArts.length + '개)</h3>';
  html += renderArticleList(entArts, "ent");

  // 스포츠
  if (sportArts.length) {
    html += '<h3 style="font-size:16px;margin:24px 0 12px;">⚾ 스포츠 많이 본 뉴스 (' + sportArts.length + '개)</h3>';
    html += renderArticleList(sportArts, "sport");
  }

  document.getElementById("articlesList").innerHTML = html;
}

function renderArticleList(arts, prefix) {
  var html = '<div style="background:white;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">';
  for (var i = 0; i < arts.length; i++) {
    var a = arts[i];
    var url = a.url || "";
    var views = a.views ? a.views.toLocaleString() + "회" : "";
    var titleLink = url ? '<a href="' + esc(url) + '" target="_blank" style="color:#1f2937;text-decoration:none;font-weight:600;">' + esc(a.title) + '</a>' : '<span style="font-weight:600;">' + esc(a.title) + '</span>';
    var artId = prefix + "_" + i;

    html += '<div style="padding:12px 16px;border-bottom:1px solid #f3f4f6;">' +
      '<div style="display:flex;align-items:flex-start;gap:12px;">' +
        '<div style="min-width:28px;height:28px;border-radius:8px;background:' + (i < 3 ? 'linear-gradient(135deg,#ef4444,#dc2626)' : (i < 10 ? '#4f46e5' : '#9ca3af')) + ';display:flex;align-items:center;justify-content:center;color:white;font-weight:800;font-size:12px;">' + (a.rank || (i+1)) + '</div>' +
        '<div style="flex:1;min-width:0;">' +
          '<div style="font-size:14px;line-height:1.5;margin-bottom:4px;">' + titleLink + '</div>' +
          '<div style="display:flex;gap:12px;align-items:center;">' +
            (views ? '<span style="font-size:12px;color:#d97706;font-weight:600;">👁 ' + views + '</span>' : '') +
            '<span style="font-size:11px;color:#9ca3af;">' + esc(a.source || "") + '</span>' +
          '</div>' +
        '</div>' +
        '<button onclick="openTopicCreator(\'' + artId + '\',\'' + esc(a.title) + '\',\'' + esc(url) + '\')" style="padding:6px 14px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;border:none;background:linear-gradient(135deg,#4285f4,#34a853);color:white;white-space:nowrap;">🎯 주제 만들기</button>' +
      '</div>' +
      '<div id="creator_' + artId + '" style="display:none;"></div>' +
    '</div>';
  }
  html += '</div>';
  return html;
}

/* ========== 주제 제작 패널 ========== */
function openTopicCreator(artId, articleTitle, articleUrl) {
  var container = document.getElementById("creator_" + artId);
  if (!container) return;

  // 이미 열려있으면 닫기
  if (container.style.display === "block") {
    container.style.display = "none";
    return;
  }

  container.style.display = "block";
  container.innerHTML = '<div style="margin-top:12px;padding:16px;background:#f8fafc;border-radius:10px;border:1px solid #e5e7eb;">' +
    '<div style="font-size:13px;color:#6b7280;margin-bottom:12px;">📰 원본: ' + esc(articleTitle) + '</div>' +

    '<div style="margin-bottom:12px;">' +
      '<button onclick="suggestAngles(\'' + artId + '\',\'' + esc(articleTitle) + '\')" style="padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;background:#7c3aed;color:white;">🤖 AI 앵글 제안받기</button>' +
      '<span style="font-size:12px;color:#9ca3af;margin-left:8px;">또는 아래에 직접 입력</span>' +
    '</div>' +
    '<div id="suggestions_' + artId + '" style="margin-bottom:12px;"></div>' +

    '<div style="margin-bottom:8px;">' +
      '<label style="font-size:12px;font-weight:600;color:#374151;">영상 주제 (수정 가능)</label>' +
      '<input id="topic_' + artId + '" type="text" placeholder="예: KBO 선수 음주운전 징계 TOP10" style="width:100%;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;margin-top:4px;box-sizing:border-box;">' +
    '</div>' +

    '<div style="margin-bottom:8px;">' +
      '<label style="font-size:12px;font-weight:600;color:#374151;">리서치 지시 (AI에게 구체적으로)</label>' +
      '<textarea id="instruction_' + artId + '" placeholder="예: KBO에서 음주운전으로 적발된 선수들을 조사해서, 적발 횟수가 많은 순으로 정리해줘. 징계 내용과 현재 활동 여부도 포함." style="width:100%;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;min-height:70px;margin-top:4px;box-sizing:border-box;resize:vertical;"></textarea>' +
    '</div>' +

    '<div style="margin-bottom:12px;">' +
      '<label style="font-size:12px;font-weight:600;color:#374151;">표 컬럼 (쉼표로 구분, 수정 가능)</label>' +
      '<input id="columns_' + artId + '" type="text" value="이름,소속·직업,이슈 내용,현재 상황" style="width:100%;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;margin-top:4px;box-sizing:border-box;">' +
    '</div>' +

    '<div style="display:flex;gap:8px;">' +
      '<button onclick="generateTable(\'' + artId + '\')" style="padding:10px 20px;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;border:none;background:linear-gradient(135deg,#4285f4,#34a853);color:white;">🤖 표 채우기</button>' +
    '</div>' +

    '<div id="result_' + artId + '" style="margin-top:12px;"></div>' +
  '</div>';
}

/* AI 앵글 제안 */
function suggestAngles(artId, articleTitle) {
  if (!STATE.geminiKey) { showToast("⚠️ 설정에서 API 키를 입력하세요"); return; }

  var container = document.getElementById("suggestions_" + artId);
  container.innerHTML = '<div style="padding:8px;color:#6b7280;font-size:13px;">⏳ AI가 앵글 분석 중...</div>';

  var prompt = '당신은 한국 유튜브 채널 "정보주는 하마"의 콘텐츠 기획자입니다.\n' +
    '타겟: 한국 남성 30~50대\n' +
    '채널 스타일: 연예인/스포츠 TOP10 숏츠 (6분 내외)\n' +
    '히트 제목 패턴: 따옴표 인용 + 구체 금액/숫자 + 의문문(?)\n\n' +
    '아래 뉴스 기사를 보고, 이 기사에서 파생할 수 있는 구체적인 TOP10 영상 주제를 3개 제안하세요.\n\n' +
    '기사: "' + articleTitle + '"\n\n' +
    '각 제안에 포함할 것:\n' +
    '1. 영상 제목 (채널 히트 패턴 적용)\n' +
    '2. 어떤 인물/선수를 모아야 하는지 1줄 설명\n' +
    '3. 추천 표 컬럼 (4개)\n\n' +
    '반드시 JSON만 응답:\n' +
    '[{"title":"영상 제목","description":"어떤 인물을 모을지","columns":"컬럼1,컬럼2,컬럼3,컬럼4"},...]';

  callGemini(prompt, function(text) {
    try {
      var clean = text.replace(/```json\s*/g, "").replace(/```/g, "").trim();
      var suggestions = JSON.parse(clean);

      var html = '<div style="font-size:12px;font-weight:600;color:#7c3aed;margin-bottom:6px;">💡 AI 제안 (클릭하면 자동 입력):</div>';
      for (var i = 0; i < suggestions.length; i++) {
        var s = suggestions[i];
        html += '<div onclick="applySuggestion(\'' + artId + '\',' + i + ')" data-title="' + esc(s.title) + '" data-desc="' + esc(s.description) + '" data-cols="' + esc(s.columns) + '" ' +
          'style="padding:10px 12px;margin-bottom:6px;background:white;border:1px solid #e5e7eb;border-radius:8px;cursor:pointer;transition:all 0.15s;" ' +
          'onmouseover="this.style.borderColor=\'#7c3aed\';this.style.background=\'#faf5ff\'" onmouseout="this.style.borderColor=\'#e5e7eb\';this.style.background=\'white\'">' +
          '<div style="font-size:14px;font-weight:700;color:#1f2937;margin-bottom:4px;">' + esc(s.title) + '</div>' +
          '<div style="font-size:12px;color:#6b7280;">' + esc(s.description) + '</div>' +
          '<div style="font-size:11px;color:#9ca3af;margin-top:3px;">📋 ' + esc(s.columns) + '</div>' +
        '</div>';
      }
      container.innerHTML = html;

      // 전역에 suggestions 저장
      window["_suggestions_" + artId] = suggestions;
    } catch(e) {
      container.innerHTML = '<div style="color:#ef4444;font-size:13px;">❌ 파싱 실패. 다시 시도해주세요.</div>';
    }
  }, function(err) {
    container.innerHTML = '<div style="color:#ef4444;font-size:13px;">❌ ' + esc(err) + '</div>';
  });
}

function applySuggestion(artId, idx) {
  var suggestions = window["_suggestions_" + artId];
  if (!suggestions || !suggestions[idx]) return;
  var s = suggestions[idx];

  document.getElementById("topic_" + artId).value = s.title || "";
  document.getElementById("instruction_" + artId).value = s.description || "";
  document.getElementById("columns_" + artId).value = s.columns || "";
  showToast("✅ 제안 적용됨! 수정 후 표 채우기 클릭");
}

/* 표 생성 */
function generateTable(artId) {
  if (!STATE.geminiKey) { showToast("⚠️ 설정에서 API 키 입력"); return; }

  var topic = document.getElementById("topic_" + artId).value.trim();
  var instruction = document.getElementById("instruction_" + artId).value.trim();
  var columns = document.getElementById("columns_" + artId).value.trim();

  if (!topic) { showToast("주제를 입력하세요"); return; }
  if (!columns) { showToast("표 컬럼을 입력하세요"); return; }

  var container = document.getElementById("result_" + artId);
  container.innerHTML = '<div style="padding:20px;text-align:center;color:#6b7280;">⏳ Gemini가 인물 리서치 중... (5~15초)</div>';

  var headers = columns.split(",");
  for (var i = 0; i < headers.length; i++) headers[i] = headers[i].trim();

  var prompt = '당신은 한국 연예/스포츠 전문 리서처입니다.\n\n' +
    '주제: "' + topic + '"\n' +
    (instruction ? '리서치 지시: ' + instruction + '\n' : '') +
    '\n타겟: 30~50대 한국 남성\n\n' +
    '규칙:\n' +
    '1. 반드시 실제 존재하는 인물만 포함\n' +
    '2. 검증된 사실만 기재 (불확실하면 "약 ○○억" 등으로 표기)\n' +
    '3. TOP10은 가장 임팩트 있는 순서로 정렬\n' +
    '4. 후보 5명은 TOP10에 못 든 구체적 이유 1줄 포함\n\n' +
    '표 컬럼: ' + headers.join(" | ") + '\n\n' +
    '반드시 아래 JSON만 응답 (다른 텍스트 없이):\n' +
    '{"top10":[["1","값","값","값"],["2","값","값","값"],...(정확히 10개)],' +
    '"candidates":[{"row":["후보1","값","값","값"],"reason":"TOP10에 못 든 이유"},... (5개)]}';

  callGemini(prompt, function(text) {
    try {
      var clean = text.replace(/```json\s*/g, "").replace(/```/g, "").trim();
      var parsed = JSON.parse(clean);

      var tableHtml = buildTableHtml(headers, parsed.top10 || [], parsed.candidates || []);
      container.innerHTML = '<div style="background:#fafafa;border-radius:8px;padding:12px;border:1px solid #e5e7eb;">' +
        '<div style="font-size:15px;font-weight:700;margin-bottom:10px;">📊 ' + esc(topic) + '</div>' +
        tableHtml +
        '<div style="display:flex;gap:8px;margin-top:12px;">' +
          '<button onclick="copyTableFrom(\'' + artId + '\')" style="padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;background:#4f46e5;color:white;">📋 표 복사 (캔바용)</button>' +
          '<button onclick="copyTitleFrom(\'' + artId + '\')" style="padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;background:#374151;color:white;">📝 제목 복사</button>' +
        '</div>' +
      '</div>';
      showToast("🤖 표 완성! 확인 후 복사하세요");
    } catch(e) {
      container.innerHTML = '<div style="padding:16px;color:#ef4444;background:#fef2f2;border-radius:8px;">❌ AI 응답 파싱 실패. 다시 시도해주세요.<br><small>' + esc(e.message) + '</small></div>';
    }
  }, function(err) {
    container.innerHTML = '<div style="padding:16px;color:#ef4444;background:#fef2f2;border-radius:8px;">❌ ' + esc(err) + '</div>';
  });
}

function buildTableHtml(headers, top10, candidates) {
  var html = '<table style="border-collapse:collapse;width:100%;font-size:13px;"><thead><tr>';
  for (var h = 0; h < headers.length; h++) html += '<th style="background:#f3f4f6;padding:8px 10px;text-align:left;font-weight:700;border:1px solid #e5e7eb;">' + esc(headers[h]) + '</th>';
  html += '</tr></thead><tbody>';
  for (var r = 0; r < top10.length; r++) {
    html += '<tr>';
    for (var c = 0; c < headers.length; c++) {
      var val = (top10[r] && top10[r][c]) ? top10[r][c] : "";
      html += '<td style="padding:6px 10px;border:1px solid #e5e7eb;' + (c === 0 ? 'font-weight:600;color:#4f46e5;' : '') + '">' + esc(val) + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table>';

  if (candidates.length) {
    html += '<div style="margin-top:14px;padding-top:12px;border-top:2px dashed #e5e7eb;">' +
      '<div style="font-weight:700;font-size:13px;margin-bottom:8px;color:#d97706;">🎯 후보 5명 (대체 가능)</div>' +
      '<table style="border-collapse:collapse;width:100%;font-size:13px;"><thead><tr>';
    for (var h = 0; h < headers.length; h++) html += '<th style="background:#fef3c7;padding:8px 10px;text-align:left;font-weight:700;border:1px solid #e5e7eb;">' + esc(headers[h]) + '</th>';
    html += '<th style="background:#fef3c7;padding:8px 10px;text-align:left;font-weight:700;border:1px solid #e5e7eb;">후보 사유</th></tr></thead><tbody>';
    for (var r = 0; r < candidates.length; r++) {
      var row = candidates[r].row || candidates[r];
      var reason = candidates[r].reason || "";
      html += '<tr>';
      for (var c = 0; c < headers.length; c++) {
        var val = (row && row[c]) ? row[c] : "";
        html += '<td style="padding:6px 10px;border:1px solid #e5e7eb;' + (c === 0 ? 'font-weight:600;color:#d97706;' : '') + '">' + esc(val) + '</td>';
      }
      html += '<td style="padding:6px 10px;border:1px solid #e5e7eb;font-size:11px;color:#888;">' + esc(reason) + '</td></tr>';
    }
    html += '</tbody></table></div>';
  }

  return html;
}

/* ========== 탭1 하단: 주제 분석 ========== */
function renderThemeAnalysis() {
  if (!STATE.data) return;
  var el = document.getElementById("themeAnalysis");
  if (!el) return;

  var arts = STATE.data.articles || [];
  // 기사 제목에서 주제(테마) 감지
  var themes = {
    "💰 자산·몸값·매출": { pattern: /자산|재산|연봉|몸값|부동산|빌딩|매출|수익|출연료|억|조원/, arts: [] },
    "😱 논란·사건·폭로": { pattern: /논란|폭로|고발|적발|음주|사기|탈세|도박|갑질|구속|체포|혐의/, arts: [] },
    "💍 결혼·이혼·열애": { pattern: /결혼|이혼|열애|재혼|파혼|임신|출산|약혼/, arts: [] },
    "🔄 복귀·근황·은퇴": { pattern: /복귀|근황|컴백|은퇴|전역|공백/, arts: [] },
    "🏥 투병·건강·사망": { pattern: /투병|완치|수술|입원|암|사망|별세|부고/, arts: [] },
    "⚾ 스포츠 기록·이적": { pattern: /홈런|안타|골|우승|FA|트레이드|MVP|감독|선발/, arts: [] },
    "👨‍👩‍👧 가족·혈연·동갑": { pattern: /가족|혈연|동갑|형제|부모|2세|자녀|아들|딸/, arts: [] },
  };

  for (var i = 0; i < arts.length; i++) {
    for (var key in themes) {
      if (themes[key].pattern.test(arts[i].title)) {
        themes[key].arts.push(arts[i]);
      }
    }
  }

  var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;">';
  for (var key in themes) {
    var t = themes[key];
    if (t.arts.length === 0) continue;
    html += '<div style="background:white;border:1px solid #e5e7eb;border-radius:10px;padding:14px;">' +
      '<div style="font-size:14px;font-weight:700;margin-bottom:8px;">' + key + ' <span style="color:#4f46e5;">(' + t.arts.length + '건)</span></div>';
    for (var j = 0; j < Math.min(t.arts.length, 3); j++) {
      html += '<div style="font-size:12px;color:#6b7280;padding:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">· ' + esc(t.arts[j].title) + '</div>';
    }
    html += '</div>';
  }
  html += '</div>';
  el.innerHTML = html;
}

/* ========== 복사 ========== */
function copyTableFrom(artId) {
  var container = document.getElementById("result_" + artId);
  if (!container) { showToast("표가 없습니다"); return; }
  var tables = container.querySelectorAll("table");
  if (!tables.length) { showToast("표가 없습니다"); return; }
  var rows = [];
  for (var t = 0; t < tables.length; t++) {
    var trs = tables[t].querySelectorAll("tr");
    for (var r = 0; r < trs.length; r++) {
      var cells = trs[r].querySelectorAll("th, td");
      var row = [];
      for (var c = 0; c < cells.length; c++) row.push(cells[c].textContent || "");
      rows.push(row.join("\t"));
    }
    rows.push("");
  }
  copyClip(rows.join("\n").trim(), "📋 표 복사 완료! 캔바에 붙여넣으세요");
}

function copyTitleFrom(artId) {
  var inp = document.getElementById("topic_" + artId);
  if (inp && inp.value) copyClip(inp.value, "📝 제목 복사 완료");
  else showToast("제목이 없습니다");
}

function copyClip(text, msg) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() { showToast(msg); }, function() { fallbackCopy(text, msg); });
  } else fallbackCopy(text, msg);
}
function fallbackCopy(text, msg) {
  var ta = document.createElement("textarea");
  ta.value = text; ta.style.position = "fixed"; ta.style.left = "-9999px";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); showToast(msg); } catch(e) { showToast("❌ 복사 실패"); }
  document.body.removeChild(ta);
}

/* ========== 실시간 분석 ========== */
function clearRealtime() {
  document.getElementById("realtimeInput").value = "";
  document.getElementById("realtimeResult").innerHTML = "";
}
function showRealtimeSample() {
  document.getElementById("realtimeInput").value = '"지예은 바타 열애 인정?" 역대 댄서 연애 결혼 이슈 TOP 10\n2026. 4. 13.\n388183\n8070\n\n"최충연부터 이종범까지?" 팬들 분통 터진 야구 논란 TOP10\n2026. 4. 14.\n186169\n6383';
  showToast("샘플 입력됨");
}
function analyzeRealtime() {
  var text = document.getElementById("realtimeInput").value.trim();
  if (!text) { showToast("데이터를 먼저 붙여넣어주세요"); return; }
  var lines = text.split("\n"), videos = [], i = 0;
  while (i < lines.length) {
    var line = (lines[i] || "").trim();
    if (line.length < 15) { i++; continue; }
    if (i + 1 >= lines.length) break;
    var dm = (lines[i+1] || "").match(/(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})/);
    if (!dm) { i++; continue; }
    var v48 = 0, v60 = 0;
    if (i+2 < lines.length) { var n = (lines[i+2]||"").replace(/[^\d]/g,""); if (n) v48 = parseInt(n); }
    if (i+3 < lines.length) { var n = (lines[i+3]||"").replace(/[^\d]/g,""); if (n) v60 = parseInt(n); }
    if (v48 > 0) { videos.push({title:line,v48:v48,v60:v60}); i+=4; } else i++;
  }
  if (!videos.length) { document.getElementById("realtimeResult").innerHTML = '<div class="empty-state">파싱 실패</div>'; return; }
  videos.sort(function(a,b) { return b.v60 - a.v60; });

  var html = '<div style="background:white;border:1px solid #e5e7eb;border-radius:12px;padding:18px 20px;">' +
    '<h3 style="margin-bottom:10px;">🔥 60분 조회수 TOP 5</h3>';
  for (var j = 0; j < Math.min(videos.length,5); j++) {
    var v = videos[j];
    html += '<div style="padding:10px 0;border-bottom:1px solid #eee;font-size:13px;">' +
      '<div style="font-weight:600;">' + (j+1) + '. ' + esc(v.title) + '</div>' +
      '<div style="font-size:12px;color:#888;margin-top:3px;">48h: ' + v.v48.toLocaleString() + ' / <strong style="color:#d97706;">60분: ' + v.v60.toLocaleString() + '</strong></div></div>';
  }
  html += '</div>';
  document.getElementById("realtimeResult").innerHTML = html;
  showToast("✅ " + videos.length + "개 분석 완료");
}

/* ========== 히스토리 ========== */
function loadHistory() {
  fetch("data/scan_log.json?t=" + Date.now())
    .then(function(r) { if (!r.ok) throw new Error(); return r.json(); })
    .then(function(logs) {
      var html = '<div style="background:white;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">';
      for (var i = 0; i < logs.length; i++) {
        html += '<div style="padding:14px 18px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;">' +
          '<div><div style="font-weight:600;">' + esc(logs[i].time) + '</div><div style="font-size:12px;color:#888;">기사 ' + logs[i].articles + '개 / 추천 ' + logs[i].topics + '개</div></div>' +
          '<a href="data/' + esc(logs[i].file) + '" target="_blank" style="color:#4f46e5;font-size:13px;font-weight:600;text-decoration:none;">JSON →</a></div>';
      }
      html += '</div>';
      document.getElementById("historyList").innerHTML = html;
    })
    .catch(function() { document.getElementById("historyList").innerHTML = '<div class="empty-state">히스토리 없음</div>'; });
}

/* ========== Gemini API 호출 ========== */
function callGemini(prompt, onSuccess, onError) {
  fetch("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key=" + STATE.geminiKey, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0.7, maxOutputTokens: 4096 } })
  })
  .then(function(r) {
    if (!r.ok) return r.json().then(function(e) { throw new Error(e.error ? e.error.message : "HTTP " + r.status); });
    return r.json();
  })
  .then(function(data) {
    var text = "";
    try { text = data.candidates[0].content.parts[0].text; } catch(e) { throw new Error("응답 없음"); }
    onSuccess(text);
  })
  .catch(function(e) { onError(e.message); });
}

function showToast(msg) {
  var t = document.getElementById("toast");
  if (!t) return;
  t.textContent = msg; t.classList.add("show");
  setTimeout(function() { t.classList.remove("show"); }, 2400);
}

function esc(s) {
  if (!s) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}
