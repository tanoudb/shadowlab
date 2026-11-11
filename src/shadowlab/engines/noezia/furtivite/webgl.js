// WebGL fingerprint hardening : paramètres GPU corrélés, precision shader, readPixels noise.
// Le GPU déclaré dans le profil doit être indistinguable du vrai GPU à travers
// toutes les API WebGL : getParameter (20+ params), getShaderPrecisionFormat, readPixels.
//
// Problème résolu : notre navigateur tourne sur le GPU réel de la machine hôte
// (Apple Metal sur Mac, SwiftShader sur un serveur Linux sans GPU)
// mais on déclare des GPU différents (NVIDIA, Intel, AMD). Sans ce script, un détecteur
// qui croise le renderer avec MAX_VERTEX_ATTRIBS ou la précision mediump voit la faille.
(() => {
  const P = window.__NOEZIA_PROFIL__;
  if (!P || !P.gpu_vendor) return;
  const natif = window.__NOEZIA_NATIF__ || (fn => fn);

  // PRNG xorshift32 pour le bruit readPixels (déterministe par profil + contenu)
  let _seed = (P.canvas_seed || 12345) >>> 0;
  function xorshift() {
    _seed ^= _seed << 13;
    _seed ^= _seed >>> 17;
    _seed ^= _seed << 5;
    return (_seed >>> 0) / 0xFFFFFFFF;
  }

  // ── Détection du backend GPU réel ──────────────────────────────
  // Sur un serveur Linux sans GPU, Chromium utilise Google SwiftShader (logiciel).
  // Ses limites WebGL (MAX_TEXTURE_SIZE=8192, pas de multisampling, SUBPIXEL_BITS=4)
  // trahissent un bot si elles fuient via des paramètres non couverts par GP.
  let _isSwiftShader = false;
  let _realExtensions = null;
  try {
    const _c = document.createElement('canvas');
    const _g = _c.getContext('webgl');
    if (_g) {
      const _d = _g.getExtension('WEBGL_debug_renderer_info');
      if (_d) {
        const _r = _g.getParameter(_d.UNMASKED_RENDERER_WEBGL);
        _isSwiftShader = typeof _r === 'string' && _r.includes('SwiftShader');
      }
      _realExtensions = new Set(_g.getSupportedExtensions() || []);
      const _l = _g.getExtension('WEBGL_lose_context');
      if (_l) _l.loseContext();
    }
  } catch(e) {}

  // ── Classification GPU depuis le renderer string du PROFIL ─────
  const rend = P.gpu_renderer || '';
  const isApple = rend.includes('Apple');
  const isIntel = rend.includes('Intel');
  const isNVIDIA = rend.includes('NVIDIA');
  const isD3D11 = rend.includes('D3D11') || rend.includes('Direct3D');
  const isMesa = rend.includes('Mesa');
  // ANGLE + OpenGL sans D3D11 ni Mesa (ex : NVIDIA Linux via ANGLE/OpenGL)
  const isLinuxGL = !isD3D11 && !isApple && !isMesa
    && (rend.includes('OpenGL') || (rend.includes('ANGLE') && !rend.includes('Metal')));

  // ── Paramètres WebGL corrélés au GPU déclaré ─────────────────────
  // Valeurs mesurées sur Chrome/ANGLE par famille de GPU réelle.
  // Clés = constantes WebGL (numéros stables, pas de noms).
  const GP = {};

  if (isApple) {
    // Apple Metal : vertex_attribs=31 (Metal max), varying=31, point_size max=511, samples=4
    GP[3379]  = 16384;   GP[34076] = 16384;   GP[34024] = 16384;  // MAX_TEXTURE/CUBE/RENDERBUFFER
    GP[34921] = 31;      GP[36347] = 4096;    GP[36348] = 31;     // VERTEX_ATTRIBS/UNIFORM/VARYING
    GP[35661] = 32;      GP[35660] = 16;      GP[34930] = 16;     // COMBINED/VERTEX/FRAG TEX UNITS
    GP[36349] = 1024;    GP[36183] = 4;                            // FRAG_UNIFORM / MAX_SAMPLES
    GP[34852] = 8;       GP[36063] = 8;                            // DRAW_BUFFERS / COLOR_ATTACHMENTS
    GP[32883] = 2048;                                              // MAX_3D_TEXTURE_SIZE (WebGL2)
    GP[3386]  = new Int32Array([16384, 16384]);                    // MAX_VIEWPORT_DIMS
    GP[33902] = new Float32Array([1, 1]);                          // ALIASED_LINE_WIDTH_RANGE
    GP[33901] = new Float32Array([1, 511]);                        // ALIASED_POINT_SIZE_RANGE
  } else if (isD3D11) {
    // D3D11 (Windows) : vertex_attribs=16, varying=32, point_size=1024
    GP[3379]  = 16384;   GP[34076] = 16384;   GP[34024] = 16384;
    GP[34921] = 16;      GP[36347] = 4096;    GP[36348] = 32;
    GP[35661] = 32;      GP[35660] = 16;      GP[34930] = 16;
    GP[36349] = 1024;    GP[36183] = isIntel ? 4 : 8;
    GP[34852] = 8;       GP[36063] = 8;
    GP[32883] = 2048;
    GP[3386]  = new Int32Array([16384, 16384]);
    GP[33902] = new Float32Array([1, 1]);
    GP[33901] = new Float32Array([1, 1024]);
  } else if (isMesa || isLinuxGL) {
    // Mesa/Linux (OpenGL backend) — couvre aussi ANGLE+OpenGL (NVIDIA Linux)
    GP[3379]  = 16384;   GP[34076] = 16384;   GP[34024] = 16384;
    GP[34921] = 16;      GP[36347] = 4096;    GP[36348] = 32;
    GP[35661] = 32;      GP[35660] = 16;      GP[34930] = 16;
    GP[36349] = 1024;    GP[36183] = isNVIDIA ? 8 : 4;
    GP[34852] = 8;       GP[36063] = 8;
    GP[32883] = 2048;
    GP[3386]  = new Int32Array([16384, 16384]);
    GP[33902] = new Float32Array([1, 1]);
    GP[33901] = new Float32Array([1, isNVIDIA ? 1024 : 511]);
  }

  // ── SwiftShader : paramètres supplémentaires pour colmater les fuites ──
  // SwiftShader a des limites distinctes sur des paramètres non couverts ci-dessus.
  // Sans cette section, origGP.call() retourne les vraies valeurs SwiftShader
  // et un détecteur qui croise renderer="Mesa Intel" avec SUBPIXEL_BITS=4 détecte le bot.
  if (_isSwiftShader && !isApple) {
    GP[3408]  = 8;            // SUBPIXEL_BITS (SwiftShader=4, vrais GPUs desktop=8)
    GP[32824] = 2147483647;   // MAX_ELEMENTS_VERTICES (SwiftShader=65536)
    GP[32825] = 2147483647;   // MAX_ELEMENTS_INDICES  (SwiftShader=65536)
    GP[35071] = 16;           // MAX_TEXTURE_LOD_BIAS  (SwiftShader=2)
    GP[35373] = 2048;         // MAX_ARRAY_TEXTURE_LAYERS (WebGL2)
    GP[35657] = isNVIDIA ? 16 : 12;  // MAX_VERTEX_UNIFORM_BLOCKS (WebGL2)
    GP[35658] = isNVIDIA ? 16 : 12;  // MAX_FRAGMENT_UNIFORM_BLOCKS (WebGL2)
    GP[35371] = 72;           // MAX_UNIFORM_BUFFER_BINDINGS (WebGL2)
    GP[35376] = 65536;        // MAX_UNIFORM_BLOCK_SIZE (WebGL2)
    GP[35968] = 4;            // MAX_TRANSFORM_FEEDBACK_SEPARATE_ATTRIBS (WebGL2)
    GP[36203] = 128;          // MAX_VERTEX_OUTPUT_COMPONENTS (WebGL2)
    GP[36211] = 128;          // MAX_FRAGMENT_INPUT_COMPONENTS (WebGL2)
  }

  // ── Filtrer les extensions du profil contre le backend réel ──────
  // Si le profil déclare des extensions que le backend ne supporte pas,
  // getExtension() retournerait null en contradiction avec getSupportedExtensions().
  // On ne déclare que ce que le backend peut réellement fournir.
  if (P.webgl_extensions && _realExtensions) {
    P.webgl_extensions = P.webgl_extensions.filter(ext => _realExtensions.has(ext));
  }

  // ── Precision shader corrélée au backend GPU ─────────────────────
  // Apple Metal a un vrai mediump (half-float, precision=10).
  // D3D11/Mesa desktop : mediump = highp (precision=23, pas de vraie demi-précision).
  // C'est un signal très discriminant — un "NVIDIA D3D11" avec mediump=10 est impossible.
  const _p = (rm, rM, p) => ({rangeMin: rm, rangeMax: rM, precision: p});
  const PREC = {};
  if (isApple) {
    PREC[0x8DF0] = _p(1, 1, 8);       // LOW_FLOAT
    PREC[0x8DF1] = _p(14, 14, 10);    // MEDIUM_FLOAT — half-float réel sur Metal
    PREC[0x8DF2] = _p(127, 127, 23);  // HIGH_FLOAT
    PREC[0x8DF3] = _p(8, 8, 0);       // LOW_INT
    PREC[0x8DF4] = _p(10, 10, 0);     // MEDIUM_INT
    PREC[0x8DF5] = _p(16, 16, 0);     // HIGH_INT
  } else {
    // D3D11, Mesa et SwiftShader desktop : pas de vrai mediump
    PREC[0x8DF0] = _p(127, 127, 23);
    PREC[0x8DF1] = _p(127, 127, 23);
    PREC[0x8DF2] = _p(127, 127, 23);
    PREC[0x8DF3] = _p(31, 30, 0);
    PREC[0x8DF4] = _p(31, 30, 0);
    PREC[0x8DF5] = _p(31, 30, 0);
  }

  // ── Override sur les deux contextes (WebGL1 + WebGL2) ────────────

  const surchargerGL = proto => {
    const origGP = proto.getParameter;
    const origGSE = proto.getSupportedExtensions;
    const origGE = proto.getExtension;
    const origRP = proto.readPixels;
    const origSPF = proto.getShaderPrecisionFormat;

    // getParameter — tous les paramètres corrélés au GPU
    proto.getParameter = natif(function getParameter(p) {
      if (p === 37445) return P.gpu_vendor;    // UNMASKED_VENDOR_WEBGL
      if (p === 37446) return P.gpu_renderer;  // UNMASKED_RENDERER_WEBGL
      if (p === 7936) return 'WebKit';         // GL_VENDOR (constant Chrome)
      if (p === 7937) return 'WebKit WebGL';   // GL_RENDERER (constant Chrome)
      const v = GP[p];
      if (v !== undefined) {
        // Copie pour les typed arrays (empêche la détection par mutation)
        if (v instanceof Float32Array) return new Float32Array(v);
        if (v instanceof Int32Array) return new Int32Array(v);
        return v;
      }
      return origGP.call(this, p);
    }, 'getParameter');

    // getSupportedExtensions — liste du profil (déjà filtrée contre le backend)
    proto.getSupportedExtensions = natif(function getSupportedExtensions() {
      if (P.webgl_extensions) return [...P.webgl_extensions];
      return origGSE.call(this);
    }, 'getSupportedExtensions');

    // getExtension — cohérent avec la liste
    proto.getExtension = natif(function getExtension(name) {
      if (P.webgl_extensions && !P.webgl_extensions.includes(name)) return null;
      return origGE.call(this, name);
    }, 'getExtension');

    // getShaderPrecisionFormat — précision corrélée au backend GPU
    proto.getShaderPrecisionFormat = natif(function getShaderPrecisionFormat(shaderType, precisionType) {
      const orig = origSPF.call(this, shaderType, precisionType);
      if (!orig) return orig;
      const p = PREC[precisionType];
      if (p) return {rangeMin: p.rangeMin, rangeMax: p.rangeMax, precision: p.precision};
      return orig;
    }, 'getShaderPrecisionFormat');

    // readPixels — bruit déterministe (fingerprint du rendu WebGL)
    // Un détecteur dessine une scène et lit les pixels — le résultat est GPU-specific.
    // On ajoute un bruit seed-based pour que chaque profil ait un hash unique et stable.
    proto.readPixels = natif(function readPixels() {
      origRP.apply(this, arguments);
      const pixels = arguments[6];
      if (!pixels || !(pixels instanceof Uint8Array) || pixels.length < 16) return;
      // Seed = profil XOR contenu (même scène → même bruit → même hash)
      let s = (P.canvas_seed || 1) >>> 0;
      for (let i = 0; i < Math.min(16, pixels.length); i++) s = (s * 31 + pixels[i]) >>> 0;
      _seed = s || 1;
      const len = Math.min(pixels.length, 4096);
      for (let i = 0; i < len; i += 4) {
        if (xorshift() < 0.2) {
          const c = (xorshift() * 3) | 0;
          const d = xorshift() < 0.5 ? 1 : -1;
          pixels[i + c] = Math.max(0, Math.min(255, pixels[i + c] + d));
        }
      }
    }, 'readPixels');
  };

  if (typeof WebGLRenderingContext !== 'undefined') surchargerGL(WebGLRenderingContext.prototype);
  if (typeof WebGL2RenderingContext !== 'undefined') surchargerGL(WebGL2RenderingContext.prototype);
})();
