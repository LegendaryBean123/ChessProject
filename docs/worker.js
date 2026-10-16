// Runs chessstats in the browser for the GitHub Pages site, which has no server to run Python.
// Pyodide is Python compiled to WebAssembly; this worker starts it, unpacks chessstats.zip
// (this package and python-chess) and answers the page's look-ups with browser.report_json.
// It runs off the page's thread, so the page stays responsive while games download.
// `python -m chessstats --pages DIR` fills in the placeholders in capitals (see pages.py).

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
const MIN_GAMES = 3;
const DATA_DIR = "/data"; // browser.DATA_DIR

importScripts(`${PYODIDE_URL}pyodide.js`);

let pyodide = null;
const started = (async () => {
  pyodide = await loadPyodide({ indexURL: PYODIDE_URL });
  await pyodide.loadPackage("requests"); // the shared code catches requests' errors
  const zip = await fetch("chessstats.zip");
  if (!zip.ok) throw new Error(`could not download chessstats.zip (${zip.status})`);
  pyodide.unpackArchive(await zip.arrayBuffer(), "zip", { extractDir: "/home/pyodide" });
  pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  // Keep downloaded months between visits. Without IndexedDB (some private windows) they
  // only last until the page is closed.
  pyodide.FS.mkdirTree(DATA_DIR);
  try {
    pyodide.FS.mount(pyodide.FS.filesystems.IDBFS, {}, DATA_DIR);
    await syncCache(true);
  } catch (error) {
    console.warn("chessstats: months won't be kept between visits", error);
  }
  return pyodide.pyimport("chessstats.browser");
})();

function syncCache(load) {
  return new Promise((resolve) => pyodide.FS.syncfs(load, (error) => {
    if (error) console.warn("chessstats: could not sync saved months", error);
    resolve();
  }));
}

// A blocking request. The Python code downloads one month after another, and workers may block.
function get(url) {
  const request = new XMLHttpRequest();
  request.open("GET", url, false);
  try {
    request.send();
  } catch {
    return [0, ""];
  }
  return [request.status, request.responseText];
}

// One look-up at a time, like the server: chess.com asks for one request at a time.
let queue = Promise.resolve();
onmessage = ({ data }) => {
  queue = queue.then(() => lookUp(data));
};

async function lookUp({ id, user, range }) {
  if (!pyodide) postMessage({ progress: { status: "Starting Python in your browser…" } });
  try {
    const browser = await started;
    const onProgress = (done, total) => postMessage({ progress: { done, total } });
    const body = JSON.parse(browser.report_json(get, user, range, MIN_GAMES, onProgress));
    await syncCache(false);
    postMessage(body.error ? { id, error: body.error } : { id, report: body });
  } catch (error) {
    postMessage({ id, error: `Something went wrong running chessstats in this browser: ${error.message}` });
  }
}
