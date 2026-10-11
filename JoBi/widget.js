/* Library book bot chat widget. Add to any page:
   <script src="https://YOUR-SERVER/widget.js" data-api="https://YOUR-SERVER"></script>
*/
(function () {
  var script = document.currentScript;
  var API = (script && script.getAttribute("data-api")) || "";

  var css = "\
#bb-btn{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:0;background:#2b6cb0;color:#fff;font-size:26px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.25);z-index:99999}\
#bb-box{position:fixed;right:20px;bottom:88px;width:360px;max-width:calc(100vw - 40px);height:480px;max-height:calc(100vh - 110px);background:#fff;border-radius:12px;box-shadow:0 8px 28px rgba(0,0,0,.25);display:none;flex-direction:column;overflow:hidden;font-family:system-ui,Arial,sans-serif;font-size:14px;z-index:99999}\
#bb-head{background:#2b6cb0;color:#fff;padding:12px 14px;font-weight:600}\
#bb-log{flex:1;overflow-y:auto;padding:10px;background:#f7f7f9}\
.bb-m{margin:6px 0;padding:8px 10px;border-radius:10px;max-width:92%;line-height:1.35;word-wrap:break-word}\
.bb-u{background:#2b6cb0;color:#fff;margin-left:auto}\
.bb-b{background:#fff;border:1px solid #e2e2e8}\
.bb-card{margin-top:6px;padding:6px 8px;border-left:3px solid #2b6cb0;background:#f1f6fc;border-radius:4px}\
.bb-card.bb-res{border-left-color:#7c3aed;background:#f5f0fe}\
.bb-card b{display:block}\
.bb-card small{color:#555;display:block}\
.bb-ok{color:#1a7f37!important;font-weight:600}\
.bb-no{color:#b45309!important;font-weight:600}\
.bb-card a{color:#5b21b6;word-break:break-all}\
.bb-h{margin-top:8px;font-weight:600;font-size:12px;color:#444}\
#bb-form{display:flex;border-top:1px solid #e2e2e8}\
#bb-in{flex:1;border:0;padding:12px;font-size:14px;outline:none}\
#bb-send{border:0;background:#fff;color:#2b6cb0;font-weight:600;padding:0 14px;cursor:pointer}";

  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  var btn = document.createElement("button");
  btn.id = "bb-btn";
  btn.setAttribute("aria-label", "Open library assistant");
  btn.textContent = "📖";

  var box = document.createElement("div");
  box.id = "bb-box";
  box.innerHTML =
    '<div id="bb-head">Library Assistant</div>' +
    '<div id="bb-log"></div>' +
    '<form id="bb-form"><input id="bb-in" placeholder="e.g. books on network security" autocomplete="off">' +
    '<button id="bb-send" type="submit">Send</button></form>';

  document.body.appendChild(btn);
  document.body.appendChild(box);

  var log = box.querySelector("#bb-log");
  var input = box.querySelector("#bb-in");

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  function add(text, who) {
    var d = el("div", "bb-m " + (who === "u" ? "bb-u" : "bb-b"), text);
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }

  function addBooks(parent, books) {
    books.forEach(function (b) {
      var c = el("div", "bb-card");
      c.appendChild(el("b", "", b.title));
      var meta = [b.author, b.genre, b.year].filter(Boolean).join(" · ");
      if (meta) c.appendChild(el("small", "", meta));
      c.appendChild(el("small", b.available ? "bb-ok" : "bb-no", b.availability));
      if (b.description) c.appendChild(el("div", "", b.description));
      parent.appendChild(c);
    });
  }

  function addResources(parent, resources) {
    if (!resources.length) return;
    parent.appendChild(el("div", "bb-h", "Free online resources"));
    resources.forEach(function (r) {
      var c = el("div", "bb-card bb-res");
      c.appendChild(el("b", "", r.title));
      var meta = [r.type, r.genre].filter(Boolean).join(" · ");
      if (meta) c.appendChild(el("small", "", meta));
      if (r.url) {
        var a = el("a", "", r.url);
        a.href = r.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        c.appendChild(a);
      }
      parent.appendChild(c);
    });
  }

  btn.onclick = function () {
    var open = box.style.display === "flex";
    box.style.display = open ? "none" : "flex";
    if (!open) {
      if (!log.children.length) add("Hi! Tell me a topic, subject or author and I'll suggest books from our library.", "b");
      input.focus();
    }
  };

  box.querySelector("#bb-form").onsubmit = function (e) {
    e.preventDefault();
    var q = input.value.trim();
    if (!q) return;
    input.value = "";
    add(q, "u");
    var wait = add("...", "b");
    fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: q })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        wait.textContent = data.reply;
        addBooks(wait, data.books || []);
        addResources(wait, data.resources || []);
        log.scrollTop = log.scrollHeight;
      })
      .catch(function () {
        wait.textContent = "Sorry, I can't reach the library server right now.";
      });
  };
})();
