// Interacciones de la plataforma.
//
// Este archivo existe por una razón de seguridad, no de estilo: la CSP de
// `security.py` usa `script-src 'self'`, que bloquea el JavaScript escrito
// dentro del HTML. Los `onsubmit="return confirm(...)"` que había antes en
// las plantillas NO se ejecutaban, así que las acciones destructivas
// (eliminar una propiedad, terminar un arrendamiento, cerrar sesiones) se
// realizaban sin preguntar nada.
//
// La confirmación ahora se declara con un atributo `data-confirm` en el
// formulario y se conecta desde aquí, que sí es un archivo propio y la CSP
// permite.
(function () {
  "use strict";

  // Confirmación antes de enviar un formulario destructivo.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var message = form.getAttribute("data-confirm");
      if (message && !window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  // Menú lateral en móvil: se abre y cierra con el botón del encabezado.
  var toggle = document.querySelector("[data-sidebar-toggle]");
  var shell = document.querySelector(".app-shell");
  if (toggle && shell) {
    toggle.addEventListener("click", function () {
      var open = shell.classList.toggle("sidebar-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    // Cerrar al elegir una opción, para que en móvil no tape el contenido.
    document.querySelectorAll(".sidebar-nav a").forEach(function (link) {
      link.addEventListener("click", function () {
        shell.classList.remove("sidebar-open");
      });
    });
  }
})();
