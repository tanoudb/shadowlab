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

  // Brouillage des DOMRect (getBoundingClientRect, getClientRects)
  // CreepJS et d'autres utilisent les dimensions exactes de spans de texte
  // pour fingerprinter les polices rendues. Un bruit déterministe par profil
  // rend l'empreinte unique mais stable pour la session.
  function _noiseRect(rect) {
    const n = () => (rand() - 0.5) * 0.15;
    const nx = n(), ny = n(), nw = n(), nh = n();
    return Object.create(DOMRect.prototype, {
      x:      {get: natif(() => rect.x + nx, 'get x'), configurable: true, enumerable: true},
      y:      {get: natif(() => rect.y + ny, 'get y'), configurable: true, enumerable: true},
      width:  {get: natif(() => rect.width + nw, 'get width'), configurable: true, enumerable: true},
      height: {get: natif(() => rect.height + nh, 'get height'), configurable: true, enumerable: true},
      top:    {get: natif(() => rect.top + ny, 'get top'), configurable: true, enumerable: true},
      right:  {get: natif(() => rect.right + nx + nw, 'get right'), configurable: true, enumerable: true},
      bottom: {get: natif(() => rect.bottom + ny + nh, 'get bottom'), configurable: true, enumerable: true},
      left:   {get: natif(() => rect.left + nx, 'get left'), configurable: true, enumerable: true},
      toJSON: {value: natif(function toJSON() {
        return {x: this.x, y: this.y, width: this.width, height: this.height,
                top: this.top, right: this.right, bottom: this.bottom, left: this.left};
      }, 'toJSON')},
    });
  }

  const origGetBCR = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = natif(function getBoundingClientRect() {
    return _noiseRect(origGetBCR.call(this));
  }, 'getBoundingClientRect');

  const origGetCR = Element.prototype.getClientRects;
  Element.prototype.getClientRects = natif(function getClientRects() {
    const rects = origGetCR.call(this);
    const result = [];
    for (let i = 0; i < rects.length; i++) result.push(_noiseRect(rects[i]));
    // DOMRectList-like
    Object.defineProperty(result, 'item', {
      value: natif(function item(idx) { return result[idx] || null; }, 'item'),
    });
    return result;
  }, 'getClientRects');

  // Range.getClientRects/getBoundingClientRect — même bruit que Element
  // Les détecteurs CreepJS utilisent Range au lieu de Element pour contourner les patches.
  const origRangeBCR = Range.prototype.getBoundingClientRect;
  Range.prototype.getBoundingClientRect = natif(function getBoundingClientRect() {
    return _noiseRect(origRangeBCR.call(this));
  }, 'getBoundingClientRect');

  const origRangeGCR = Range.prototype.getClientRects;
  Range.prototype.getClientRects = natif(function getClientRects() {
    const rects = origRangeGCR.call(this);
    const result = [];
    for (let i = 0; i < rects.length; i++) result.push(_noiseRect(rects[i]));
    Object.defineProperty(result, 'item', {
      value: natif(function item(idx) { return result[idx] || null; }, 'item'),
    });
    return result;
  }, 'getClientRects');

  // SVGTextContentElement.getComputedTextLength — fingerprint via SVG
  if (typeof SVGTextContentElement !== 'undefined') {
    const origGCTL = SVGTextContentElement.prototype.getComputedTextLength;
    if (origGCTL) {
      SVGTextContentElement.prototype.getComputedTextLength = natif(function getComputedTextLength() {
        return origGCTL.call(this) + (rand() - 0.5) * 0.2;
      }, 'getComputedTextLength');
    }
  }

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
