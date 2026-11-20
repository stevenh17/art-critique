// Optional: fade the reference over the drawing. The site reads fine without it.
document.querySelectorAll(".compare").forEach(function (c) {
  var t = c.querySelector(".ov-toggle"), s = c.querySelector(".ov-opacity"), o = c.querySelector(".overlay");
  if (!t || !s || !o) return;
  function apply() { o.hidden = s.hidden = !t.checked; o.style.opacity = s.value / 100; }
  t.addEventListener("change", apply);
  s.addEventListener("input", apply);
});
