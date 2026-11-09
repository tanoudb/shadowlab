// Évasion font fingerprinting — défense contre l'énumération de polices.
// Les détecteurs mesurent la largeur de texte rendu dans différentes polices pour déduire
// lesquelles sont installées. Ce script normalise les résultats pour correspondre au profil.
// Technique : brouillage des mesures de texte (measureText, getBoundingClientRect sur spans).
(() => {
  const P = window.__NOEZIA_PROFIL__;
  const natif = window.__NOEZIA_NATIF__;
  if (!P || !natif) return;

  try { const h = location.hostname;
    if (h !== 'localhost' && h !== '127.0.0.1' && !h.endsWith('.localhost') && !h.endsWith('.test')) return;
  } catch(e) { return; }

  // PRNG déterministe (même seed que canvas)
  let seed = P.canvas_seed || 42;
  function rand() {
    seed = (seed * 1664525 + 1013904223) & 0xffffffff;
    return (seed >>> 0) / 0xffffffff;
  }

  // Polices système par OS
  const POLICES_OS = {
    macOS: ['Arial', 'Helvetica Neue', 'Helvetica', 'Times New Roman', 'Courier New', 'Georgia',
            'Trebuchet MS', 'Verdana', 'Menlo', 'SF Pro', 'San Francisco', 'Lucida Grande',
            'Palatino', 'Futura', 'Avenir', 'Didot', 'Optima', 'Gill Sans'],
    Windows: ['Arial', 'Calibri', 'Cambria', 'Consolas', 'Courier New', 'Georgia',
              'Segoe UI', 'Tahoma', 'Times New Roman', 'Trebuchet MS', 'Verdana',
              'Comic Sans MS', 'Impact', 'Lucida Console', 'Palatino Linotype'],
    Linux: ['Arial', 'DejaVu Sans', 'DejaVu Serif', 'DejaVu Sans Mono', 'Liberation Sans',
            'Liberation Serif', 'Liberation Mono', 'Noto Sans', 'Noto Serif',
            'Ubuntu', 'Cantarell', 'Droid Sans', 'FreeSans'],
  };

  const osPolices = new Set(POLICES_OS[P.platform_name] || POLICES_OS.Windows);

  // Brouiller légèrement measureText pour que l'empreinte soit stable par profil
  const origMeasureText = CanvasRenderingContext2D.prototype.measureText;
  CanvasRenderingContext2D.prototype.measureText = natif(function measureText(text) {
    const result = origMeasureText.call(this, text);
    // Micro-bruit déterministe sur la largeur (±0.1px)
    const noise = (rand() - 0.5) * 0.2;
    const origWidth = result.width;
    try {
      Object.defineProperty(result, 'width', {
        get() { return origWidth + noise; },
        configurable: true,
      });
    } catch(e) {}
    return result;
  }, 'measureText');

  // Défense check() de FontFaceSet : signaler uniquement les polices du profil OS
  if (document.fonts && document.fonts.check) {
    const origCheck = document.fonts.check.bind(document.fonts);
    document.fonts.check = natif(function check(font, text) {
      const match = font.match(/["']?([^"',]+)["']?\s*$/);
      if (match) {
        const name = match[1].trim();
        if (!osPolices.has(name) && !['serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui'].includes(name)) {
          return false;
        }
      }
      return origCheck(font, text);
    }, 'check');
  }
})();
