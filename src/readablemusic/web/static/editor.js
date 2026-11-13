// Job page: wait for the conversion, then show the score and let the user fix its lyrics,
// credits and part names.
// The MusicXML is edited in place as an XML document; Verovio renders a copy whose
// <note> elements get ids n0, n1, ... so a click on the SVG leads back to the XML note.

const job = location.pathname.split("/")[2];
const $ = id => document.getElementById(id);
// The PDF's page (_toolkit in engrave.py): A4 with 5 mm staves is 1.44 times Verovio's natural
// size, with 20 mm margins at the sides, and the lines are the PDF's, written in the score.
const PAGE = { pageWidth: 3024, pageHeight: 4277, pageMarginLeft: 288, pageMarginRight: 288, lyricWordSpace: 2.0 };

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
    ...PAGE,
    scale: Math.max(10, Math.floor($("score").clientWidth * 100 / PAGE.pageWidth)),  // the page fills the window
    adjustPageHeight: true,
    breaks: "line",
    header: "encoded",  // the title and credits, as in the PDF
    footer: "encoded",
  });
  tk.loadData(new XMLSerializer().serializeToString(copy));
  let svg = "";
  for (let p = 1; p <= tk.getPageCount(); p++) svg += tk.renderToSVG(p);
  $("score").innerHTML = svg;
  showFootnotes();
}

// Verovio does not print footnotes; the PDF step draws them, and here they go under the score.
function showFootnotes() {
  const fields = [...xml.querySelectorAll('miscellaneous-field[name="footnote"]'), ...xml.querySelectorAll("rights")];
  $("footnotes").innerHTML = "";
  for (const field of fields) {
    const line = document.createElement("p");
    line.textContent = field.textContent;
    line.dir = "auto";
    $("footnotes").append(line);
  }
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
  $("details").hidden = $("signs").hidden = true;
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

// ---- Edit the title, credits and part names

const all = name => Array.from(xml.getElementsByTagName(name));
const textLines = id => $(id).value.split("\n").map(s => s.trim()).filter(Boolean);
const footnoteFields = () => all("miscellaneous-field").filter(f => f.getAttribute("name") === "footnote");
const initials = name => name.split(/[\s,-]+/).filter(Boolean)
  .map(w => /^\d/.test(w) ? w : w[0].toUpperCase()).join("");

function make(name, text, attributes = {}) {
  const el = xml.createElement(name);
  el.textContent = text;
  for (const [key, value] of Object.entries(attributes)) el.setAttribute(key, value);
  return el;
}

function creators(type) {
  return all("creator").filter(c => c.getAttribute("type") === type).map(c => c.textContent);
}

function creditsOf(type) {
  return all("credit").filter(c => child(c, "credit-type")?.textContent === type)
    .map(c => child(c, "credit-words")?.textContent || "");
}

function partRow(scorePart) {
  const row = Object.assign(document.createElement("div"), { className: "part-row" });
  const name = Object.assign(document.createElement("input"),
    { value: child(scorePart, "part-name")?.textContent || "", dir: "auto", title: "Part name" });
  const short = Object.assign(document.createElement("input"),
    { value: child(scorePart, "part-abbreviation")?.textContent || "", dir: "auto", title: "Short name" });
  name.addEventListener("input", () => { if (!short.dataset.typed) short.value = initials(name.value); });
  short.addEventListener("input", () => { short.dataset.typed = "1"; });
  row.append(name, short);
  return row;
}

function openDetails() {
  closePopup(true);
  $("panel").hidden = $("signs").hidden = true;
  $("d-title").value = all("work-title")[0]?.textContent || creditsOf("title")[0] || "";
  $("d-subtitle").value = creditsOf("subtitle").join("\n");
  for (const type of ["composer", "lyricist", "arranger"]) $(`d-${type}`).value = creators(type).join(", ");
  $("d-others").value = all("creator").filter(c => !c.getAttribute("type")).map(c => c.textContent).join("\n");
  $("d-parts").replaceChildren(document.createTextNode("Parts: name and short name"), ...all("score-part").map(partRow));
  $("d-footnotes").value = footnoteFields().map(f => f.textContent).join("\n");
  $("d-rights").value = all("rights").map(r => r.textContent).join("\n");
  $("details").hidden = false;
  $("d-title").focus();
}

// The header as the PDF step writes it: see header_lines in pagetext.py.
function headerLines(title, subtitles, music, words, arranger, others) {
  const result = title ? [["title", "center", title]] : [];
  result.push(...subtitles.map(s => ["subtitle", "center", s]));
  if (music && music === words) result.push(["composer", "right", `Words and music: ${music}`]);
  else {
    if (music) result.push(["composer", "right", `Music: ${music}`]);
    if (words) result.push(["lyricist", "left", `Words: ${words}`]);
  }
  if (arranger) result.push(["arranger", "right", `Arrangement: ${arranger}`]);
  result.push(...others.map(name => ["", "left", name]));
  return result;
}

function identification(root) {
  let ident = child(root, "identification");
  if (!ident) {
    ident = xml.createElement("identification");
    root.insertBefore(ident, child(root, "defaults") || all("credit")[0] || child(root, "part-list"));
  }
  return ident;
}

// MusicXML wants <work> first, creators and rights first in <identification>, its
// <miscellaneous> last, and the credits just before the <part-list>.
function applyDetails() {
  const root = xml.documentElement;
  const title = $("d-title").value.trim(), subtitles = textLines("d-subtitle"), others = textLines("d-others");
  const [music, words, arranger] = ["composer", "lyricist", "arranger"].map(t => $(`d-${t}`).value.trim());
  const footnotes = textLines("d-footnotes"), rights = textLines("d-rights");

  [...all("work"), ...all("movement-title"), ...all("credit"), ...all("creator"), ...all("rights"), ...footnoteFields()]
    .forEach(el => el.remove());
  if (title) {
    const work = xml.createElement("work");
    work.append(make("work-title", title));
    root.insertBefore(work, root.firstElementChild);
  }
  const ident = identification(root);
  const typed = [["composer", music], ["lyricist", words], ["arranger", arranger]].filter(([, name]) => name);
  ident.prepend(...typed.map(([type, name]) => make("creator", name, { type })),
    ...others.map(name => make("creator", name)), ...rights.map(line => make("rights", line)));
  let misc = child(ident, "miscellaneous");
  if (footnotes.length) {
    if (!misc) misc = ident.appendChild(xml.createElement("miscellaneous"));
    misc.append(...footnotes.map(line => make("miscellaneous-field", line, { name: "footnote" })));
  } else if (misc && !misc.children.length) misc.remove();
  const partList = child(root, "part-list");
  for (const [type, justify, text] of headerLines(title, subtitles, music, words, arranger, others)) {
    const credit = make("credit", "", { page: "1" });
    if (type) credit.append(make("credit-type", type));
    credit.append(make("credit-words", text,
      { justify, valign: "top", ...(type === "title" ? { "font-weight": "bold" } : {}) }));
    root.insertBefore(credit, partList);
  }

  all("score-part").forEach((scorePart, k) => {
    const [name, short] = $("d-parts").querySelectorAll(".part-row")[k].querySelectorAll("input");
    let nameEl = child(scorePart, "part-name"), shortEl = child(scorePart, "part-abbreviation");
    const changed = nameEl?.textContent !== name.value.trim();
    if (!nameEl) nameEl = scorePart.insertBefore(xml.createElement("part-name"), scorePart.firstElementChild);
    nameEl.textContent = name.value.trim();
    if (changed) child(scorePart, "part-name-display")?.remove();
    if (short.value.trim()) {
      if (!shortEl) shortEl = scorePart.insertBefore(xml.createElement("part-abbreviation"), nameEl.nextElementSibling);
      if (shortEl.textContent !== short.value.trim()) child(scorePart, "part-abbreviation-display")?.remove();
      shortEl.textContent = short.value.trim();
    } else if (shortEl) shortEl.remove();
  });
  markDirty();
  render();
  fillStaves();  // a part renamed may hold one voice more or less
}

// ---- Clef, key and time, read again on the server (see reread.py)

const CLEFS = { treble: "Treble", "treble-8": "Treble, an octave lower (tenor)", bass: "Bass", alto: "Alto" };
const MAJOR = ["C♭", "G♭", "D♭", "A♭", "E♭", "B♭", "F", "C", "G", "D", "A", "E", "B", "F♯", "C♯"];
const MINOR = ["A♭", "E♭", "B♭", "F", "C", "G", "D", "A", "E", "B", "F♯", "C♯", "G♯", "D♯", "A♯"];
const TIME = /^\d{1,2}\/(1|2|4|8|16|32)$/;

function keyName(fifths) {
  const n = Math.abs(fifths);
  const count = n ? `${n} ${fifths > 0 ? "sharp" : "flat"}${n > 1 ? "s" : ""}` : "No sharps or flats";
  return `${count} (${MAJOR[fifths + 7]} major / ${MINOR[fifths + 7]} minor)`;
}

function clefName(clef) {
  const sign = child(clef, "sign")?.textContent, octave = +(child(clef, "clef-octave-change")?.textContent || 0);
  if (sign === "G") return octave === -1 ? CLEFS["treble-8"] : octave === 1 ? "Treble, an octave higher" : CLEFS.treble;
  return { F: CLEFS.bass, C: CLEFS.alto }[sign] || sign;
}

const distinct = values => [...new Set(values)];
const asRead = values => values.length ? `As read: ${values.join("; ")}` : "As read: none";

function openSigns() {
  closePopup(true);
  $("panel").hidden = $("details").hidden = true;
  $("s-error").textContent = "";
  const keys = distinct(all("key").map(k => child(k, "fifths")?.textContent).filter(Boolean)).map(f => keyName(+f));
  const fifths = Array.from({ length: 15 }, (_, k) => k - 7);
  $("s-key").replaceChildren(new Option(asRead(keys), ""), ...fifths.map(f => new Option(keyName(f), f)));
  const times = distinct(all("time").map(t => `${child(t, "beats")?.textContent}/${child(t, "beat-type")?.textContent}`));
  $("s-time").value = "";
  $("s-time").placeholder = times.length ? `as read: ${times.join(", ")}` : "none read, e.g. 3/8";
  const names = Object.fromEntries(all("score-part").map(sp => [sp.getAttribute("id"), child(sp, "part-name")?.textContent]));
  const rows = all("part").filter(p => !Array.from(p.getElementsByTagName("staves")).some(s => +s.textContent > 1))
    .map(part => {
      const id = part.getAttribute("id");
      const select = document.createElement("select");
      select.dataset.part = id;
      const clefs = distinct(Array.from(part.getElementsByTagName("clef")).map(clefName));
      select.append(new Option(asRead(clefs), ""), ...Object.entries(CLEFS).map(([value, label]) => new Option(label, value)));
      const label = document.createElement("label");
      label.append(`Clef of ${names[id] || id} `, select);
      return label;
    });
  $("s-parts").replaceChildren(...rows);
  $("signs").hidden = false;
}

async function applySigns() {
  const clefs = {};
  $("s-parts").querySelectorAll("select").forEach(s => { if (s.value) clefs[s.dataset.part] = s.value; });
  const fifths = $("s-key").value === "" ? null : +$("s-key").value;
  const time = $("s-time").value.trim().replace(/\s/g, "") || null;
  if (time && !TIME.test(time)) {
    $("s-error").textContent = "Write the time signature as beats/note value, e.g. 3/8 or 4/4.";
    return;
  }
  if (!Object.keys(clefs).length && fifths === null && !time) return;
  $("signs-apply").disabled = true;
  $("s-error").textContent = "Reading the notes again…";
  const response = await fetch(`/api/jobs/${job}/reread`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ score: new XMLSerializer().serializeToString(xml), clefs, fifths, time }),
  });
  $("signs-apply").disabled = false;
  if (!response.ok) {
    $("s-error").textContent = (await response.json().catch(() => ({}))).detail || `Failed (${response.status})`;
    return;
  }
  useScore(await response.text());
  markDirty();
  render();
  openSigns();
  $("s-error").textContent = "Done. Check the score, then save.";
}

// ---- Staves: the voices spread over more staves or gathered onto fewer, on the server (see staves.py)

// As voices_of in staves.py: a staff named after two voices ("Soprano, Alto") holds both.
const voiceCount = () => all("score-part")
  .reduce((n, sp) => n + ((child(sp, "part-name")?.textContent || "").split(", ").length === 2 ? 2 : 1), 0);

function fillStaves() {
  const n = voiceCount(), now = all("part").length, least = Math.ceil(n / 2);
  const counts = Array.from({ length: n - least + 1 }, (_, k) => least + k);
  $("staves").replaceChildren(...counts.map(c => new Option(c, c)));
  $("staves").value = now;
  $("staves-box").hidden = counts.length < 2 || !counts.includes(now);
}

async function applyStaves() {
  closePopup(true);
  $("staves").disabled = true;
  $("status").textContent = "Moving the voices…";
  const response = await fetch(`/api/jobs/${job}/staves`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ score: new XMLSerializer().serializeToString(xml), staves: +$("staves").value }),
  });
  $("staves").disabled = false;
  if (!response.ok) {
    $("status").textContent = (await response.json().catch(() => ({}))).detail || `Failed (${response.status})`;
    fillStaves();
    return;
  }
  useScore(await response.text());
  markDirty();
  render();
  fillStaves();
  $("status").textContent = "Voices moved. Check the score, then save.";
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

function useScore(text) {
  xml = new DOMParser().parseFromString(text, "application/xml");
  notes = Array.from(xml.getElementsByTagName("note"));
  verses = [...new Set(Array.from(xml.getElementsByTagName("lyric")).map(lyricNumber))].sort((a, b) => a - b);
  if (!verses.length) verses = ["1"];
}

async function loadEditor() {
  $("status").textContent = "Loading the score…";
  const [text] = await Promise.all([fetch(`/jobs/${job}/score.musicxml`).then(r => r.text()), verovioReady]);
  useScore(text);
  tk = new verovio.toolkit();
  render();
  fillStaves();
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
  $("details-view").addEventListener("click", openDetails);
  $("details-apply").addEventListener("click", applyDetails);
  $("details-close").addEventListener("click", () => { $("details").hidden = true; });
  $("signs-view").addEventListener("click", openSigns);
  $("signs-apply").addEventListener("click", applySigns);
  $("signs-close").addEventListener("click", () => { $("signs").hidden = true; });
  $("staves").addEventListener("change", applyStaves);
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
    if (status.state === "poor") return askAnyway(status);
    $("status").textContent = status.state === "queued"
      ? "Waiting for another conversion to finish…"
      : `Reading the music, about a minute per page… (${seconds}s)`;
    await new Promise(r => setTimeout(r, 3000));
  }
}

function askAnyway(status) {
  $("status").textContent = "Stopped before reading the music";
  $("poor-problems").replaceChildren(...status.problems.map(text => {
    const li = document.createElement("li");
    li.textContent = text;
    return li;
  }));
  $("poor-cost").textContent = status.cost === null
    ? "Claude, which reads handwriting and hard photos, reads here only with an access code. "
      + "Reading it anyway gives what recognition alone finds."
    : `Reading it anyway has Claude read the music, at a cost of about $${status.cost.toFixed(2)}.`;
  $("poor").hidden = false;
}

$("anyway").addEventListener("click", async () => {
  $("anyway").disabled = true;
  const response = await fetch(`/api/jobs/${job}/anyway`, {method: "POST", body: "{}"});
  if (!response.ok) {
    $("poor-cost").textContent = (await response.json().catch(() => ({}))).detail || `Failed (${response.status})`;
    $("anyway").disabled = false;
    return;
  }
  $("poor").hidden = true;
  poll();
});

poll();
