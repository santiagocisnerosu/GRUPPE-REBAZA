"use strict";
const AGENT_ID = "";
const base = new URL(document.currentScript.dataset.base, location.href);
const $ = (id) => document.getElementById(id);
const audio = $("audio"), rows = $("rows"), seek = $("seek"), card = $("source-card");
const roles = { mara: "Rates & FX", jordan: "Tech investor", priya: "UK retailer" };
const queries = new URLSearchParams(location.search);
const present = queries.get("present") === "1";
document.body.classList.toggle("present", present);
const records = new Map();
let data, mediaRequest, cardAnchor, closeTimer, wordFrame;
let active = -1, currentChapter = -1, chapters = [], wordKey = "", citations = [];
let activeWords = [], audioUrl;

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text != null) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function icon(name) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS(n.namespaceURI, "use");
  use.setAttribute("href", "#ico-" + name);
  n.setAttribute("class", "icon");
  n.setAttribute("aria-hidden", "true");
  n.append(use);
  return n;
}
function link(label, url, cls) {
  let dest;
  try {
    dest = new URL(url);
  } catch {
    return el("span", label, cls);
  }
  if (!["https:", "http:"].includes(dest.protocol)) return el("span", label, cls);
  const a = el("a", label, cls);
  a.href = dest.href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}
async function json(relative) {
  const response = await fetch(new URL(relative, base));
  if (!response.ok) throw Error("Couldn't load " + relative);
  return response.json();
}
function clock(s) {
  s = Math.max(0, Math.floor(s || 0));
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
}
function runtime() {
  return Number.isFinite(audio.duration) ? audio.duration : data?.sentences.at(-1)?.end || 0;
}
function status(message) {
  $("status").textContent = message;
  $("status").hidden = !message;
}
function meter() {
  const { figures_verified: verified, figures_total: total } = data;
  const ratio = verified + "/" + total;
  $("ratio").textContent = $("trust-ratio").textContent = ratio;
  $("invented").textContent = total - verified + " invented";
}
function makeProfile(id, role) {
  const b = el("button", null, "profile");
  b.dataset.listener = id;
  b.setAttribute("aria-pressed", "false");
  b.append(el("span", id, "profile-name"), el("span", role, "role"));
  $("profiles").append(b);
  const record = json(id + "/transcript.json").then((briefing) => {
    b.title = clock(briefing.sentences.at(-1)?.end) + " · " + briefing.figures_total + " figures";
    b.setAttribute("aria-description", b.title);
    return briefing;
  }).catch(() => {
    b.title = "Briefing unavailable";
    return null;
  });
  records.set(id, record);
  b.onclick = () => {
    if (b.getAttribute("aria-pressed") === "true" && data) return;
    const url = new URL(location.href);
    url.searchParams.set("listener", id);
    history.replaceState(null, "", url);
    selectListener(id);
  };
}
function hideCard() {
  clearTimeout(closeTimer);
  card.hidden = true;
  cardAnchor = null;
}
function scheduleHide() {
  clearTimeout(closeTimer);
  closeTimer = setTimeout(hideCard, 220);
}
function showCard(button, item) {
  clearTimeout(closeTimer);
  cardAnchor = button;
  const owner = button.closest("dialog") || document.body;
  if (card.parentElement !== owner) owner.append(card);
  const title = link(item.headline, item.link);
  title.append(" ", icon("link"));
  card.replaceChildren(el("strong", item.outlet), title);
  card.hidden = false;
  const r = button.getBoundingClientRect(),
    w = card.offsetWidth,
    h = card.offsetHeight;
  card.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + "px";
  card.style.top =
    (r.top > h + 8 ? r.top - h - 5 : Math.min(innerHeight - h - 8, r.bottom + 5)) + "px";
}
card.onpointerenter = () => clearTimeout(closeTimer);
card.onpointerleave = scheduleHide;
card.onfocusin = () => clearTimeout(closeTimer);
card.onfocusout = scheduleHide;
document.addEventListener("pointerdown", (e) => {
  if (!card.contains(e.target) && !e.target.closest(".fig")) hideCard();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && cardAnchor) {
    const b = cardAnchor;
    hideCard();
    b.focus();
    hideCard();
  }
});
window.addEventListener("scroll", hideCard, { capture: true, passive: true });
function figureButton(item) {
  const b = el("button", null, "fig");
  b.setAttribute("aria-label", item.figure + ", verified by " + item.outlet + ". Show source");
  b.setAttribute("aria-controls", "source-card");
  const open = () => showCard(b, item);
  b.onpointerenter = (e) => {
    if (e.pointerType === "mouse") open();
  };
  b.onpointerleave = scheduleHide;
  b.onfocus = open;
  b.onblur = scheduleHide;
  b.onclick = (e) => {
    e.stopPropagation();
    open();
  };
  b.onkeydown = (e) => {
    if (e.key === "Tab" && !e.shiftKey && cardAnchor === b) {
      e.preventDefault();
      card.querySelector("a")?.focus();
    }
  };
  return b;
}
// Join the audited receipt to this sentence by source and exact printed value.
function sentenceCitations(sentence) {
  const sources = new Set(sentence.sources.map((s) => s.link)), text = sentence.text;
  const hits = [];
  for (const item of data.receipt) {
    if (!sources.has(item.link) || !item.figure) continue;
    for (let from = 0, at; (at = text.indexOf(item.figure, from)) !== -1; from = at + item.figure.length) {
      const end = at + item.figure.length;
      if (/[\w$£€¥]/.test(text[at - 1] || "") || /^[\w%]|^[.,]\d/.test(text.slice(end))) continue;
      hits.push({ at, end, item });
    }
  }
  hits.sort((a, b) => a.at - b.at || b.end - a.end);
  const matches = [];
  for (const hit of hits) {
    if (hit.at >= (matches.at(-1)?.end ?? 0)) matches.push(hit);
  }
  return matches;
}
function evidenceText(parent, sentence, hits) {
  const text = sentence.text;
  let wordEnd = 0;
  const words = (sentence.words || []).map(({ w }, index) => {
    const start = text.indexOf(w, wordEnd);
    wordEnd = start + w.length;
    return { start, end: wordEnd, index };
  });
  function appendRange(target, start, end) {
    let cursor = start;
    for (const word of words) {
      if (word.end <= start || word.start >= end) continue;
      const left = Math.max(start, word.start),
        right = Math.min(end, word.end);
      target.append(text.slice(cursor, left));
      const span = el("span", text.slice(left, right), "word");
      span.dataset.word = word.index;
      target.append(span);
      cursor = right;
    }
    target.append(text.slice(cursor, end));
  }
  let pos = 0;
  for (const [index, h] of hits.entries()) {
    appendRange(parent, pos, h.at);
    const button = figureButton(h.item);
    appendRange(button, h.at, h.end);
    button.append(el("sup", "[" + (index + 1) + "]"));
    parent.append(button);
    pos = h.end;
  }
  appendRange(parent, pos, text.length);
}
function jump(t) {
  if (!audio.readyState) return;
  audio.currentTime = t;
  sync();
}
function drawTranscript() {
  active = -1;
  wordKey = "";
  const lines = data.sentences.map((s, index) => {
    const row = el("article", null, "line"),
      body = el("div"),
      p = el("p");
    const time = el("button", clock(s.start), "line-time");
    time.setAttribute("aria-label", "Seek to " + clock(s.start));
    time.onclick = p.onclick = () => jump(s.start);
    evidenceText(p, s, citations[index]);
    body.append(p);
    if (s.sources.length) {
      const cites = el("div", null, "sources");
      for (const source of s.sources) {
        const label = source.outlet + " · " + source.headline;
        const a = link("", source.link, "chip");
        a.title = label;
        a.append(icon("link"), el("span", label));
        cites.append(a);
      }
      body.append(cites);
    }
    row.append(time, body);
    return row;
  });
  rows.replaceChildren(...lines);
  rows.scrollTop = 0;
}
function drawChapters() {
  chapters = [];
  currentChapter = -1;
  for (const s of data.sentences) {
    if (s.story !== chapters.at(-1)?.title) chapters.push({ title: s.story, start: s.start });
  }
  $("chapter-count").textContent = "";
  $("chapters").replaceChildren(
    ...chapters.map((c) => {
      const li = el("li"),
        b = el("button");
      b.append(el("span", clock(c.start), "chapter-time"), el("span", c.title));
      b.onclick = () => {
        jump(c.start);
        toggleChapters(false);
        $("chapter-toggle").focus();
      };
      li.append(b);
      return li;
    }),
  );
}
function toggleChapters(open) {
  $("chapters").hidden = !open;
  $("chapter-toggle").setAttribute("aria-expanded", String(open));
}
$("chapter-toggle").onclick = () => toggleChapters($("chapters").hidden);
function drawMarkers() {
  const duration = runtime();
  $("markers").replaceChildren(
    ...chapters.slice(1).map((c) => {
      const tick = el("span", null, "marker");
      tick.style.left = (100 * c.start) / duration + "%";
      return tick;
    }),
  );
}
function drawEvidence(index) {
  const sentence = data.sentences[index], panel = $("evidence");
  const preview = !sentence.sources.length;
  const cited = preview ? data.sentences.slice(index + 1).find((line) => line.sources.length) : sentence;
  panel.classList.toggle("preview", preview);
  if (!cited) {
    panel.replaceChildren(el("p", "No further sources in this briefing.", "empty-evidence"));
    return;
  }
  const matches = preview ? [] : citations[index];
  const items = [];
  if (preview) items.push(el("p", "Up next", "up-next"));
  const matchedLinks = new Set(matches.map((m) => m.item.link));
  const entries = [
    ...matches.map((m) => m.item),
    ...cited.sources.filter((s) => !matchedLinks.has(s.link)),
  ];
  entries.forEach((source, index) => {
    const row = el("div", null, "source-item");
    const details = el("div"), meta = el("div", null, "source-meta"), outlet = el("div", null, "outlet");
    if (source.figure) {
      const value = el("div", source.figure, "source-value");
      value.append(el("span", "✓", "check"));
      meta.append(value);
      outlet.append(el("span", "matched in ", "matched"));
    }
    outlet.append(source.outlet);
    const headline = link(source.headline, source.link, "headline");
    headline.append(" ", icon("link"));
    meta.append(outlet);
    details.append(meta, headline);
    if (!preview) row.append(el("span", "[" + (index + 1) + "]", "ref"));
    row.append(details);
    items.push(row);
  });
  panel.replaceChildren(...items);
}

function showSentence(index) {
  hideCard();
  const sentence = data.sentences[index];
  const old = rows.children[active];
  old?.querySelectorAll(".speaking, .said").forEach((n) => n.classList.remove("speaking", "said"));
  old?.classList.remove("active");
  old?.removeAttribute("aria-current");
  active = index;
  const row = rows.children[index];
  row.classList.add("active");
  row.setAttribute("aria-current", "true");
  if ($("transcript").open) row.scrollIntoView({ block: "nearest" });
  const lyric = $("lyric");
  lyric.replaceChildren();
  evidenceText(lyric, sentence, citations[index]);
  drawEvidence(index);
  activeWords = [...lyric.querySelectorAll(".word"), ...row.querySelectorAll(".word")];
  wordKey = "";
  for (const [id, offset] of [["previous", -1], ["next", 1]]) {
    const text = data.sentences[index + offset]?.text;
    $(id).textContent = text || "";
    $(id + "-row").hidden = !text;
  }
}
function syncWord() {
  if (!data || !data.sentences.length) return;
  const time = audio.currentTime;
  const index = Math.max(0, data.sentences.findLastIndex((s) => s.start <= time));
  if (active !== index) showSentence(index);
  const words = data.sentences[index].words || [];
  const last = words.findLastIndex((w) => w.start <= time);
  const speaking = last >= 0 && time < words[last].end ? last : -1;
  const key = last + "/" + speaking;
  if (key !== wordKey) {
    wordKey = key;
    for (const span of activeWords) {
      const n = Number(span.dataset.word);
      span.classList.toggle("speaking", n === speaking);
      span.classList.toggle("said", n <= last && n !== speaking);
    }
  }
  const chapter = Math.max(0, chapters.findLastIndex((c) => c.start <= time));
  if (chapter !== currentChapter && chapters[chapter]) {
    currentChapter = chapter;
    $("current").textContent = chapters[chapter].title;
    $("chapter-count").textContent = (chapter + 1) + "/" + chapters.length;
    [...$("chapters").querySelectorAll("button")].forEach((b, i) => b.setAttribute("aria-current", String(i === chapter)));
  }
}
function animateWord() {
  syncWord();
  if (!audio.paused && !audio.ended) wordFrame = requestAnimationFrame(animateWord);
}
function sync() {
  if (!data) return;
  syncWord();
  const time = audio.currentTime, end = runtime();
  $("elapsed").textContent = clock(time);
  $("duration").textContent = clock(end);
  seek.max = end;
  seek.value = time;
  seek.setAttribute("aria-valuetext", clock(time) + " of " + clock(end));
  $("track").style.setProperty("--progress", 100 * time / (end || 1) + "%");
}
function heardInstead(caught) {
  return data.receipt.find((item) => {
    const at = caught.sentence.indexOf(item.figure);
    if (at < 0 || item.figure === caught.figure) return false;
    const context = caught.sentence.slice(at).split(/\s+/).slice(0, 6);
    return (
      context.length >= 4 &&
      data.sentences.some(
        (s) =>
          s.text.includes(context.join(" ")) && s.sources.some((src) => src.link === item.link),
      )
    );
  });
}
function drawTrust() {
  const list = $("trust-list");
  list.replaceChildren();
  function note(title) {
    const li = el("li"), detail = el("span", null, "trust-detail");
    li.append(el("strong", title), detail);
    list.append(li);
    return detail;
  }
  const blocked = data.caught.filter((c) => c.kind === "invented");
  if (blocked.length) {
    const best = blocked.find((c) => heardInstead(c)) || blocked[0];
    const used = heardInstead(best);
    const detail = note("Blocked before broadcast");
    detail.append("The draft said ", el("del", best.figure), ". The source did not support that figure.");
    if (used) detail.append(" In the audio: ", link(used.figure + " (" + used.outlet + ")", used.link), ".");
  } else {
    note("Every spoken figure matched its source.");
  }
  const conflict = data.conflicts.find((c) => ["a", "b"].includes(c.used));
  if (conflict) {
    const detail = note("Where sources differ");
    detail.append(conflict.measure + ": ");
    for (const side of ["a", "b"]) {
      if (side === "b") detail.append(" / ");
      detail.append(link(conflict["value_" + side] + " · " + conflict["outlet_" + side], conflict["link_" + side]));
    }
    detail.append(". The briefing uses " + conflict["outlet_" + conflict.used] + ".");
  }
}
function drawAudit() {
  drawTrust();
  const kinds = ["invented", "copied", "miscited"];
  const labels = {
    invented: "Unverified number blocked",
    copied: "Licensed text blocked",
    miscited: "Citation fixed",
  };
  $("caught-count").textContent = data.caught.length;
  const caught = [...data.caught]
    .sort((a, b) => kinds.indexOf(a.kind) - kinds.indexOf(b.kind))
    .map((c) => {
      const row = el("div", null, "audit-row"),
        p = el("p", null, "diff"),
        at = c.figure ? c.sentence.indexOf(c.figure) : -1;
      if (at >= 0)
        p.append(
          c.sentence.slice(0, at),
          el("del", c.figure),
          c.sentence.slice(at + c.figure.length),
        );
      else p.textContent = c.sentence || "Licensed wording withheld.";
      row.append(el("h3", labels[c.kind]), p);
      if (c.kind === "invented") {
        const replacement = heardInstead(c);
        if (replacement)
          row.append(
            link("Heard in the briefing · " + replacement.figure, replacement.link, "used-link"),
          );
      }
      return row;
    });
  $("caught").replaceChildren(...(caught.length ? caught : [el("p", "No issues caught.")]));
  $("conflict-count").textContent = data.conflicts.length;
  const conflicts = data.conflicts.map((c) => {
    const row = el("div", null, "audit-row"),
      compare = el("div", null, "compare");
    for (const side of ["a", "b"]) {
      const used = c.used === side,
        reading = el("div", null, "reading" + (used ? " used" : ""));
      reading.append(
        el("strong", c["value_" + side]),
        link(c["outlet_" + side], c["link_" + side]),
      );
      if (used) reading.append(el("div", "✓ Used in audio", "small"));
      compare.append(reading);
    }
    const reason = c.used
      ? "The script cites this source. Story rank, then source order, determines which reading goes to the writer."
      : "Neither reading was cited in this briefing.";
    row.append(el("h3", c.measure), compare, el("p", reason, "explain"));
    return row;
  });
  $("conflicts").replaceChildren(
    ...(conflicts.length ? conflicts : [el("p", "No conflicting figures reported.")]),
  );
}
function drawReceipt() {
  $("ticket-meta").textContent = data.name + " / News of " + data.date;
  $("ticket-lines").replaceChildren(
    ...data.receipt.map((r) => {
      const li = el("li"),
        detail = el("div", r.measures),
        a = link(r.outlet, r.link);
      a.title = r.headline;
      detail.append(a);
      li.append(el("strong", r.figure), detail, el("span", "✓", "check"));
      return li;
    }),
  );
  const totals = {
    FIGURES: data.figures_total,
    VERIFIED: data.figures_verified,
    INVENTED: data.figures_total - data.figures_verified,
    SOURCES: data.sources_total,
  };
  $("totals").replaceChildren(
    ...Object.entries(totals).flatMap(([k, v]) => [el("span", k), el("strong", v)]),
  );
}
function hasMarketConsequence(text) {
  const market = /\b(?:markets?|dollar|sterling|yen|euro|bonds?|gilts?|yields?|shares?|equities|gold|bullion|crude|brent)\b/i;
  const effect = /\b(?:support(?:s|ed|ing)?|pressure|headwinds?|tailwinds?|weigh(?:s|ed|ing)? on|strengthen(?:s|ed|ing)?|weaken(?:s|ed|ing)?|firmer|(?:could|may|would|might) (?:rise|fall|gain|drop|lift|keep))\b/i;
  return market.test(text) && effect.test(text);
}

function listenerMeaning(briefing, fact) {
  if (!briefing) return null;
  const { listener, sentences } = briefing;
  const quote = fact.listeners[listener].sentence;
  const anchor = sentences.findIndex((s) => s.text === quote && s.sources.some((src) => src.link === fact.link));
  if (anchor < 0) return null;
  const story = sentences[anchor].story;
  let first = anchor, end = anchor + 1;
  while (first > 0 && sentences[first - 1].story === story) first--;
  while (end < sentences.length && sentences[end].story === story) end++;
  const lines = sentences.slice(first, end).filter((s) => s.sources.length);
  let line;
  if (listener === "priya") {
    line = lines.find((s) => /^For your business\b/i.test(s.text));
  } else {
    // Mara's editorial rule puts the market consequence at the end of the story.
    line = lines.findLast((s) => hasMarketConsequence(s.text))
      || sentences.slice(anchor + 1, end).find((s) => s.sources.length);
  }
  if (!line) return null;
  // If the quote itself contains the implication, pull out its spoken second clause.
  const tail = line.text === quote && line.text.match(/, and (.+)$/i)?.[1];
  const text = tail && hasMarketConsequence(tail) ? "… " + tail : line.text;
  return { text, sources: line.sources };
}

async function extras() {
  const [shared, costs] = await Promise.allSettled([
    json("shared_facts.json"),
    json("costs.json"),
  ]);
  if (shared.status === "fulfilled") {
    const facts = shared.value.filter((f) => f.listeners.mara && f.listeners.priya);
    if (facts.length) {
      const [mara, priya] = await Promise.all([records.get("mara"), records.get("priya")]);
      const briefings = { mara, priya };
      let index = 0;
      function showFact() {
        const fact = facts[index];
        const article = el("article", null, "fact"), metric = el("div");
        const title = el("h3");
        title.append(link(fact.measure, fact.link));
        metric.append(el("span", fact.value, "metric"), title);
        article.append(metric);
        for (const id of ["mara", "priya"]) {
          const angle = el("figure", null, "angle"), caption = el("figcaption", id);
          caption.append(el("span", " / " + roles[id]));
          const quote = el("blockquote"), { sentence, spoken_value } = fact.listeners[id];
          const at = sentence.indexOf(spoken_value);
          if (at >= 0) quote.append("“" + sentence.slice(0, at), el("mark", spoken_value), sentence.slice(at + spoken_value.length) + "”");
          else quote.textContent = "“" + sentence + "”";
          angle.append(caption, quote);
          const meaning = listenerMeaning(briefings[id], fact);
          if (meaning) {
            const detail = el("div", null, "angle-meaning");
            detail.append(el("h4", "What it means for " + briefings[id].name), el("p", meaning.text));
            const sources = el("div", null, "meaning-sources");
            for (const source of meaning.sources) {
              const a = link(source.outlet, source.link);
              a.title = source.headline;
              sources.append(a);
            }
            detail.append(sources);
            angle.append(detail);
          }
          article.append(angle);
        }
        $("facts").replaceChildren(article);
        $("fact-count").textContent = (index + 1) + " / " + facts.length;
        $("fact-prev").disabled = index === 0;
        $("fact-next").disabled = index === facts.length - 1;
      }
      $("fact-prev").onclick = () => { index--; showFact(); };
      $("fact-next").onclick = () => { index++; showFact(); };
      showFact();
      $("shared").hidden = false;
    }
  }
  if (costs.status === "fulfilled") {
    const report = costs.value,
      monthly = report.scenarios.find((s) => s.scenario.startsWith("Per listener per month"));
    if (!monthly || !Number.isFinite(monthly.with_segment_cache)) return;
    const fmt = new Intl.NumberFormat("en-US", { style: "currency", currency: report.currency });
    const price = fmt.format(monthly.with_segment_cache);
    const headline =
      report.currency === "USD" && monthly.with_segment_cache < 1 ? "Under $1" : price;
    $("cost").textContent = headline + " per listener per month · costs measured, not estimated";
    $("cost-detail").textContent =
      price +
      " projected from recorded API usage with shared audio at " +
      report.assumptions.listeners.toLocaleString("en-US") +
      " listeners.";
    $("foot").hidden = false;
  }
}
function updatePlay() {
  const paused = audio.paused;
  $("play").replaceChildren(icon(paused ? "play" : "pause"));
  $("play").setAttribute("aria-label", paused ? "Play briefing" : "Pause briefing");
}
async function selectListener(id) {
  mediaRequest?.abort();
  mediaRequest = new AbortController();
  const signal = mediaRequest.signal;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = null;
  data = null;
  hideCard();
  toggleChapters(false);
  $("play").disabled = true;
  $("briefing").hidden = true;
  $("ratio").textContent = "–/–";
  $("invented").textContent = "– invented";
  document
    .querySelectorAll(".profile")
    .forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.listener === id)));
  const tab = document.querySelector('.profile[aria-pressed="true"]');
  const profiles = $("profiles");
  if (tab && profiles.clientWidth) profiles.scrollLeft = tab.offsetLeft - profiles.offsetLeft - (profiles.clientWidth - tab.offsetWidth) / 2;
  status("Loading briefing…");
  try {
    const record = await records.get(id);
    if (signal.aborted) return;
    if (!record) throw Error("Transcript unavailable");
    data = record;
    citations = data.sentences.map(sentenceCitations);
    drawTranscript();
    drawChapters();
    drawAudit();
    drawReceipt();
    meter();
    const date = $("edition");
    // The morning edition follows the transcript's news day.
    const morning = new Date(data.date + "T00:00:00Z");
    morning.setUTCDate(morning.getUTCDate() + 1);
    date.dateTime = morning.toISOString().slice(0, 10);
    date.textContent = new Intl.DateTimeFormat("en-GB", {
      weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
    }).format(morning).replace(",", "");
    $("deck-title").textContent = data.name + "’s briefing";
    $("briefing").hidden = false;
    sync();
    drawMarkers();
    updatePlay();
    const response = await fetch(new URL(id + "/" + data.audio, base), { signal });
    if (!response.ok) throw Error("Audio unavailable");
    const blob = await response.blob();
    if (signal.aborted) return;
    audioUrl = URL.createObjectURL(blob);
    audio.src = audioUrl;
    status("");
  } catch {
    if (!signal.aborted)
      status("This briefing could not be loaded. Check the local server or refresh the page.");
  }
}
audio.onloadedmetadata = () => {
  if (!data || audio.currentSrc !== audioUrl) return;
  $("play").disabled = false;
  drawMarkers();
  sync();
};
audio.onerror = () => {
  if (audioUrl && audio.error) {
    status("Audio could not be played.");
    $("play").disabled = true;
  }
};
audio.onplay = audio.onpause = () => {
  updatePlay();
  cancelAnimationFrame(wordFrame);
  animateWord();
};
audio.ontimeupdate = audio.onseeked = sync;
audio.onended = () => {
  updatePlay();
  sync();
};
seek.oninput = () => jump(Number(seek.value));
$("play").onclick = async () => {
  if (!audio.paused) {
    audio.pause();
    return;
  }
  try {
    await audio.play();
  } catch {
    status("Playback could not start. Try Play again.");
  }
};
for (const [buttonId, dialogId] of [["open-audit", "audit-dialog"], ["receipt-btn", "receipt"], ["transcript-btn", "transcript"]]) {
  const dialog = $(dialogId);
  $(buttonId).onclick = () => {
    hideCard();
    dialog.showModal();
    if (dialogId === "transcript") rows.children[active]?.scrollIntoView({ block: "nearest" });
  };
  dialog.addEventListener("close", hideCard);
  dialog.onclick = (e) => {
    if (e.target !== dialog) return;
    const r = dialog.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close();
  };
}
document.addEventListener("pointerdown", (e) => {
  if (!e.target.closest(".chapter-picker")) toggleChapters(false);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("chapters").hidden) {
    toggleChapters(false);
    $("chapter-toggle").focus();
  }
});
Object.entries(roles).forEach(([id, role]) => makeProfile(id, role));
selectListener(Object.hasOwn(roles, queries.get("listener")) ? queries.get("listener") : "mara");
extras();
if (AGENT_ID.trim()) {
  const widget = el("elevenlabs-convai");
  widget.setAttribute("agent-id", AGENT_ID.trim());
  const embed = el("script");
  embed.src = "https://unpkg.com/@elevenlabs/convai-widget-embed";
  embed.async = true;
  document.body.append(widget, embed);
}
