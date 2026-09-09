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
      lineHeight: 1.08,
      scrollback: 10000,
      theme: {
        background: "#000000", foreground: "#eeeeee", cursor: "#eeeeee",
        black: "#000000", red: "#ff3b30", green: "#00e05a", yellow: "#fff200",
        blue: "#2f80ff", magenta: "#ff42ff", cyan: "#00e5ff", white: "#e6e6e6",
        brightBlack: "#777777", brightRed: "#ff6258", brightGreen: "#54ff7d",
        brightYellow: "#ffff66", brightBlue: "#66a3ff", brightMagenta: "#ff7aff",
        brightCyan: "#66f3ff", brightWhite: "#ffffff"
      }
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
