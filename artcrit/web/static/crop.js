// Drag a rectangle on the reference photo; writes a normalized box to #photo_crop.
(function () {
  const stage = document.getElementById("crop-stage");
  const img = document.getElementById("crop-img");
  const box = document.getElementById("crop-box");
  const input = document.getElementById("photo_crop");
  if (!stage || !img || !box || !input) return;
  let b = JSON.parse(input.value);
  function draw() {
    box.style.left = b[0] * 100 + "%"; box.style.top = b[1] * 100 + "%";
    box.style.width = (b[2] - b[0]) * 100 + "%"; box.style.height = (b[3] - b[1]) * 100 + "%";
    box.style.right = "auto"; box.style.bottom = "auto";
    input.value = JSON.stringify(b.map(v => Math.round(v * 1000) / 1000));
  }
  const clamp = (v) => Math.min(Math.max(v, 0), 1);
  stage.addEventListener("pointerdown", (e) => {
    if (e.target !== img) return;
    e.preventDefault();
    stage.setPointerCapture(e.pointerId);
    const r = img.getBoundingClientRect();
    const x0 = clamp((e.clientX - r.left) / r.width), y0 = clamp((e.clientY - r.top) / r.height);
    const move = (ev) => {
      const x1 = clamp((ev.clientX - r.left) / r.width), y1 = clamp((ev.clientY - r.top) / r.height);
      b = [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)];
      draw();
    };
    const up = () => {
      stage.removeEventListener("pointermove", move); stage.removeEventListener("pointerup", up);
      if (b[2] - b[0] < 0.02 || b[3] - b[1] < 0.02) { b = [0, 0, 1, 1]; draw(); }
    };
    stage.addEventListener("pointermove", move);
    stage.addEventListener("pointerup", up);
  });
  draw();
})();
