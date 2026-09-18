/**
 * Autonomous LinkedIn AI Agent — Masterclass Explainer Dashboard
 * Interactive Tab Management, Mermaid Diagram Rendering & Statistical AI Detection Engine
 */

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initMermaid();
  initAccordions();
  initPlayground();
});

/* ==============================================================================
   1. Tab Navigation Management
   ============================================================================== */
function initTabs() {
  const navItems = document.querySelectorAll(".nav-item");
  const tabPanels = document.querySelectorAll(".tab-panel");

  function switchTab(targetId) {
    navItems.forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-tab") === targetId);
    });

    tabPanels.forEach((panel) => {
      panel.classList.toggle("active", panel.id === targetId);
    });

    // Re-render Mermaid diagrams if newly revealed
    if (window.mermaid) {
      setTimeout(() => {
        try {
          window.mermaid.run();
        } catch (e) {
          console.warn("Mermaid re-render:", e);
        }
      }, 50);
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  navItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      switchTab(targetId);
      history.replaceState(null, "", `#${targetId}`);
    });
  });

  // Handle URL hash on load
  const hash = window.location.hash.replace("#", "");
  if (hash && document.getElementById(hash)) {
    switchTab(hash);
  }
}

/* ==============================================================================
   2. Mermaid.js Diagram Initialization
   ============================================================================== */
function initMermaid() {
  if (typeof mermaid !== "undefined") {
    mermaid.initialize({
      startOnLoad: true,
      theme: "dark",
      themeVariables: {
        darkMode: true,
        background: "#0d121d",
        primaryColor: "#6366f1",
        primaryTextColor: "#f8fafc",
        primaryBorderColor: "rgba(99, 102, 241, 0.4)",
        lineColor: "#8b5cf6",
        secondaryColor: "#1e293b",
        tertiaryColor: "#0f172a",
      },
      flowchart: {
        curve: "basis",
        padding: 20,
        nodeSpacing: 45,
        rankSpacing: 45,
      },
    });
  }
}

/* ==============================================================================
   3. Accordion Management (Interview Questions & Code Snippets)
   ============================================================================== */
function initAccordions() {
  const accordions = document.querySelectorAll(".faq-header");
  accordions.forEach((header) => {
    header.addEventListener("click", () => {
      const card = header.closest(".faq-card");
      const wasOpen = card.classList.contains("open");

      // Optional: close other open accordions in the same group
      // card.parentElement.querySelectorAll('.faq-card.open').forEach(c => c.classList.remove('open'));

      card.classList.toggle("open", !wasOpen);
    });
  });
}

/* ==============================================================================
   4. Statistical AI Detection & Burstiness Playground
   ============================================================================== */
const AI_HALLMARK_PHRASES = [
  /\bthe benefits are (?:pretty )?straightforward\b/i,
  /\bof course,? there are (?:some )?trade-offs\b/i,
  /\bcurious to hear (?:how|your|what)\b/i,
  /\bit is worth noting that\b/i,
  /\bit's worth noting that\b/i,
  /\bin today's fast-paced\b/i,
  /\bin today's world\b/i,
  /\bin the fast-paced world\b/i,
  /\bwhen it comes to\b/i,
  /\bharness(?:ing)? the power\b/i,
  /\bgame changer\b/i,
  /\bdive deep\b/i,
  /\bdelve into\b/i,
  /\bdelving into\b/i,
  /\ba testament to\b/i,
  /\bbeacon of\b/i,
  /\btapestry of\b/i,
  /\brevolutioniz(?:e|ing|ed)\b/i,
  /\bpivotal role\b/i,
  /\bcrucial role\b/i,
  /\bmoreover\b/i,
  /\bfurthermore\b/i,
  /\bin conclusion\b/i,
  /\bseamlessly integrate\b/i,
  /\bunleash(?:ing)? the\b/i,
  /\bby leveraging\b/i,
  /\bleveraging the power\b/i,
  /\bnavigat(?:e|ing) the complexities\b/i,
  /\bever-evolving\b/i,
  /\bstands as a testament\b/i,
  /\ba double-edged sword\b/i,
  /\ba holistic approach\b/i,
  /\bfoster(?:ing)? innovation\b/i,
  /\bpush(?:ing)? the boundaries\b/i,
  /\bat its core\b/i,
  /\bin essence\b/i,
];

function splitSentences(text) {
  let clean = text.replace(/https?:\/\/\S+/g, "");
  clean = clean.replace(/#\w+/g, "");
  clean = clean.replace(/^[ \t]*[-*•]\s*/gm, "");
  const raw = clean.split(/(?:[.!?]+(?:\s+|\n+|$)|[\r\n]+)/);
  return raw.map((s) => s.trim()).filter((s) => s.split(/\s+/).length >= 2);
}

function calculateBurstiness(sentences) {
  if (sentences.length < 2) return 5.0;
  const lengths = sentences.map((s) => s.split(/\s+/).length);
  const mean = lengths.reduce((a, b) => a + b, 0) / lengths.length;
  const variance =
    lengths.reduce((acc, l) => acc + Math.pow(l - mean, 2), 0) / (lengths.length - 1);
  return Math.round(Math.sqrt(variance) * 100) / 100;
}

function scanHallmarks(text) {
  const matches = [];
  AI_HALLMARK_PHRASES.forEach((pattern) => {
    const found = text.match(pattern);
    if (found) {
      matches.push(found[0].toLowerCase());
    }
  });
  return [...new Set(matches)];
}

function analyzeAIText(text) {
  if (!text || text.trim().split(/\s+/).length < 10) {
    return {
      aiScore: 0,
      humanScore: 100,
      status: "Likely Human",
      badge: "✅",
      burstiness: 0.0,
      flagged: [],
      sentenceCount: 0,
    };
  }

  const sentences = splitSentences(text);
  const burstiness = calculateBurstiness(sentences);
  const flagged = scanHallmarks(text);

  let baseScore = 15.0;
  if (burstiness < 2.5) {
    baseScore += 40.0;
  } else if (burstiness < 3.8) {
    baseScore += 20.0;
  } else if (burstiness < 5.0) {
    baseScore += 0.0;
  } else if (burstiness >= 7.0) {
    baseScore -= 15.0;
  } else if (burstiness >= 5.0) {
    baseScore -= 5.0;
  }

  const hallmarkPenalty = flagged.length * 22.0;
  let totalScore = baseScore + hallmarkPenalty;

  if (/\b(?:containers|docker|microvms|agents) are (?:lightweight|a platform|designed to)\b/i.test(text)) {
    totalScore += 15.0;
  }

  const finalAiScore = Math.max(2, Math.min(99, Math.round(totalScore)));
  const finalHumanScore = 100 - finalAiScore;

  let status = "Likely Human";
  let badge = "✅";
  if (finalAiScore > 55) {
    status = "High AI Signature";
    badge = "🚨";
  } else if (finalAiScore > 25) {
    status = "Moderate AI";
    badge = "⚠️";
  }

  return {
    aiScore: finalAiScore,
    humanScore: finalHumanScore,
    status,
    badge,
    burstiness,
    flagged,
    sentenceCount: sentences.length,
    sentences,
  };
}

function initPlayground() {
  const btnAnalyze = document.getElementById("btn-analyze-text");
  const inputEl = document.getElementById("playground-input-text");
  const btnLoadRobotic = document.getElementById("btn-load-robotic");
  const btnLoadHuman = document.getElementById("btn-load-human");

  if (!btnAnalyze || !inputEl) return;

  function runAnalysis() {
    const text = inputEl.value;
    const res = analyzeAIText(text);

    document.getElementById("res-ai-score").textContent = `${res.aiScore}%`;
    document.getElementById("res-human-score").textContent = `${res.humanScore}%`;
    document.getElementById("res-burstiness").textContent = res.burstiness.toFixed(2);
    document.getElementById("res-status").textContent = `${res.badge} ${res.status}`;

    const flaggedContainer = document.getElementById("res-flagged-phrases");
    if (res.flagged.length > 0) {
      flaggedContainer.innerHTML = `⚠️ <strong>Flagged AI Tropes:</strong> ${res.flagged
        .map((p) => `<span class="chip amber">"${p}"</span>`)
        .join(" ")}`;
    } else {
      flaggedContainer.innerHTML = `<span style="color: #34d399;">✅ Zero formulaic AI hallmark phrases detected.</span>`;
    }

    // Breakdown breakdown list
    const breakdownEl = document.getElementById("sentence-breakdown-list");
    if (breakdownEl && res.sentences) {
      breakdownEl.innerHTML = res.sentences
        .map(
          (s, i) =>
            `<div style="display:flex; justify-content:space-between; padding: 6px 12px; background: rgba(255,255,255,0.02); border-radius: 6px; margin-bottom: 4px; font-size: 13px;">
              <span style="color: #cbd5e1;">${i + 1}. "${s.length > 65 ? s.substring(0, 65) + '...' : s}"</span>
              <span style="color: #a5b4fc; font-weight: 600; font-family: var(--font-mono);">${s.split(/\s+/).length} words</span>
            </div>`
        )
        .join("");
    }
  }

  btnAnalyze.addEventListener("click", runAnalysis);

  if (btnLoadRobotic) {
    btnLoadRobotic.addEventListener("click", () => {
      inputEl.value =
        "The benefits are pretty straightforward: isolation and security. Using Docker for containerization, each AI agent runs in its own environment. In today's fast-paced world, containers are lightweight units that can be scaled up or down. Of course, there are some trade-offs when it comes to memory overhead. Curious to hear your thoughts!";
      runAnalysis();
    });
  }

  if (btnLoadHuman) {
    btnLoadHuman.addEventListener("click", () => {
      inputEl.value =
        "If you give an autonomous agent bash access on raw metal, you're one hallucinated rm command away from a postmortem.\n\nDon't do it.\n\nWe run each agent in an ephemeral rootless Docker container with a read-only tmpfs and capped memory cgroups. Network egress is locked down with strict iptables rules. Total silence.\n\nStartup latency added 180ms per task, but the blast radius dropped to zero.\n\nAre you isolating agent execution at the namespace boundary yet?";
      runAnalysis();
    });
  }

  // Initial trigger
  runAnalysis();
}
