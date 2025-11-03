import glob
import http.server
import json
import os
import re
import socketserver
import urllib.parse

files = "*.png"
keys = {"1": "good", "2": "bad"}

INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Evaluate plots</title>
  <!-- Thx to ChatGTP for help w/HTLM https://chatgpt.com/share/68f51123-dab0-8006-ac9a-644a997d9b68 + https://chatgpt.com/share/6908ee67-0990-8006-8d00-ac22ac169130 -->
  <style>
    html,body{height:100%;margin:0}
    body{background:#000;display:flex;align-items:center;justify-content:center}

    #viewer{
      width:100vw;
      height:100vh;
      object-fit:contain;
      display:block;
    }

    /* Hidden preload image (kept out of layout but loaded by browser) */
    .preload{
      visibility:hidden;
      position:absolute;
      width:1px;
      height:1px;
      overflow:hidden;
      pointer-events:none;
      left:-9999px;
      top:-9999px;
    }

    .hint{
      color:rgba(255,255,255,0.85);
      font-family:system-ui,sans-serif;
      font-size:13px;
      background:rgba(0,0,0,0.35);
      padding:6px 8px;
      border-radius:6px;
    }
    .hintcontainer{
      position:fixed;
      left:12px;
      right:12px;
      text-align:center;
      bottom:12px;
    }
  </style>
</head>
  <body>
  <img id="viewer" src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==" alt="fullscreen image" />
  <img class="preload" src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==" alt="preload" aria-hidden="true" />
  <img class="preload" src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==" alt="preload" aria-hidden="true" />
  <img class="preload" src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==" alt="preload" aria-hidden="true" />
  <div class="hintcontainer"><span class="hint"></span></div>
  <script>
function init(data) {
  const session = new Date().toISOString().replace(/:/g, "-");
  const filenames = data.filenames;
  const keys = data.keys;
  const viewer = document.getElementById('viewer');
  const hint = document.querySelector(".hint");
  const preload = [...document.querySelectorAll('.preload')];
  const imageselection = data.imageselection ?? {};
  let index = 0;

  function showIndex(i){
    index = (i + filenames.length) % filenames.length;
    const current = filenames[index];
    viewer.src = current;
    const key = imageselection[current];
    const label = key ? ` → ${keys[key]} (${key})` : "";
    if (hint) hint.textContent = `(${index+1}/${filenames.length}) ${current}${label}`;
    document.title = `Image selection (${index+1}/${filenames.length}) ${current}`;
    history.replaceState(history.state, "", `${location.pathname}?${window.encodeURIComponent(current)}`);
    for (let j = 0; j < preload.length; ++j)
      preload[j].src = filenames[(index + j + 1) % filenames.length];
  }

  function showNext(){ showIndex(index + 1); }
  function showPrev(){ showIndex(index - 1); }

  window.addEventListener('keydown', function(e){
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if(tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement.isContentEditable) return;

    if(e.key === 'ArrowRight'){
      e.preventDefault();
      showNext();
    } else if(e.key === 'ArrowLeft'){
      e.preventDefault();
      showPrev();
    } else if(keys[e.key]) {
      // record classification
      const currentpath = filenames[index];
      imageselection[currentpath] = e.key;
      console.log(`Selected ${currentpath}: ${keys[e.key]} (${e.key})`);
      showIndex(index); // update hint immediately

      // send POST to /save
      fetch("/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          session,
          imageselection,
        })
      }).catch(err => alert("POST /save failed:", err));
    }
  });

  viewer.addEventListener('click', function(e){
    const w = viewer.clientWidth;
    if(e.clientX > w/2) showNext(); else showPrev();
  });

  const f = location.search.replace("?", "").replace(/[;&].*/, "");
  const i = filenames.indexOf(window.decodeURIComponent(f));
  console.log(location.search, i);
  showIndex(i === -1 ? 0 : i);
}
  </script>

</body>
</html>
"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        try:
            if urllib.parse.urlparse(self.path).path == "/":
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                prevstate = glob.glob("selections/*.json")
                data = {"filenames": glob.glob(files), "keys": keys}
                if prevstate:
                    with open(max(prevstate)) as fp:
                        data["imageselection"] = json.load(fp)
                self.wfile.write(
                    (INDEX_HTML + f"<script>init({json.dumps(data)})</script>").encode(
                        "utf-8"
                    )
                )
            else:
                super().do_GET()
        except BrokenPipeError:
            pass

    def do_POST(self):
        if self.path == "/save":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
            except Exception:
                data = body.decode("utf-8", errors="replace")
            print("Received /save:", data)
            filename = re.sub(r"[^0-9a-zA-Z-]", "", data["session"]) + ".json"
            savedata = json.dumps(data["imageselection"])
            with open(os.path.join("selections", filename), "w") as ofp:
                ofp.write(savedata)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_error(404, "Not found")


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True  # sets SO_REUSEADDR


def main() -> None:
    port = 8000
    os.makedirs("selections", exist_ok=True)
    with ReusableTCPServer(("", port), Handler) as httpd:
        print(f"Serving at http://localhost:{port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
