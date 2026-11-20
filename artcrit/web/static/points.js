// Collect the named points on each image (normalized coordinates) for "Help me measure".
(function () {
  const names = window.POINT_NAMES || [];
  const pts = { photo: [], old: [], new: [] };
  const out = document.getElementById("points");
  const submit = document.getElementById("measure-submit");
  function refresh() {
    document.querySelectorAll(".next-point").forEach((el) => {
      const n = pts[el.dataset.key].length;
      el.textContent = n < names.length ? names[n] : "done";
    });
    out.value = JSON.stringify(pts);
    submit.disabled = !Object.values(pts).every((p) => p.length === names.length);
  }
  document.querySelectorAll(".measure-stage").forEach((stage) => {
    const key = stage.dataset.key, img = stage.querySelector("img");
    stage.addEventListener("click", (e) => {
      const list = pts[key];
      const marker = e.target.classList.contains("pt");
      if (marker) { list.pop(); stage.querySelectorAll(".pt")[list.length].remove(); refresh(); return; }
      if (list.length >= names.length) return;
      const r = img.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      list.push([Math.round(x * 1e4) / 1e4, Math.round(y * 1e4) / 1e4]);
      const dot = document.createElement("span");
      dot.className = "pt"; dot.textContent = list.length;
      dot.style.left = x * 100 + "%"; dot.style.top = y * 100 + "%";
      stage.appendChild(dot);
      refresh();
    });
  });
  refresh();
})();
