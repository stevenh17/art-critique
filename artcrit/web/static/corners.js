// Draggable four-corner handles over the drawing; writes corners (image pixels) to #corners.
(function () {
  const stage = document.getElementById("corner-stage");
  const img = document.getElementById("corner-img");
  const input = document.getElementById("corners");
  if (!stage || !img || !input) return;
  let pts = JSON.parse(input.value);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("corner-svg");
  const poly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
  poly.setAttribute("fill", "rgba(200,69,47,.08)");
  poly.setAttribute("stroke", "#c8452f");
  poly.setAttribute("stroke-width", "2");
  svg.appendChild(poly);
  stage.appendChild(svg);
  const handles = pts.map(() => { const h = document.createElement("div"); h.className = "handle"; stage.appendChild(h); return h; });

  function scale() { return img.clientWidth / img.naturalWidth; }
  function draw() {
    const s = scale();
    handles.forEach((h, i) => { h.style.left = pts[i][0] * s + "px"; h.style.top = pts[i][1] * s + "px"; });
    svg.setAttribute("viewBox", `0 0 ${img.clientWidth} ${img.clientHeight}`);
    poly.setAttribute("points", pts.map(p => `${p[0] * s},${p[1] * s}`).join(" "));
    input.value = JSON.stringify(pts.map(p => [Math.round(p[0]), Math.round(p[1])]));
  }
  handles.forEach((h, i) => {
    h.addEventListener("pointerdown", (e) => {
      h.setPointerCapture(e.pointerId);
      const move = (ev) => {
        const r = img.getBoundingClientRect(), s = scale();
        pts[i] = [Math.min(Math.max(ev.clientX - r.left, 0), r.width) / s, Math.min(Math.max(ev.clientY - r.top, 0), r.height) / s];
        draw();
      };
      const up = () => { h.removeEventListener("pointermove", move); h.removeEventListener("pointerup", up); };
      h.addEventListener("pointermove", move);
      h.addEventListener("pointerup", up);
    });
  });
  if (img.complete) draw(); else img.addEventListener("load", draw);
  window.addEventListener("resize", draw);
})();
