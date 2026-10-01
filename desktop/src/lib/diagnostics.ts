export const diagnosticOptions = window.shotlogfixer?.diagnostics;
export const diagnosticsEnabled = import.meta.env.DEV || Boolean(diagnosticOptions);
const counters: Record<string, number> = {};
const snapshot = { ticks: 0, frames: 0, lastTick: 0, phase: "startup", counters };

export function diagnosticPhase(phase: string) {
  if (!diagnosticsEnabled) return;
  snapshot.phase = phase;
  // Phase messages survive a subsequent block before the next heartbeat.
  diagnosticOptions?.report({ ...snapshot, counters: { ...counters } });
}

export function useRenderDiagnostics(component: string) {
  if (diagnosticsEnabled) counters[`${component}.render`] = (counters[`${component}.render`] || 0) + 1;
}

export function startRendererDiagnostics() {
  if (!diagnosticsEnabled) return;
  window.shotlogfixerHeartbeat = () => ({ ...snapshot, counters: { ...counters } });
  const timer = window.setInterval(() => {
    snapshot.ticks++;
    snapshot.lastTick = performance.now();
    diagnosticOptions?.report(window.shotlogfixerHeartbeat!());
  }, 250);
  let frame = 0;
  const onFrame = () => { snapshot.frames++; frame = requestAnimationFrame(onFrame); };
  frame = requestAnimationFrame(onFrame);
  window.addEventListener("error", (event) => diagnosticPhase(`error: ${event.message}`));
  window.addEventListener("unhandledrejection", (event) => diagnosticPhase(`unhandledrejection: ${String(event.reason)}`));
  window.addEventListener("pagehide", () => { clearInterval(timer); cancelAnimationFrame(frame); }, { once: true });
}
