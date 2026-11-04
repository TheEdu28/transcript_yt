# Original User Request

## Initial Request — 2026-11-04T04:09:24Z

Implementar mejoras funcionales y correcciones en la aplicación transcript_yt para un entorno de producción, garantizando la correcta separación de roles entre profesores y alumnos, la gestión individual de intentos y calificaciones por actividad, la búsqueda y ordenamiento de videos, el control de acceso en cuestionarios y resúmenes, y la calibración precisa de timestamps.

Working directory: c:\Users\jesus\OneDrive\Documentos\ChatGPT\transcript_yt 2
Integrity mode: demo
The team must NOT: Run external scripts or delegate execution to other tools.

## Requirements

### R1. Sistema de calificaciones centrado en cada actividad
El profesor debe poder entrar a una actividad específica y consultar la lista de alumnos que la han realizado, revisar los intentos y respuestas individuales de cada alumno, y asignar o modificar la calificación individual desde ese mismo apartado. Las calificaciones deben quedar asociadas al alumno y a la actividad correspondiente, permitiendo identificar fácilmente quién ya fue calificado y quién tiene una calificación pendiente, sin depender de un panel general para realizar la acción principal de calificar.

### R2. Separación de intentos individuales por usuario
Cada alumno debe visualizar únicamente la cantidad de intentos que él mismo ha realizado en la actividad o cuestionario. El profesor debe poder consultar los intentos de cada alumno de manera individual (al consultar el perfil o resultados de un alumno, solo se deben mostrar sus intentos). Los intentos deben relacionarse correctamente en el backend y la base de datos con el usuario, la actividad y el cuestionario correspondiente, asegurando que no se mezclen los intentos de diferentes alumnos ni se dependa únicamente de un contador en el frontend.

### R3. Selección, ordenamiento y búsqueda de videos
El sistema debe mostrar los videos ordenados inicialmente del más reciente al más antiguo según las fechas reales de publicación o registro disponibles (sin sustituir el orden cronológico por orden alfabético), permitiendo alternar entre más recientes primero y más antiguos primero. Debe incorporarse un campo de búsqueda por texto sobre el título del video que funcione conjuntamente con el ordenamiento, sin pérdida de datos ni errores en la selección.

### R4. Control y separación de cuestionarios con respuestas y sin respuestas por roles
El profesor debe disponer de dos versiones del cuestionario mediante un selector o control visual que actualice el contenido y los botones de exportación de inmediato:
- Versión con respuestas: muestra todas las preguntas, opciones, identifica respuestas correctas y permite exportar con respuestas.
- Versión sin respuestas: muestra preguntas y opciones, pero oculta respuestas correctas y cualquier indicador identificativo, y permite exportar sin respuestas.
El alumno solo debe poder visualizar y exportar el cuestionario sin respuestas, sin acceso al selector y con restricción tanto en frontend como en backend (la API no debe exponer las respuestas correctas a alumnos bajo ninguna petición directa).

### R5. Separación de resúmenes del profesor y del alumno
El resumen oficial del profesor debe estar asociado a la actividad, ser consultable por los alumnos, pero no modificable, reemplazable ni regenerable por ellos. El alumno debe contar con un espacio independiente para generar y consultar su propio resumen personal asociado exclusivamente a su cuenta y actividad, sin sobrescribir el resumen oficial ni afectar a otros usuarios. El profesor debe poder distinguir con claridad el resumen oficial de los resúmenes personales de los alumnos en backend, base de datos y frontend.

### R6. Calibración y corrección de timestamps en cuestionarios
El mecanismo de asignación de timestamps para las preguntas de los cuestionarios debe asegurar que el timestamp dirija al alumno a un momento ligeramente anterior al inicio de la explicación del tema (con un margen aproximado de 5 a 10 segundos previos a la explicación relevante), evitando marcas lejanas o menciones superficiales. El ajuste debe analizar el desfase entre segmentos de transcripción y contexto sin aplicar una resta fija uniforme.

### R7. Reporte técnico final y restricciones de calidad
Al finalizar las correcciones y verificaciones, se debe presentar un reporte técnico que documente: problemas encontrados y sus causas, cambios implementados en cada apartado, archivos modificados en frontend y backend, cambios en la base de datos si fueron necesarios, validaciones de permisos implementadas, pruebas realizadas con roles profesor y alumno con sus resultados, y problemas pendientes o limitaciones encontradas. No se deben eliminar funcionalidades existentes, alterar funciones no relacionadas, romper contratos de API sin analizar dependencias, ni duplicar información innecesariamente.

## Verification Resources
- Entorno de pruebas automatizadas del repositorio: utilizar la configuración de pruebas existente (pytest en `tests/`) y ampliarla con pruebas automatizadas (unitarias, integración y validación de permisos de roles profesor vs alumno) para verificar cada requerimiento.

## Acceptance Criteria

### Calificaciones e Intentos
- [ ] Desde una actividad específica, el profesor puede consultar la lista de alumnos que la realizaron y acceder a los intentos y respuestas de cada alumno.
- [ ] El profesor puede asignar y modificar calificaciones individuales por alumno y actividad desde la propia actividad.
- [ ] La interfaz distingue visualmente los alumnos calificados de aquellos con calificación pendiente.
- [ ] Cada alumno visualiza únicamente el conteo y detalle de sus propios intentos.
- [ ] El profesor visualiza exclusivamente los intentos del alumno consultado sin mezcla de datos de otros alumnos.
- [ ] Las consultas del backend y las relaciones de base de datos asocian los intentos estrictamente al usuario, actividad y cuestionario.

### Videos
- [ ] Los videos se muestran inicialmente ordenados del más reciente al más antiguo según su fecha real.
- [ ] El usuario puede alternar el orden (más recientes primero / más antiguos primero).
- [ ] La búsqueda por título filtra los videos correctamente y opera de forma conjunta con el orden cronológico sin pérdida de selección ni errores.

### Cuestionarios y Permisos
- [ ] El profesor puede alternar entre la versión con respuestas y sin respuestas, actualizándose la vista y la exportación de inmediato según el modo activo.
- [ ] El alumno no tiene acceso al selector de versiones ni puede ver las respuestas correctas.
- [ ] Las peticiones a los endpoints del backend realizadas por alumnos no incluyen respuestas correctas ni indicadores en el payload.
- [ ] Las exportaciones realizadas por el alumno contienen únicamente el cuestionario sin respuestas.

### Resúmenes
- [ ] El alumno puede consultar el resumen oficial del profesor pero no puede modificarlo, sobrescribirlo ni regenerarlo.
- [ ] El alumno dispone de un espacio independiente para generar y guardar su resumen personal asociado a su cuenta y actividad.
- [ ] El profesor puede consultar y diferenciar el resumen oficial de los resúmenes personales de los alumnos.

### Timestamps
- [ ] Al seleccionar el timestamp de una pregunta, el video inicia entre 5 y 10 segundos antes del comienzo de la explicación relevante del tema.
- [ ] La corrección de timestamps se fundamenta en el análisis de segmentos y contexto, sin aplicar un desfase fijo arbitrario.

### Matriz de Permisos y Robustez
- [ ] Se verifica la matriz de permisos para los roles Profesor y Alumno:
  - Calificar alumnos: Profesor Sí, Alumno No.
  - Consultar intentos individuales: Profesor Sí (de cada alumno), Alumno solo los propios.
  - Ordenar y buscar videos: Profesor Sí, Alumno Sí.
  - Ver y exportar cuestionario con respuestas: Profesor Sí, Alumno No.
  - Ver y exportar cuestionario sin respuestas: Profesor Sí, Alumno Sí.
  - Consultar resumen del profesor: Profesor Sí, Alumno Sí.
  - Generar resumen personal: Alumno Sí.
  - Modificar resumen oficial: Alumno No.
- [ ] Los datos persisten correctamente tras recargar la página.
- [ ] No existen errores en la consola del navegador ni excepciones no controladas en el backend.
- [ ] Las funcionalidades existentes en la aplicación continúan funcionando sin regresiones.
- [ ] Se incluye el reporte final documentando los 8 puntos requeridos.

## Follow-up — 2026-11-04T05:39:38Z

The user notes that they are running very low on credits and asks how much is left. Please accelerate the conclusion, wrap up Milestone 6 and the R7 final technical report as quickly as possible. What is the current progress and ETA?
