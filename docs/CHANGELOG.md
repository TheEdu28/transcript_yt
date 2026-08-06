# Changelog

Este archivo registra los incrementos funcionales del prototipo de tesis.

## Sprint 2 - HU-03 y HU-05

### Implementado

- Recuperación de chunks relevantes indexados en ChromaDB para construir el contexto RAG del resumen.
- Presupuesto estricto de caracteres de contexto antes de llamar a Gemini, para proteger la capa gratuita.
- Contrato estructurado de sinopsis, glosario y bloques didácticos con timestamps `HH:MM:SS`.
- Verificación posterior: cada timestamp generado debe coincidir con un límite temporal de la evidencia recuperada.
- Rechazo controlado de JSON inválido, sinopsis de más de 200 palabras y respuestas inconsistentes por evidencia insuficiente.
- Pruebas unitarias sin proveedores externos para contexto limitado, timestamps fundamentados y errores de salida.

### Pendiente

- Sprint 3: HU-04, cuestionario de autoevaluación con evidencia temporal.

## Sprint 1 - HU-01 y HU-10

### Implementado

- Validación previa a la descarga de URLs de videos YouTube, excluyendo listas de reproducción y dominios ajenos.
- Verificación de acceso público, rechazo de transmisiones en vivo y error específico para videos privados/no disponibles.
- Restricción configurable de duración máxima de 60 minutos.
- Aceptación exclusiva de contenido declarado en español o inglés, incluyendo metadatos de subtítulos.
- Pruebas unitarias sin dependencias de red para URL, visibilidad, idioma y duración.

### Pendiente

- Sprint 2: HU-03 y HU-05, resumen estructurado y anclaje temporal mediante RAG.
