(function () {
  "use strict";

  let terminal = null;
  let fitAddon = null;
  let writeChain = Promise.resolve();
  const fallback = document.getElementById("terminal-fallback");

  function initTerminal(onInput, onResize) {
    if (!window.Terminal || !window.FitAddon) {
      document.getElementById("terminal").classList.add("hidden");
      fallback.classList.remove("hidden");
      fallback.textContent = "xterm.js 加载失败。请检查网络，或按 README 将依赖放到本地。\n";
      return;
    }
    terminal = new window.Terminal({
      cursorBlink: true,
      convertEol: false,
      fontFamily: "Cascadia Mono, Consolas, monospace",
      fontSize: 14,
      scrollback: 10000,
      theme: { background: "#0b1020", foreground: "#d7e0f2", cursor: "#62d9ff" }
    });
    fitAddon = new window.FitAddon.FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(document.getElementById("terminal"));
    fitAddon.fit();
    terminal.onData(onInput);
    terminal.onResize(({ cols, rows }) => onResize(cols, rows));
    window.addEventListener("resize", () => fitAddon.fit());
  }

  function writeTerminal(data) {
    if (!terminal) {
      fallback.textContent += data;
      fallback.scrollTop = fallback.scrollHeight;
      return Promise.resolve();
    }
    writeChain = writeChain.then(() => new Promise((resolve) => terminal.write(data, resolve)));
    return writeChain;
  }

  async function terminalRendered() {
    await writeChain;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }

  window.RTRTerminal = {
    init: initTerminal,
    write: writeTerminal,
    rendered: terminalRendered,
    focus: () => terminal && terminal.focus(),
    fit: () => fitAddon && fitAddon.fit()
  };
})();

