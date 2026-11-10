// Évasion iframe.contentWindow — empêche la détection via iframes srcdoc.
// Les détecteurs créent des iframes pour vérifier que window.chrome, navigator.plugins etc.
// existent aussi dans le contexte enfant. Sans ce patch, les iframes srcdoc créées
// dynamiquement n'héritent pas de nos overrides.
// Technique : puppeteer-extra-plugin-stealth/evasions/iframe.contentWindow (adaptée).
(() => {
  const natif = window.__NOEZIA_NATIF__;
  if (!natif) return;


  const addContentWindowProxy = iframe => {
    const handler = {
      get(target, key) {
        if (key === 'self') return this;
        if (key === 'frameElement') return iframe;
        if (key === '0') return undefined;
        return Reflect.get(target, key);
      }
    };
    if (!iframe.contentWindow) {
      const proxy = new Proxy(window, handler);
      Object.defineProperty(iframe, 'contentWindow', {
        get() { return proxy; },
        set(v) { return v; },
        enumerable: true,
        configurable: false,
      });
    }
  };

  const handleIframeCreation = (target, thisArg, args) => {
    const iframe = target.apply(thisArg, args);
    const origSrcdoc = iframe.srcdoc;
    Object.defineProperty(iframe, 'srcdoc', {
      configurable: true,
      get() { return origSrcdoc; },
      set(v) {
        addContentWindowProxy(this);
        Object.defineProperty(iframe, 'srcdoc', {
          configurable: false, writable: false, value: origSrcdoc,
        });
        iframe.srcdoc = v;
      },
    });
    return iframe;
  };

  const origCreateElement = document.createElement.bind(document);
  document.createElement = natif(function createElement() {
    const tag = arguments[0];
    if (tag && String(tag).toLowerCase() === 'iframe') {
      return handleIframeCreation(origCreateElement, document, arguments);
    }
    return origCreateElement.apply(document, arguments);
  }, 'createElement');
})();
