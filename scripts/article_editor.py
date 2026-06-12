#!/usr/bin/env python3
"""Tiny WYSIWYG-ish markdown editor for the article.

GET /         -> split-pane editor (textarea left, rendered preview right)
POST /save    -> writes the markdown back to disk (and shows git status hint)

Stdlib only; preview rendering uses marked.js from CDN client-side.
"""
import http.server
import json
import pathlib
import sys

ARTICLE = pathlib.Path(
    sys.argv[1] if len(sys.argv) > 1
    else pathlib.Path(__file__).resolve().parent.parent / "docs/article/2026-06-local-subagent-fleet.md"
).resolve()

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>article editor</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
 body{margin:0;font:14px/1.5 -apple-system,'Segoe UI',sans-serif;background:#0e1116;color:#dbe2ea}
 #bar{padding:8px 14px;background:#161b23;border-bottom:1px solid #232b36;display:flex;gap:12px;align-items:center}
 #bar b{color:#9fc2e8} #status{color:#7ee787;font-size:12.5px}
 #wrap{display:flex;height:calc(100vh - 45px)}
 #src{width:50%;background:#0e1116;color:#dbe2ea;border:none;border-right:1px solid #232b36;
      padding:18px;font:13px/1.6 ui-monospace,monospace;resize:none;outline:none}
 #preview{width:50%;overflow:auto;padding:18px 28px}
 #preview table{border-collapse:collapse} #preview td,#preview th{border:1px solid #2a3340;padding:4px 9px}
 #preview h1{font-size:22px} #preview code{background:#161b23;padding:1px 5px;border-radius:4px}
 button{background:#1f6feb;color:#fff;border:none;border-radius:6px;padding:6px 16px;cursor:pointer;font-weight:600}
 button:hover{background:#388bfd}
</style></head><body>
<div id="bar"><b>__NAME__</b><button onclick="save()">Save (Ctrl+S)</button><span id="status"></span></div>
<div id="wrap">
 <textarea id="src" spellcheck="false">__CONTENT__</textarea>
 <div id="preview"></div>
</div>
<script>
const src=document.getElementById('src'), prev=document.getElementById('preview'), st=document.getElementById('status');
function render(){prev.innerHTML=marked.parse(src.value);}
src.addEventListener('input',()=>{render(); st.textContent='unsaved changes'; st.style.color='#e3b341';});
async function save(){
  const r=await fetch('/save',{method:'POST',body:src.value});
  const j=await r.json();
  st.textContent=j.ok?('saved '+new Date().toLocaleTimeString()):('ERROR: '+j.error);
  st.style.color=j.ok?'#7ee787':'#f85149';
}
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='s'){e.preventDefault();save();}});
render();
</script></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        content = ARTICLE.read_text()
        page = PAGE.replace("__NAME__", ARTICLE.name).replace(
            "__CONTENT__",
            content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
        )
        body = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/save":
            self.send_response(404); self.end_headers(); return
        n = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(n).decode()
        try:
            ARTICLE.write_text(data)
            out = {"ok": True}
        except Exception as e:  # surface write errors to the page
            out = {"ok": False, "error": str(e)}
        body = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8078
    print(f"editing {ARTICLE} on http://localhost:{port}/")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
