// Canvas fingerprint noise : bruit paramétré par le seed du profil.
// Chaque profil a un seed unique → un hash canvas unique et persistant.
// Le bruit est subtil mais suffisant pour changer le hash sans casser l'image.
(() => {
  const P = window.__NOEZIA_PROFIL__;
  if (!P || !P.canvas_seed) return;
  const natif = window.__NOEZIA_NATIF__ || (fn => fn);

  // PRNG : xorshift32 (rapide, déterministe, seed du profil)
  let state = P.canvas_seed >>> 0;
  function xorshift() {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 0xFFFFFFFF;
  }

  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  const origToBlob = HTMLCanvasElement.prototype.toBlob;
  const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;

  function bruiter(source) {
    try {
      const w = source.width, h = source.height;
      if (w <= 0 || h <= 0) return null;
      const tmp = document.createElement('canvas');
      tmp.width = w; tmp.height = h;
      const ctx = tmp.getContext('2d');
      ctx.drawImage(source, 0, 0);

      // Bruit sur une zone limitée mais représentative
      const sw = Math.min(w, 128), sh = Math.min(h, 128);
      const img = origGetImageData.call(ctx, 0, 0, sw, sh);
      const d = img.data;

      // Réinitialiser le PRNG au seed pour ce canvas
      state = P.canvas_seed >>> 0;

      // Bruit non-uniforme : concentré sur certains pixels (pattern du profil)
      for (let i = 0; i < d.length; i += 4) {
        const r = xorshift();
        if (r < 0.3) {
          // Modifier un seul canal (R, G ou B) de ±1 ou ±2
          const canal = (xorshift() * 3) | 0;
          const delta = xorshift() < 0.8 ? 1 : 2;
          const signe = xorshift() < 0.5 ? 1 : -1;
          d[i + canal] = Math.max(0, Math.min(255, d[i + canal] + signe * delta));
        }
      }
      ctx.putImageData(img, 0, 0);
      return tmp;
    } catch(e) { return null; }
  }

  function _nettoyer_stack(e) {
    if (e && e.stack) {
      e.stack = e.stack.split('\n').filter(l => !l.includes('<anonymous>')).join('\n');
    }
    return e;
  }

  HTMLCanvasElement.prototype.toDataURL = natif(function toDataURL() {
    try {
      const b = bruiter(this);
      return origToDataURL.apply(b || this, arguments);
    } catch(e) { throw _nettoyer_stack(e); }
  }, 'toDataURL');

  HTMLCanvasElement.prototype.toBlob = natif(function toBlob() {
    try {
      const b = bruiter(this);
      return origToBlob.apply(b || this, arguments);
    } catch(e) { throw _nettoyer_stack(e); }
  }, 'toBlob');

  // getImageData aussi, pour les détecteurs qui lisent les pixels directement
  CanvasRenderingContext2D.prototype.getImageData = natif(function getImageData(sx, sy, sw, sh) {
    const data = origGetImageData.call(this, sx, sy, sw, sh);
    // Bruit léger sur les données brutes
    state = P.canvas_seed >>> 0;
    const d = data.data;
    for (let i = 0; i < Math.min(d.length, 4096); i += 4) {
      if (xorshift() < 0.15) {
        const canal = (xorshift() * 3) | 0;
        d[i + canal] = Math.max(0, Math.min(255, d[i + canal] + (xorshift() < 0.5 ? 1 : -1)));
      }
    }
    return data;
  }, 'getImageData');
})();
