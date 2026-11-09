// WebGL spoofing : vendor, renderer, extensions paramétrés par le profil.
(() => {
  const P = window.__NOEZIA_PROFIL__;
  if (!P || !P.gpu_vendor) return;
  const natif = window.__NOEZIA_NATIF__ || (fn => fn);

  const surchargerGL = proto => {
    const origGP = proto.getParameter;
    const origGSE = proto.getSupportedExtensions;
    const origGE = proto.getExtension;

    proto.getParameter = natif(function getParameter(p) {
      if (p === 37445) return P.gpu_vendor;    // UNMASKED_VENDOR_WEBGL
      if (p === 37446) return P.gpu_renderer;  // UNMASKED_RENDERER_WEBGL
      // MAX_TEXTURE_SIZE cohérent avec le GPU (les GPUs intégrés ont des limites plus basses)
      if (p === 3379 && P.gpu_renderer && P.gpu_renderer.includes('Intel')) {
        return 8192;
      }
      return origGP.call(this, p);
    }, 'getParameter');

    proto.getSupportedExtensions = natif(function getSupportedExtensions() {
      if (P.webgl_extensions) return [...P.webgl_extensions];
      return origGSE.call(this);
    }, 'getSupportedExtensions');

    proto.getExtension = natif(function getExtension(name) {
      // Si l'extension n'est pas dans notre liste, retourner null
      if (P.webgl_extensions && !P.webgl_extensions.includes(name)) return null;
      return origGE.call(this, name);
    }, 'getExtension');
  };

  if (typeof WebGLRenderingContext !== 'undefined')
    surchargerGL(WebGLRenderingContext.prototype);
  if (typeof WebGL2RenderingContext !== 'undefined')
    surchargerGL(WebGL2RenderingContext.prototype);
})();
