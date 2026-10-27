// Job page: wait for the conversion, then show the score and let the user fix its lyrics.
// The MusicXML is edited in place as an XML document; Verovio renders a copy whose
// <note> elements get ids n0, n1, ... so a click on the SVG leads back to the XML note.

const job = location.pathname.split("/")[2];
const $ = id => document.getElementById(id);
const SCALE = 40;

let tk, xml, notes, verses;
let dirty = false;
let current = null;  // {i, before} while the popup is open

const verovioReady = new Promise(resolve => {
  if (verovio.module.calledRun) resolve();
  else verovio.module.onRuntimeInitialized = resolve;
});

// ---- MusicXML helpers

const child = (el, name) => Array.from(el.children).find(c => c.tagName === name);
const isChordTone = n => !!child(n, "chord");
const isSung = n => !child(n, "rest") && !isChordTone(n);
const voiceOf = n => child(n, "voice")?.textContent || "1";
const lyricNumber = l => l.getAttribute("number") || "1";
const lyricOf = (n, v) => Array.from(n.children).find(c => c.tagName === "lyric" && lyricNumber(c) === v);
const hyphenAfter = l => ["begin", "middle"].includes(child(l, "syllabic")?.textContent);
const syllabic = (fromPrev, toNext) => fromPrev ? (toNext ? "middle" : "end") : (toNext ? "begin" : "single");

// A syllable as the user sees it: its text, with "-" when the word continues.
function shown(l) {
  if (!l) return "";
  const text = Array.from(l.getElementsByTagName("text")).map(t => t.textContent).join("_");
  return text + (hyphenAfter(l) ? "-" : "");
}

// The sung notes of one voice in one part, in score order.
function line(note) {
  const voice = voiceOf(note);
  return Array.from(note.closest("part").getElementsByTagName("note"))
    .filter(n => isSung(n) && voiceOf(n) === voice);
}

function neighbour(note, v, step) {
  const notesOfLine = line(note);
  for (let k = notesOfLine.indexOf(note) + step; k >= 0 && k < notesOfLine.length; k += step) {
    const l = lyricOf(notesOfLine[k], v);
    if (l) return l;
  }
  return null;
}

function setSyllabic(l, value) {
  let s = child(l, "syllabic");
  if (!s) {
    s = xml.createElement("syllabic");
    l.insertBefore(s, l.firstChild);
  }
  s.textContent = value;
}

// Set the lyric of a note for verse v from what the user typed ("" removes it).
function setLyric(note, v, value) {
  value = value.trim();
  const hyphen = value.endsWith("-");
  const text = value.replace(/-+$/, "").trim();
  const prev = neighbour(note, v, -1), next = neighbour(note, v, +1);
  const fromPrev = prev ? hyphenAfter(prev) : false;
  let l = lyricOf(note, v);
  if (!text) {
    if (l) l.remove();
    if (next) setSyllabic(next, syllabic(fromPrev, hyphenAfter(next)));
    return;
  }
  if (!l) {
    l = xml.createElement("lyric");
    l.setAttribute("number", v);
    const after = Array.from(note.children).find(c => ["play", "listen"].includes(c.tagName));
    note.insertBefore(l, after || null);
  }
  for (const c of Array.from(l.children)) if (c.tagName !== "extend") c.remove();
  const t = xml.createElement("text");
  t.textContent = text;
  l.insertBefore(t, l.firstChild);
  setSyllabic(l, syllabic(fromPrev, hyphen));
  if (next) setSyllabic(next, syllabic(hyphen, hyphenAfter(next)));
}

// ---- Rendering

function render() {
  const copy = xml.cloneNode(true);
  Array.from(copy.getElementsByTagName("note")).forEach((n, i) => n.setAttribute("id", "n" + i));
  tk.setOptions({
    scale: SCALE,
    pageWidth: Math.round($("score").clientWidth * 100 / SCALE),
    adjustPageHeight: true,
    breaks: "auto",
    header: "none",
    footer: "none",
  });
  tk.loadData(new XMLSerializer().serializeToString(copy));
  let svg = "";
  for (let p = 1; p <= tk.getPageCount(); p++) svg += tk.renderToSVG(p);
  $("score").innerHTML = svg;
}

function markDirty() {
  dirty = true;
  $("save").disabled = false;
  $("status").textContent = "Unsaved changes";
}

// ---- Click-to-edit popup

function openPopup(i, focusVerse) {
  closePopup(true, false);
  const note = notes[i];
  const g = document.getElementById("n" + i);
  if (!g) return;
  const popup = $("popup");
  popup.replaceChildren();
  for (const v of verses) {
    const label = document.createElement("label");
    if (verses.length > 1) label.append(`Verse ${v} `);
    const input = document.createElement("input");
    input.dir = "auto";
    input.dataset.verse = v;
    input.value = shown(lyricOf(note, v));
    label.append(input);
    popup.append(label);
  }
  const buttons = document.createElement("div");
  buttons.className = "popup-buttons";
  const done = Object.assign(document.createElement("button"), { type: "button", textContent: "Done" });
  const cancel = Object.assign(document.createElement("button"), { type: "button", textContent: "Cancel" });
  done.addEventListener("click", () => closePopup(true));
  cancel.addEventListener("click", () => closePopup(false));
  buttons.append(done, cancel);
  popup.append(buttons);
  current = { i, before: verses.map(v => shown(lyricOf(note, v))) };
  document.querySelectorAll("#score .current").forEach(e => e.classList.remove("current"));
  g.classList.add("current");
  const r = g.getBoundingClientRect();
  popup.style.left = `${Math.max(8, r.left + scrollX - 20)}px`;
  popup.style.top = `${r.bottom + scrollY + 6}px`;
  popup.hidden = false;
  popup.scrollIntoView({ block: "nearest" });
  const input = popup.querySelector(`input[data-verse="${focusVerse}"]`) || popup.querySelector("input");
  input.focus();
  input.select();
}

// Apply (or drop) the popup's edits; returns whether anything changed.
function commitPopup() {
  if (!current) return false;
  let changed = false;
  $("popup").querySelectorAll("input").forEach((input, k) => {
    if (input.value.trim() !== current.before[k].trim()) {
      setLyric(notes[current.i], input.dataset.verse, input.value);
      changed = true;
    }
  });
  return changed;
}

let pendingRender = false;
function closePopup(commit, rerender = true) {
  if (!current) return;
  if (commit && commitPopup()) {
    markDirty();
    pendingRender = true;
  }
  current = null;
  $("popup").hidden = true;
  if (rerender && pendingRender) {
    pendingRender = false;
    render();
  }
}

function move(step) {
  const { i } = current;
  const verse = document.activeElement?.dataset?.verse || verses[0];
  const notesOfLine = line(notes[i]);
  const target = notesOfLine[notesOfLine.indexOf(notes[i]) + step];
  if (target) openPopup(notes.indexOf(target), verse);
}

function onScoreClick(e) {
  const chord = e.target.closest("g.chord");
  const g = e.target.closest("g.note") || chord?.querySelector("g.note");
  if (!g || !/^n\d+$/.test(g.id)) return closePopup(true);
  let i = +g.id.slice(1);
  while (i > 0 && isChordTone(notes[i])) i--;
  const verseEl = e.target.closest("g.verse");
  const container = chord || g;
  const k = verseEl ? Array.from(container.querySelectorAll("g.verse")).indexOf(verseEl) : 0;
  const numbers = Array.from(notes[i].children).filter(c => c.tagName === "lyric").map(lyricNumber)
    .sort((a, b) => a - b);
  openPopup(i, numbers[k] || verses[0]);
}

function onPopupKey(e) {
  if (e.key === "Enter") closePopup(true);
  else if (e.key === "Escape") closePopup(false);
  else if (e.key === "Tab") {
    e.preventDefault();
    move(e.shiftKey ? -1 : 1);
  }
}

// ---- Edit a whole line as text

function lines() {
  const names = Object.fromEntries(Array.from(xml.getElementsByTagName("score-part"))
    .map(sp => [sp.getAttribute("id"), child(sp, "part-name")?.textContent || sp.getAttribute("id")]));
  const result = [];
  for (const part of xml.getElementsByTagName("part")) {
    const sung = Array.from(part.getElementsByTagName("note")).filter(isSung);
    const voices = [...new Set(sung.map(voiceOf))];
    for (const voice of voices) {
      const name = names[part.getAttribute("id")] || part.getAttribute("id");
      result.push({
        label: voices.length > 1 ? `${name} (voice ${voice})` : name,
        notes: sung.filter(n => voiceOf(n) === voice),
      });
    }
  }
  return result;
}

function tokens(text) {
  return text.split(/\s+/).flatMap(word => {
    const parts = word.split("-").filter(Boolean);
    return parts.map((p, k) => k < parts.length - 1 ? p + "-" : p);
  });
}

let panelLines = [];
const panelSlots = () => panelLines[$("panel-part").value].notes.filter(n => lyricOf(n, $("panel-verse").value));

function fillPanelText() {
  $("panel-text").value = panelSlots().map(n => shown(lyricOf(n, $("panel-verse").value)))
    .map(s => s.endsWith("-") ? s : s + " ").join("").trim();
  updateCount();
}

function updateCount() {
  const typed = tokens($("panel-text").value).length, slots = panelSlots().length;
  $("panel-count").textContent = `${typed} of ${slots} syllables`;
  $("panel-apply").disabled = typed !== slots;
}

function openPanel() {
  closePopup(true);
  panelLines = lines();
  $("panel-part").replaceChildren(...panelLines.map((l, k) => new Option(l.label, k)));
  $("panel-verse").replaceChildren(...verses.map(v => new Option(v, v)));
  $("panel").hidden = false;
  fillPanelText();
  $("panel-text").focus();
}

function applyPanel() {
  const v = $("panel-verse").value;
  const slots = panelSlots();
  tokens($("panel-text").value).forEach((t, k) => {
    if (t !== shown(lyricOf(slots[k], v))) setLyric(slots[k], v, t);
  });
  markDirty();
  render();
  fillPanelText();
}

// ---- Save and downloads

async function save() {
  closePopup(true);
  $("save").disabled = true;
  $("status").textContent = "Saving and making the PDF…";
  const response = await fetch(`/api/jobs/${job}/score.musicxml`, {
    method: "PUT",
    headers: { "Content-Type": "application/vnd.recordare.musicxml+xml" },
    body: new XMLSerializer().serializeToString(xml),
  });
  if (!response.ok) {
    $("save").disabled = false;
    $("status").textContent = `Saving failed: ${(await response.json()).detail || response.status}`;
    return;
  }
  dirty = false;
  setDownloads();
  $("status").textContent = "Saved. The downloads include your changes.";
}

function setDownloads() {
  const t = Date.now();
  $("get-xml").href = `/jobs/${job}/score.musicxml?t=${t}`;
  $("get-pdf").href = `/jobs/${job}/score.pdf?t=${t}`;
}

// ---- Start-up

async function loadEditor() {
  $("status").textContent = "Loading the score…";
  const [text] = await Promise.all([fetch(`/jobs/${job}/score.musicxml`).then(r => r.text()), verovioReady]);
  xml = new DOMParser().parseFromString(text, "application/xml");
  notes = Array.from(xml.getElementsByTagName("note"));
  verses = [...new Set(Array.from(xml.getElementsByTagName("lyric")).map(lyricNumber))].sort((a, b) => a - b);
  if (!verses.length) verses = ["1"];
  tk = new verovio.toolkit();
  render();
  setDownloads();
  $("tools").hidden = false;
  $("help").hidden = false;
  $("status").textContent = "Ready. Check the lyrics, then save.";

  $("score").addEventListener("click", onScoreClick);
  $("popup").addEventListener("keydown", onPopupKey);
  // A click outside the popup and the score (score clicks are handled above) closes it.
  document.addEventListener("click", e => {
    if (!$("popup").contains(e.target) && !$("score").contains(e.target)) closePopup(true);
  });
  $("save").addEventListener("click", save);
  $("text-view").addEventListener("click", openPanel);
  $("panel-part").addEventListener("change", fillPanelText);
  $("panel-verse").addEventListener("change", fillPanelText);
  $("panel-text").addEventListener("input", updateCount);
  $("panel-apply").addEventListener("click", applyPanel);
  $("panel-close").addEventListener("click", () => { $("panel").hidden = true; });
  let resize;
  addEventListener("resize", () => {
    clearTimeout(resize);
    resize = setTimeout(() => { closePopup(true); render(); }, 300);
  });
  addEventListener("beforeunload", e => { if (dirty) e.preventDefault(); });
}

async function poll() {
  const started = Date.now();
  for (;;) {
    const response = await fetch(`/api/jobs/${job}`);
    if (!response.ok) {
      $("status").textContent = (await response.json()).detail || "Unknown job";
      return;
    }
    const status = await response.json();
    const seconds = Math.round((Date.now() - started) / 1000);
    if (status.state === "done") return loadEditor();
    if (status.state === "failed") {
      $("status").textContent = `Conversion failed: ${status.error}`;
      return;
    }
    $("status").textContent = status.state === "queued"
      ? "Waiting for another conversion to finish…"
      : `Reading the music, about a minute per page… (${seconds}s)`;
    await new Promise(r => setTimeout(r, 3000));
  }
}

poll();
