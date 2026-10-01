// Executa o RESYNC_JS real (app/sources/chatpanel.py) num DOM/jQuery falsos, com um
// "servidor" paginado. Uso: node tests/resync_js_harness.js <arquivo-com-o-js> <modo> [cenário]
// Imprime JSON: {result, boxes: {box-atende-chats, box-atendeothers-chats}, calls}.
// Cenários: normal (padrão) | dead (sessão morta: listas vazias e a página cai no login) |
// empty-alive (listas vazias de verdade, sessão viva) | probe-error (listas vazias e a
// consulta da sessão falha) | empty-dom (listas vazias e DOM já sem conversas).
"use strict";
const fs = require("fs");

const js = fs.readFileSync(process.argv[2], "utf8");
const mode = process.argv[3] || "full";
const scenario = process.argv[4] || "normal";

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

// --- cenários de sessão: depois da carga, o servidor passa a devolver listas vazias ----
const PAGE_URL = "https://x/chat.php";
const pages = {
  alive: '<html><input type="hidden" id="int_username" value="TUI"><input type="hidden" id="int_username_st" value="1"></html>',
  // o id parecido (int_username_st) não pode ser confundido com o do usuário logado
  login: '<html><form><input id="user"><input type="password" id="password"><input id="captcha">' +
    '<input type="hidden" id="int_username_st" value="0"></form></html>',
};
if (scenario !== "normal") {
  server["control-atende-on-us.php"] = { 1: "" };
  server["control-atende-on-ot.php"] = { 1: "" };
}
if (scenario === "empty-dom") {  // nada no DOM e nada no servidor: não há o que proteger
  boxes["box-atende-chats"] = "";
  boxes["box-atendeothers-chats"] = "";
}

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
$.ajax = ({ type, url, data, cache, success, error }) => {
  if (type === "GET") {  // consulta da sessão: a própria página (viva) ou a tela de login (morta)
    calls.push({ url, page: 0, cache });
    const html = scenario === "probe-error" ? undefined : scenario === "dead" ? pages.login : pages.alive;
    setTimeout(() => (html === undefined ? error() : success(html)), 0);
    return;
  }
  const page = data.qpage || 1;
  calls.push({ url, page });
  const html = server[url] && server[url][page];
  setTimeout(() => (html === undefined ? error() : success(html)), 0);
};

globalThis.$ = $;
globalThis.document = document;  // o RESYNC_JS usa os dois como globais
globalThis.location = { href: PAGE_URL };
const fn = eval("(" + js + ")");
fn.call({ $, document }, mode).then((result) => {
  console.log(JSON.stringify({ result, boxes, calls }));
});

