/* ═══════════════════════════════════════
   정보주는 하마 · 트렌드 스캐너 v4.0
   app.js — 대시보드 로직
   ═══════════════════════════════════════ */

(function () {
  "use strict";

  // ── State ──
  let scanData = null;
  let currentFilter = "all";
  let currentTableData = null; // { headers, rows }

  // ── DOM ──
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // ── Init ──
  document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initSettings();
    initModal();
    initRealtime();
    loadScanData();
  });

  // ═══════════════════════════════════════
  // Tabs
  // ═══════════════════════════════════════
  function initTabs() {
    $$(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$(".tab").forEach((t) => t.classList.remove("active"));
        $$(".tab-panel").forEach((p) => p.classList.remove("active"));
        tab.classList.add("active");
        $(`#panel-${tab.dataset.tab}`).classList.add("active");
      });
    });
  }

  // ═══════════════════════════════════════
  // Load scan data
  // ═══════════════════════════════════════
  async function loadScanData() {
    try {
      const r = await fetch("data/latest.json?t=" + Date.now());
      if (!r.ok) throw new Error("No data");
      scanData = await r.json();
      renderStats();
      renderTopics();
      renderArticles();
      loadHistory();
    } catch (e) {
      console.error("Data load failed:", e);
      $("#topicsList").innerHTML = `<div class="loading-placeholder">⚠ 스캔 데이터 없음. Actions에서 수동 실행하세요.</div>`;
      $("#articlesList").innerHTML = `<div class="loading-placeholder">데이터 없음</div>`;
    }
  }

  // ── Stats bar ──
  function renderStats() {
    if (!scanData) return;
    $("#scanTime").textContent = scanData.scan_time || "-";
    $("#statArticles").textContent = scanData.total_articles || 0;
    $("#statTopics").textContent = (scanData.total_topics_generated || 0);
    $("#statDup").textContent = scanData.excluded_duplicates || 0;
    $("#statValid").textContent = scanData.valid_topics || 0;
    // AI 분석 여부
    if (scanData.ai_analyzed) {
      $("#scanTime").textContent += " · 🤖 AI";
    }
  }

  // ═══════════════════════════════════════
  // AI 추천 주제
  // ═══════════════════════════════════════
  function renderTopics() {
    const container = $("#topicsList");
    const topics = scanData?.topics || [];
    if (!topics.length) {
      container.innerHTML = `<div class="loading-placeholder">추천 주제가 없습니다.</div>`;
      return;
    }

    container.innerHTML = topics.map((t, i) => {
      const conf = t.confidence || 0;
      let badgeClass, badgeLabel;
      if (conf >= 8) { badgeClass = "badge-fire"; badgeLabel = `🔥 ${conf}/10`; }
      else if (conf >= 5) { badgeClass = "badge-good"; badgeLabel = `✅ ${conf}/10`; }
      else { badgeClass = "badge-ok"; badgeLabel = `📌 ${conf}/10`; }
      if (!t.ai_generated) { badgeClass = "badge-fallback"; badgeLabel = "📊 키워드"; }

      // 관련 기사
      const sources = (t.source_articles || []).map((s) => {
        if (s.url) {
          return `<a href="${escHtml(s.url)}" target="_blank" title="${escHtml(s.title)}">${truncate(s.title, 40)}</a>`;
        }
        return `<span>${truncate(s.title, 40)}</span>`;
      }).join(" · ");

      // 컬럼 태그
      const cols = (t.table_columns || []).map((c) => `<span class="topic-tag">${escHtml(c)}</span>`).join("");

      // 중복 체크
      let dupHtml = "";
      if (t.dup_check) {
        if (t.dup_check.status === "재활용 가능") {
          dupHtml = `<div class="topic-dup dup-reuse">♻️ ${escHtml(t.dup_check.reason)} — ${truncate(t.dup_check.matched_title, 30)}</div>`;
        } else if (t.dup_check.status === "통과" && t.dup_check.matched_title) {
          dupHtml = `<div class="topic-dup dup-ok">✅ 유사: ${truncate(t.dup_check.matched_title, 30)} (${t.dup_check.reason || '통과'})</div>`;
        }
      }

      return `
        <div class="topic-card" data-idx="${i}">
          <div class="topic-top">
            <div class="topic-title">${escHtml(t.title)}</div>
            <span class="topic-badge ${badgeClass}">${badgeLabel}</span>
          </div>
          ${t.angle ? `<div class="topic-angle">💡 ${escHtml(t.angle)}</div>` : ""}
          <div class="topic-meta">${cols}</div>
          ${sources ? `<div class="topic-sources">📎 ${sources}</div>` : ""}
          <div class="topic-actions">
            <button class="btn btn-primary btn-sm" onclick="openTableModal(${i})">📝 표 채우기</button>
            <button class="btn btn-ghost btn-sm" onclick="copyTopicTitle(${i})">📋 제목 복사</button>
          </div>
          ${dupHtml}
        </div>`;
    }).join("");
  }

  // ═══════════════════════════════════════
  // 기사 목록
  // ═══════════════════════════════════════
  function renderArticles() {
    const container = $("#articlesList");
    let articles = scanData?.articles || [];
    if (currentFilter !== "all") {
      articles = articles.filter((a) => a.category === currentFilter);
    }
    if (!articles.length) {
      container.innerHTML = `<div class="loading-placeholder">기사 없음</div>`;
      return;
    }

    container.innerHTML = articles.map((a, i) => {
      const catClass = a.category === "연예" ? "cat-ent" : "cat-sport";
      const rankClass = a.rank <= 3 ? "top3" : "";
      const views = a.views ? `${numberFormat(a.views)}회` : "";
      const link = a.url
        ? `<a href="${escHtml(a.url)}" target="_blank">${escHtml(a.title)}</a>`
        : escHtml(a.title);

      return `
        <div class="article-row ${catClass}">
          <div class="article-rank ${rankClass}">${a.rank}</div>
          <div class="article-title-wrap">
            <div class="article-title">${link}</div>
            <div class="article-source">${escHtml(a.source)} · ${escHtml(a.category)}</div>
          </div>
          <div class="article-views">${views}</div>
        </div>`;
    }).join("");

    // Filter buttons
    $$(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".filter-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentFilter = btn.dataset.filter;
        renderArticles();
      });
    });
  }

  // ═══════════════════════════════════════
  // 표 채우기 모달
  // ═══════════════════════════════════════
  function initModal() {
    $("#btnCloseModal").addEventListener("click", closeModal);
    $("#tableModal").addEventListener("click", (e) => {
      if (e.target === $("#tableModal")) closeModal();
    });
    $("#btnFillTable").addEventListener("click", fillTable);
    $("#btnCopyTSV").addEventListener("click", () => copyTable("tsv"));
    $("#btnCopyMarkdown").addEventListener("click", () => copyTable("md"));
  }

  window.openTableModal = function (idx) {
    const topic = scanData?.topics?.[idx];
    if (!topic) return;

    $("#modalVideoTitle").value = topic.title || "";
    $("#modalResearch").value = topic.research_instruction || "";
    $("#modalColumns").value = (topic.table_columns || []).join(", ");
    $("#modalTitle").textContent = "📝 표 채우기";
    $("#tableResult").innerHTML = "";
    $("#tableCopyArea").style.display = "none";
    $("#tableLoading").style.display = "none";
    currentTableData = null;

    $("#tableModal").classList.add("open");
  };

  function closeModal() {
    $("#tableModal").classList.remove("open");
  }

  async function fillTable() {
    const apiKey = localStorage.getItem("gemini_api_key");
    if (!apiKey) {
      toast("⚠ 설정 탭에서 Gemini API 키를 입력하세요");
      return;
    }

    const title = $("#modalVideoTitle").value.trim();
    const research = $("#modalResearch").value.trim();
    const columns = $("#modalColumns").value.split(",").map((c) => c.trim()).filter(Boolean);

    if (!title || columns.length < 2) {
      toast("⚠ 제목과 컬럼을 입력하세요");
      return;
    }

    $("#tableLoading").style.display = "flex";
    $("#tableResult").innerHTML = "";
    $("#tableCopyArea").style.display = "none";
    $("#btnFillTable").disabled = true;

    const prompt = `당신은 유튜브 TOP10 영상의 표를 채우는 전문가입니다.

영상 제목: ${title}
리서치 지시: ${research || '해당 주제의 대표적 인물/사례를 조사'}
표 컬럼: ${columns.join(" | ")}

**지시사항:**
1. TOP10 (10명/10개)을 채워주세요. 각 항목은 실제 사실에 기반해야 합니다.
2. 추가로 후보 5명도 만들어주세요 (11~15번).
3. 1위가 가장 임팩트 있는 항목이어야 합니다.
4. 각 셀은 간결하게 (20자 내외).

**반드시 아래 JSON 형식으로만 응답하세요:**

\`\`\`json
{
  "headers": ${JSON.stringify(columns)},
  "rows": [
    {"rank": 1, "cells": ["셀1", "셀2", "셀3", "셀4"], "type": "main"},
    ...
    {"rank": 11, "cells": ["셀1", "셀2", "셀3", "셀4"], "type": "candidate"}
  ]
}
\`\`\``;

    try {
      const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key=${apiKey}`;
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: {
            temperature: 0.5,
            maxOutputTokens: 4096,
            responseMimeType: "application/json",
          },
        }),
      });

      if (!r.ok) {
        const err = await r.text();
        throw new Error(`API ${r.status}: ${err.slice(0, 200)}`);
      }

      const data = await r.json();
      let text = data.candidates?.[0]?.content?.parts?.[0]?.text || "";
      text = text.replace(/^```\w*\n?/, "").replace(/\n?```$/, "").trim();
      const result = JSON.parse(text);

      currentTableData = result;
      renderTable(result);
      $("#tableCopyArea").style.display = "block";
    } catch (e) {
      console.error("Table fill error:", e);
      $("#tableResult").innerHTML = `<div style="color:var(--red);padding:12px;">⚠ 오류: ${escHtml(e.message)}</div>`;
    } finally {
      $("#tableLoading").style.display = "none";
      $("#btnFillTable").disabled = false;
    }
  }

  function renderTable(data) {
    if (!data || !data.rows) return;
    const headers = data.headers || [];
    const mainRows = data.rows.filter((r) => r.type !== "candidate");
    const candRows = data.rows.filter((r) => r.type === "candidate");

    let html = `<table><thead><tr><th>#</th>${headers.map((h) => `<th>${escHtml(h)}</th>`).join("")}</tr></thead><tbody>`;
    mainRows.forEach((r) => {
      html += `<tr><td>${r.rank}</td>${(r.cells || []).map((c) => `<td>${escHtml(c)}</td>`).join("")}</tr>`;
    });
    if (candRows.length) {
      html += `<tr class="divider-row"><td colspan="${headers.length + 1}">── 후보 5명 ──</td></tr>`;
      candRows.forEach((r) => {
        html += `<tr class="candidate"><td>${r.rank}</td>${(r.cells || []).map((c) => `<td>${escHtml(c)}</td>`).join("")}</tr>`;
      });
    }
    html += `</tbody></table>`;
    $("#tableResult").innerHTML = html;
  }

  function copyTable(format) {
    if (!currentTableData) return;
    const { headers, rows } = currentTableData;
    let text = "";

    if (format === "tsv") {
      text = headers.join("\t") + "\n";
      rows.forEach((r) => {
        text += (r.cells || []).join("\t") + "\n";
      });
    } else {
      // Markdown
      text = "| # | " + headers.join(" | ") + " |\n";
      text += "|---|" + headers.map(() => "---").join("|") + "|\n";
      rows.forEach((r) => {
        text += `| ${r.rank} | ` + (r.cells || []).join(" | ") + " |\n";
      });
    }

    navigator.clipboard.writeText(text).then(() => {
      toast(`✅ ${format === "tsv" ? "TSV" : "마크다운"} 복사 완료!`);
    }).catch(() => {
      // Fallback
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      toast(`✅ ${format === "tsv" ? "TSV" : "마크다운"} 복사 완료!`);
    });
  }

  window.copyTopicTitle = function (idx) {
    const topic = scanData?.topics?.[idx];
    if (!topic) return;
    navigator.clipboard.writeText(topic.title).then(() => {
      toast("✅ 제목 복사 완료!");
    }).catch(() => {});
  };

  // ═══════════════════════════════════════
  // 실시간 분석
  // ═══════════════════════════════════════
  function initRealtime() {
    $("#btnAnalyze").addEventListener("click", analyzeRealtime);
    $("#btnClearRealtime").addEventListener("click", () => {
      $("#realtimeInput").value = "";
      $("#realtimeResults").innerHTML = "";
    });
    $("#btnSample").addEventListener("click", () => {
      $("#realtimeInput").value = SAMPLE_DATA;
    });
  }

  const SAMPLE_DATA = `"세상에 이런 일이?" 연예인 자산 역전 TOP10
Apr 18, 2026
48시간: 45,231
60분: 1,234

"충격 반전" 은퇴 선언했다가 복귀한 스타 TOP10
Apr 18, 2026
48시간: 32,100
60분: 890

"이 커플 실화?" 나이차 극복 연예인 커플 TOP10
Apr 17, 2026
48시간: 128,000
60분: 456`;

  function analyzeRealtime() {
    const raw = $("#realtimeInput").value.trim();
    if (!raw) { toast("⚠ 데이터를 붙여넣으세요"); return; }

    // 4줄씩 파싱
    const lines = raw.split("\n").filter((l) => l.trim());
    const videos = [];
    for (let i = 0; i < lines.length; i += 4) {
      if (i + 3 >= lines.length) break;
      const title = lines[i].trim();
      const date = lines[i + 1].trim();
      const h48 = parseInt((lines[i + 2] || "").replace(/[^0-9]/g, "")) || 0;
      const m60 = parseInt((lines[i + 3] || "").replace(/[^0-9]/g, "")) || 0;

      videos.push({ title, date, h48, m60, ratio: h48 > 0 ? (m60 / h48 * 48 * 60).toFixed(1) : 0 });
    }

    if (!videos.length) { toast("⚠ 파싱 실패. 형식을 확인하세요"); return; }

    // 60분 기준 정렬
    videos.sort((a, b) => b.m60 - a.m60);

    let html = `<div style="margin-top:20px;">
      <h3 style="margin-bottom:12px;">⚡ 분석 결과 (${videos.length}개 영상)</h3>`;

    videos.forEach((v, i) => {
      const isHot = v.m60 >= 500;
      const color = isHot ? "var(--green)" : "var(--text)";
      const badge = isHot ? "🔥 급상승" : v.m60 >= 200 ? "📈 양호" : "📊 보통";
      html += `
        <div style="padding:10px 14px;background:var(--bg-card);border-radius:6px;margin-bottom:6px;border-left:3px solid ${color};">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:0.88rem;font-weight:600;">${escHtml(v.title)}</span>
            <span style="font-size:0.72rem;color:${color};">${badge}</span>
          </div>
          <div style="font-size:0.78rem;color:var(--text-dim);margin-top:4px;">
            60분: <strong>${numberFormat(v.m60)}</strong> · 48시간: ${numberFormat(v.h48)} · ${v.date}
          </div>
        </div>`;
    });

    // 교차 추천
    if (scanData?.topics?.length) {
      const hotAngles = videos.filter((v) => v.m60 >= 200).map((v) => {
        const words = v.title.match(/[가-힣]{2,}/g) || [];
        return words;
      }).flat();

      if (hotAngles.length) {
        html += `<h3 style="margin:20px 0 12px;">🎯 교차 추천</h3>
          <p style="font-size:0.82rem;color:var(--text-dim);margin-bottom:10px;">
            현재 잘 되는 영상 앵글 + 네이버 트렌드 매칭
          </p>`;

        const matched = scanData.topics.filter((t) => {
          const tWords = (t.title + " " + (t.angle || "")).match(/[가-힣]{2,}/g) || [];
          return hotAngles.some((w) => tWords.includes(w));
        });

        if (matched.length) {
          matched.forEach((t) => {
            html += `<div style="padding:10px;background:var(--accent-bg);border-radius:6px;margin-bottom:6px;">
              <span style="font-size:0.88rem;font-weight:600;color:var(--accent);">🎯 ${escHtml(t.title)}</span>
              <div style="font-size:0.78rem;color:var(--text-dim);margin-top:4px;">${escHtml(t.angle || '')}</div>
            </div>`;
          });
        } else {
          html += `<div style="color:var(--text-muted);font-size:0.85rem;">직접 교차되는 주제는 없지만, 비슷한 앵글의 AI 추천 주제를 확인하세요.</div>`;
        }
      }
    }

    html += `</div>`;
    $("#realtimeResults").innerHTML = html;
  }

  // ═══════════════════════════════════════
  // 히스토리
  // ═══════════════════════════════════════
  async function loadHistory() {
    try {
      const r = await fetch("data/scan_log.json?t=" + Date.now());
      if (!r.ok) throw new Error();
      const logs = await r.json();
      const container = $("#historyList");
      if (!logs.length) {
        container.innerHTML = `<div class="loading-placeholder">히스토리 없음</div>`;
        return;
      }
      container.innerHTML = logs.map((log) => {
        const aiTag = log.ai ? `<span class="history-ai">🤖 AI</span>` : "";
        return `
          <div class="history-item">
            <span class="history-time">${escHtml(log.time)}</span>
            <span class="history-stats">기사 ${log.articles}개 · 주제 ${log.topics}개 ${aiTag}</span>
          </div>`;
      }).join("");
    } catch {
      $("#historyList").innerHTML = `<div class="loading-placeholder">히스토리 없음</div>`;
    }
  }

  // ═══════════════════════════════════════
  // 설정
  // ═══════════════════════════════════════
  function initSettings() {
    const saved = localStorage.getItem("gemini_api_key");
    if (saved) {
      $("#apiKeyInput").value = saved;
      $("#apiKeyStatus").innerHTML = `<span style="color:var(--green);">✅ API 키 저장됨</span>`;
    }

    $("#btnSaveKey").addEventListener("click", () => {
      const key = $("#apiKeyInput").value.trim();
      if (key) {
        localStorage.setItem("gemini_api_key", key);
        $("#apiKeyStatus").innerHTML = `<span style="color:var(--green);">✅ 저장 완료!</span>`;
        toast("✅ API 키 저장됨");
      }
    });

    $("#btnToggleKey").addEventListener("click", () => {
      const input = $("#apiKeyInput");
      input.type = input.type === "password" ? "text" : "password";
    });
  }

  // ═══════════════════════════════════════
  // Helpers
  // ═══════════════════════════════════════
  function escHtml(s) {
    if (!s) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function truncate(s, n) {
    if (!s) return "";
    return s.length > n ? s.slice(0, n) + "…" : s;
  }
  function numberFormat(n) {
    return (n || 0).toLocaleString("ko-KR");
  }

  // Toast
  let toastTimer;
  function toast(msg) {
    let el = $(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2500);
  }
})();
