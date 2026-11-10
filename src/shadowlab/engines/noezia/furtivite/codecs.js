// Évasion media codecs — Chromium headless ne supporte pas les codecs propriétaires.
// Un vrai Chrome retourne "probably" pour H.264 (avc1), "maybe" pour x-m4a, "probably" pour AAC.
// Sans ce patch, canPlayType('video/mp4; codecs="avc1.42E01E"') retourne "" au lieu de "probably".
// Technique : puppeteer-extra-plugin-stealth/evasions/media.codecs (adaptée).
(() => {
  const natif = window.__NOEZIA_NATIF__;
  if (!natif) return;


  const origCanPlayType = HTMLMediaElement.prototype.canPlayType;

  HTMLMediaElement.prototype.canPlayType = natif(function canPlayType(mediaType) {
    if (!mediaType) return origCanPlayType.call(this, mediaType);
    const [mime, codecStr] = mediaType.trim().split(';');
    const codecs = codecStr && codecStr.includes('codecs="')
      ? codecStr.trim().replace('codecs="', '').replace('"', '').trim().split(',').map(c => c.trim()).filter(Boolean)
      : [];

    if (mime === 'video/mp4' && codecs.some(c => c.startsWith('avc1'))) return 'probably';
    if (mime === 'audio/x-m4a' && !codecs.length) return 'maybe';
    if (mime === 'audio/aac' && !codecs.length) return 'probably';
    if (mime === 'audio/mpeg' && !codecs.length) return 'probably';

    return origCanPlayType.call(this, mediaType);
  }, 'canPlayType');
})();
