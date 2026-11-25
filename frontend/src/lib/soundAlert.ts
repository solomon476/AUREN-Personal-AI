/**
 * Built-in Web Audio API Alert & Alarm Tone Synthesizer for AUREN.
 * Eliminates external MP3 asset dependencies and works reliably offline & in PWA mode.
 * Note: Browsers enforce autoplay gesture unlock; call unlockAudioContext() on first interaction.
 */

export type AlertSoundKey = 'chime' | 'bell' | 'pulse' | 'gentle' | 'silent';

let sharedAudioCtx: AudioContext | null = null;
let activeTimerIds: number[] = [];

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
  if (!AudioCtx) return null;
  if (!sharedAudioCtx) {
    try {
      sharedAudioCtx = new AudioCtx();
    } catch {
      return null;
    }
  }
  if (sharedAudioCtx.state === 'suspended') {
    sharedAudioCtx.resume().catch(() => {});
  }
  return sharedAudioCtx;
}

export function unlockAudioContext(): void {
  const ctx = getAudioContext();
  if (ctx && ctx.state === 'suspended') {
    ctx.resume().catch(() => {});
  }
}

export function stopAlertSound(): void {
  activeTimerIds.forEach((id) => window.clearTimeout(id));
  activeTimerIds = [];
}

function playTone(ctx: AudioContext, freq: number, startOffset: number, duration: number, type: OscillatorType = 'sine', peakGain = 0.22): void {
  const startTime = ctx.currentTime + startOffset;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();

  osc.type = type;
  osc.frequency.setValueAtTime(freq, startTime);

  gain.gain.setValueAtTime(0.0001, startTime);
  gain.gain.exponentialRampToValueAtTime(peakGain, startTime + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);

  osc.connect(gain);
  gain.connect(ctx.destination);

  osc.start(startTime);
  osc.stop(startTime + duration + 0.02);
}

export function playAlertSound(soundKey: string = 'chime', isAlarm: boolean = false): boolean {
  if (soundKey === 'silent') return false;
  const ctx = getAudioContext();
  if (!ctx) return false;

  stopAlertSound();

  const playCycle = () => {
    try {
      switch (soundKey) {
        case 'bell':
          playTone(ctx, 880, 0, 0.45, 'triangle', 0.25);
          playTone(ctx, 1318.5, 0.02, 0.35, 'sine', 0.12);
          break;
        case 'pulse':
          playTone(ctx, 740, 0, 0.16, 'triangle', 0.24);
          playTone(ctx, 740, 0.22, 0.16, 'triangle', 0.24);
          playTone(ctx, 987.77, 0.44, 0.28, 'triangle', 0.26);
          break;
        case 'gentle':
          playTone(ctx, 523.25, 0, 0.25, 'sine', 0.16);
          playTone(ctx, 783.99, 0.18, 0.35, 'sine', 0.16);
          break;
        case 'chime':
        default:
          playTone(ctx, 587.33, 0, 0.22, 'sine', 0.2);
          playTone(ctx, 880, 0.14, 0.32, 'sine', 0.22);
          break;
      }
    } catch {
      // Audio playback blocked by browser autoplay policy before user gesture
    }
  };

  playCycle();

  // For alarm-style alerts, repeat gently at most 2 extra cycles (bounded, never infinite)
  if (isAlarm) {
    const t1 = window.setTimeout(playCycle, 2000);
    const t2 = window.setTimeout(playCycle, 4000);
    activeTimerIds.push(t1, t2);
  }

  return true;
}

