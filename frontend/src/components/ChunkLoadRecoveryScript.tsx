/**
 * Inline bootstrap — a layout.js chunk ELŐTT fut (nem webpack chunk).
 * Dev/Docker HMR: ChunkLoadError / ERR_CONNECTION_RESET → automatikus reload.
 */
export function ChunkLoadRecoveryScript() {
  const script = `
(function () {
  var KEY = "bitunix_chunk_reload";
  function isChunk(msg) {
    if (!msg) return false;
    return /ChunkLoadError|Loading chunk/i.test(String(msg));
  }
  function reload() {
    var n = Number(sessionStorage.getItem(KEY) || "0");
    if (n >= 3) return;
    sessionStorage.setItem(KEY, String(n + 1));
    location.reload();
  }
  window.addEventListener("error", function (e) {
    if (isChunk(e.message) || (e.error && isChunk(e.error.name))) reload();
  });
  window.addEventListener("unhandledrejection", function (e) {
    var r = e.reason;
    var msg = r && (r.message || r.name) ? r.message || r.name : r;
    if (isChunk(msg)) reload();
  });
  window.addEventListener("load", function () {
    sessionStorage.removeItem(KEY);
  });
})();
`.trim();

  return (
    <script
      dangerouslySetInnerHTML={{ __html: script }}
      suppressHydrationWarning
    />
  );
}
