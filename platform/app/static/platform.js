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

  // «Ver contraseña» (punto 3.1 del CEO).
  //
  // Por delegación en el documento y no atando un manejador a cada botón:
  // así funciona también en formularios que se pinten después, y es un solo
  // manejador en vez de uno por campo.
  //
  // Solo cambia el `type` del campo. No copia el valor a ningún sitio, no lo
  // guarda y no lo manda a ninguna parte: lo que se ve en pantalla es el
  // mismo campo de siempre, y el gestor de contraseñas del navegador lo sigue
  // reconociendo porque `name` y `autocomplete` no se tocan.
  document.addEventListener("click", function (event) {
    var boton = event.target.closest("[data-pw-toggle]");
    if (!boton) return;
    var campo = document.getElementById(boton.getAttribute("data-pw-toggle"));
    if (!campo) return;

    var mostrando = campo.type === "text";
    campo.type = mostrando ? "password" : "text";
    if (mostrando) {
      campo.removeAttribute("data-was-password");
    } else {
      // Marca para poder volver a ocultarlo al enviar el formulario.
      campo.setAttribute("data-was-password", "1");
    }
    // El botón es solo un icono (lo pinta el CSS según `aria-pressed`), así
    // que lo único que cambia aquí es el estado y la etiqueta accesible. Sin
    // `aria-label` el botón sería un cuadro mudo para un lector de pantalla.
    boton.setAttribute("aria-pressed", mostrando ? "false" : "true");
    boton.setAttribute("aria-label", mostrando ? "Mostrar la contraseña" : "Ocultar la contraseña");

    // Devolver el foco al campo y dejar el cursor al final: si no, al pulsar
    // el botón se pierde el sitio donde se estaba escribiendo.
    campo.focus();
    try {
      var n = campo.value.length;
      campo.setSelectionRange(n, n);
    } catch (e) {
      // Algunos navegadores no admiten setSelectionRange según el tipo.
    }
  });

  // Una contraseña visible no debe quedarse en pantalla al enviar el
  // formulario ni al salir de la página.
  document.addEventListener("submit", function () {
    document.querySelectorAll("input[type='text'][data-was-password]").forEach(function (campo) {
      campo.type = "password";
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
