// AudioContext fingerprint noise : bruit paramétré par le seed audio du profil.
(() => {
  const P = window.__NOEZIA_PROFIL__;
  if (!P || !P.audio_seed) return;
  const natif = window.__NOEZIA_NATIF__ || (fn => fn);

  // PRNG indépendant du canvas (seed différent)
  let state = P.audio_seed >>> 0;
  function xorshift() {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 0xFFFFFFFF;
  }

  if (typeof OfflineAudioContext !== 'undefined') {
    const origSR = OfflineAudioContext.prototype.startRendering;
    OfflineAudioContext.prototype.startRendering = natif(function startRendering() {
      return origSR.call(this).then(buf => {
        try {
          const d = buf.getChannelData(0);
          // Réinitialiser au seed audio pour reproductibilité par profil
          state = P.audio_seed >>> 0;
          // Bruit infime : ~1e-7, suffisant pour changer le hash
          for (let i = 0; i < d.length; i++) {
            d[i] += (xorshift() - 0.5) * 1e-7;
          }
        } catch(e) {}
        return buf;
      });
    }, 'startRendering');
  }

  // AudioContext.prototype.getOutputTimestamp — certains détecteurs l'utilisent
  if (typeof AudioContext !== 'undefined' && AudioContext.prototype.getOutputTimestamp) {
    const origTS = AudioContext.prototype.getOutputTimestamp;
    AudioContext.prototype.getOutputTimestamp = natif(function getOutputTimestamp() {
      const ts = origTS.call(this);
      // Micro-décalage basé sur le seed
      state = P.audio_seed >>> 0;
      xorshift(); // avancer le PRNG
      ts.contextTime += (xorshift() - 0.5) * 1e-8;
      return ts;
    }, 'getOutputTimestamp');
  }
})();
