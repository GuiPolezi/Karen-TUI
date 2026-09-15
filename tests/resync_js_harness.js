// Executa o EXPAND_JS real (app/sources/chatpanel.py) num DOM/jQuery falsos, com um
// "servidor" paginado. Uso: node tests/resync_js_harness.js <arquivo-com-o-js>
// Imprime JSON: {result, boxes: {box-atende-chats, box-atendeothers-chats}, calls}.
"use strict";
const fs = require("fs");

const js = fs.readFileSync(process.argv[2], "utf8");

// --- servidor falso: 2 listas, 3 páginas na "us" e 1 na "ot" ------------------------
const li = (n, agent) => `<li class="checkforactive" id="chat_${n}"><a><span class="avatar"></span>` +
  `<p class="mb-0 fw-medium">Contato ${n} <span class="float-end">10:00</span></p>` +
  `<p class="fs-12 mb-0"><span class="chat-msg">oi</span></p>` +
  `<p class="mb-0"><span class="badge"><i class="bi bi-person"></i> ${agent}</span></p></a></li>`;
const footer = (id, fn, page) =>
  `<div class="text-center my-2" id="${id}"><button id="btnX" onclick="${fn}(${page - 1} + 1)">ver mais</button></div>`;
const server = {
  "control-atende-on-us.php": {
    1: li(101, "Guilherme") + li(102, "Guilherme") + footer("box-bottom-activeus-services", "viewMoreActiveusChats", 2),
    2: li(103, "Guilherme") + footer("box-bottom-activeus-services", "viewMoreActiveusChats", 3),
    3: li(104, "Guilherme"),
  },
  "control-atende-on-ot.php": { 1: li(201, "Fulano") },
};
const calls = [];

// --- DOM falso: cada box guarda innerHTML; o rodapé é achado por id dentro do box ----
const boxes = { "box-atende-chats": "", "box-atendeothers-chats": "" };
// estado inicial "como a página carregou": só a 1ª página de cada lista
boxes["box-atende-chats"] = server["control-atende-on-us.php"][1];
boxes["box-atendeothers-chats"] = server["control-atende-on-ot.php"][1];

function findFooter(id) {
  for (const box of Object.keys(boxes)) {
    const re = new RegExp(`<div[^>]*id="${id}"[^>]*>.*?</div>`, "s");
    const m = boxes[box].match(re);
    if (m) return { box, html: m[0] };
  }
  return null;
}
const document = {
  getElementById(id) {
    if (id in boxes) return { innerHTML: boxes[id] };
    const f = findFooter(id);
    if (!f) return null;
    return { innerHTML: f.html, remove() { boxes[f.box] = boxes[f.box].replace(f.html, ""); } };
  },
};
function $(sel) {
  if (sel.startsWith("#")) {
    const id = sel.slice(1);
    return {
      remove() { const el = document.getElementById(id); if (el && el.remove) el.remove(); },
      html(h) { boxes[id] = h; },
      append(h) { boxes[id] += h; },
    };
  }
  throw new Error("seletor não suportado: " + sel);
}
$.ajax = ({ url, data, success, error }) => {
  const page = data.qpage || 1;
  calls.push({ url, page });
  const html = server[url] && server[url][page];
  setTimeout(() => (html === undefined ? error() : success(html)), 0);
};

globalThis.$ = $;
globalThis.document = document;  // o EXPAND_JS usa os dois como globais
const fn = eval("(" + js + ")");
fn.call({ $, document }).then((result) => {
  console.log(JSON.stringify({ result, boxes, calls }));
});

