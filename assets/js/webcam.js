/* Webcam + MediaPipe Face Landmarker helpers shared by the two webcam demos.
   Everything runs locally in the browser; frames are never uploaded. */
(function () {
  "use strict";
  const VERSION = "0.10.14";
  const BASE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}`;
  const MODEL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

  async function start(video) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error("This browser has no camera API (or the page is not served over HTTPS).");
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user", frameRate: { ideal: 30 } }, audio: false });
    video.srcObject = stream; video.muted = true; video.playsInline = true;
    await video.play();
    return stream;
  }
  function stop(video) {
    const s = video.srcObject; if (s) s.getTracks().forEach((t) => t.stop()); video.srcObject = null;
  }
  async function landmarker(opts) {
    opts = opts || {};
    const { FaceLandmarker, FilesetResolver } = await import(`${BASE}/+esm`);
    const fileset = await FilesetResolver.forVisionTasks(`${BASE}/wasm`);
    const make = (delegate) => FaceLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: MODEL, delegate }, runningMode: "VIDEO", numFaces: 1,
      outputFaceBlendshapes: !!opts.blendshapes, outputFacialTransformationMatrixes: false,
    });
    try { return await make("GPU"); } catch (e) { console.warn("GPU delegate unavailable, using CPU", e); return await make("CPU"); }
  }
  /** run fn(now_ms) once per video frame (uses requestVideoFrameCallback when available) */
  function onFrame(video, fn) {
    let alive = true;
    const tick = (now) => { if (!alive) return; fn(now); schedule(); };
    const schedule = () => (video.requestVideoFrameCallback ? video.requestVideoFrameCallback((n) => tick(n)) : requestAnimationFrame(tick));
    schedule();
    return () => { alive = false; };
  }
  window.Webcam = { start, stop, landmarker, onFrame };
})();
