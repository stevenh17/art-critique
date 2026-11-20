// Fade the cropped reference over the drawing (simple resize; best-fit alignment comes in Plan 2).
(function () {
  const toggle = document.getElementById("overlay-toggle");
  const slider = document.getElementById("overlay-opacity");
  const img = document.getElementById("overlay-img");
  if (!toggle || !slider || !img) return;
  const apply = () => {
    img.hidden = slider.hidden = !toggle.checked;
    img.style.opacity = slider.value / 100;
  };
  toggle.addEventListener("change", apply);
  slider.addEventListener("input", apply);
})();
