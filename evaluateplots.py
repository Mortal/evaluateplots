"""
This script MUST be called from the directory containing plots/images to classify.
Run the script and open your browser to http://localhost:8000
Press '1'/'2' to classify each image and use arrow left/right to navigate between images.
The classification is stored in JSON format in a subdir named 'selections'.
"""
import glob
import http.server
import json
import os
import re
import socketserver
import urllib.parse

# glob.glob() pattern matching files to sort through:
files = "*.png"
# different keys to press to classify each image:
keys = {"1": "good", "2": "bad"}

# ------------------------------------------------------

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

    .hintcontainer{
      position:fixed;
      left:12px;
      bottom:12px;
      color:rgba(255,255,255,0.85);
      font-family:system-ui,sans-serif;
      font-size:13px;
      background:rgba(0,0,0,0.65);
      padding:6px 8px;
      border-radius:6px;
    }
    .keyform {
      display: inline;
    }
    .keyform label {
      margin: 0 1em;
      cursor: pointer;
    }
  </style>
</head>
  <body>
  <img id="viewer" src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==" alt="fullscreen image" />
  <img class="preload" src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==" alt="preload" aria-hidden="true" />
  <img class="preload" src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==" alt="preload" aria-hidden="true" />
  <img class="preload" src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==" alt="preload" aria-hidden="true" />
  <div class="hintcontainer">
    <form id="keyform" class="keyform"></form>
    <span class="hint"></span>
  </div>
  <script>
function init(data) {
  const session = new Date().toISOString().replace(/:/g, "-");
  const filenames = data.filenames;
  const keys = data.keys;
  const viewer = document.getElementById('viewer');
  const hint = document.querySelector(".hint");
  const preload = [...document.querySelectorAll('.preload')];
  const form = document.getElementById('keyform');
  const imageselection = data.imageselection ?? {};
  let index = 0;

  if (form) {
    for (const [k, label] of Object.entries(keys)) {
      const id = `key_${k}`;
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = 'classification';
      input.id = id;
      input.value = k;

      const lab = document.createElement('label');
      lab.setAttribute('for', id);
      lab.textContent = `${label} (${k})`;

      form.appendChild(input);
      form.appendChild(lab);
    }
  }

  // update checked state when current image changes
  function updateFormSelection(current) {
    if (form == null) return;
    const selectedKey = imageselection[current];
    for (const input of form.elements) {
      input.checked = input.value === selectedKey;
    }
  }

  function showIndex(i){
    index = (i + filenames.length) % filenames.length;
    const current = filenames[index];
    viewer.src = current;
    const key = imageselection[current];
    if (hint) hint.textContent = `(${index+1}/${filenames.length}) ${current}`;
    document.title = `Image selection (${index+1}/${filenames.length}) ${current}`;
    history.replaceState(history.state, "", `${location.pathname}?f=${window.encodeURIComponent(current)}`);
    for (let j = 0; j < preload.length; ++j)
      preload[j].src = filenames[(index + j + 1) % filenames.length];
    updateFormSelection(current);
  }

  function showNext(){ showIndex(index + 1); }
  function showPrev(){ showIndex(index - 1); }

  function classify(currentpath, key) {
    imageselection[currentpath] = key;
    console.log(`Selected ${currentpath}: ${keys[key]} (${key})`);
    showIndex(index); // refresh hint

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

  window.addEventListener('keydown', function(e){
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if(tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement.isContentEditable) return;
    if(e.ctrlKey || e.altKey || e.shiftKey || e.metaKey) return;

    if(e.key === 'ArrowRight'){
      e.preventDefault(); showNext();
    } else if(e.key === 'ArrowLeft'){
      e.preventDefault(); showPrev();
    } else if(keys[e.key]) {
      e.preventDefault();
      classify(filenames[index], e.key);
    }
  });

  viewer.addEventListener('click', function(e){
    const w = viewer.clientWidth;
    if(e.clientX > w/2) showNext(); else showPrev();
  });

  // click handler for mouse radio selection
  form?.addEventListener('change', function(e){
    const k = e.target.value;
    classify(filenames[index], k);
  });

  const f = new URLSearchParams(location.search).get("f") ?? new URLSearchParams(location.hash.replace("#", "")).get("f") ?? "";
  const i = filenames.indexOf(f);
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
            filename = re.sub(r"[^0-9a-zA-Z-]", "", data["session"]) + ".json"
            savedata = json.dumps(data["imageselection"])
            print(filename)
            print(savedata, flush=True)
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
