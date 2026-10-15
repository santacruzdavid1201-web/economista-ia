# Plan: flujo-proyecto

Especificación: [SPEC-flujo-proyecto.md](../SPEC-flujo-proyecto.md) (aprobada
el 15/10/2026). Tareas en [todo.md](todo.md). El plan anterior
(`matematica-financiera`, completo) queda en la historia de Git.

## Resumen

El gerente escribe su proyecto a precios de hoy y Python arma el flujo de
caja libre año por año: en pesos corrientes por dentro (impuestos,
depreciación, capital de trabajo) y en pesos de hoy en la pantalla, con la
senda de inflación del BanRep (pronóstico del Informe de Política Monetaria y
meta de 3 % después). El tablero de Proyectos pasa a dos pestañas.

## Decisiones de arquitectura

- La senda de inflación es una función pura (`senda_inflacion`) que recibe el
  pronóstico y la meta ya cargados: el flujo no sabe de dónde vienen, y los
  tests no tocan la red.
- El pronóstico del BanRep es una fuente nueva con el mismo patrón de las
  series: descarga separada de la transformación, copia del día en la caché,
  copia versionada de respaldo y caída a la meta si todo falla. El
  actualizador diario lo revisa junto con las series.
- `Proyecto` es un modelo pydantic: la validación de rangos vive en un solo
  lugar y el formulario solo traduce sus errores a mensajes.
- Las pestañas son enlaces con `?pestana=` que HTMX carga sin recargar la
  página; sin HTMX funcionan como enlaces normales.

## Grafo de dependencias

```
meta de inflación (853) ──┐
pronóstico del BanRep ────┼── senda_inflacion ──┐
                          │                     ├── formulario y tabla del flujo
Proyecto + flujo_caja ────┼─────────────────────┘           │
pestañas del tablero ─────┴─────────────────────────────────┘
```

## Fases

1. **Datos de inflación (tareas 1-2):** la meta en el catálogo y el
   pronóstico del informe, con fixture del Excel real.
2. **Cálculo (tareas 3-4):** senda y flujo de caja con los casos a mano.
3. **Tablero (tareas 5-6):** pestañas y la pestaña "Su proyecto".

Cada tarea: tests primero (verlos fallar), implementación, suite completa,
revisión del diff, commit y push.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Errores de nominal contra real en el flujo | Alto | Casos a mano con π = 0 y π fija; propiedad: con π > 0 el flujo en pesos de hoy es menor; conciliación del usuario. |
| El BanRep cambia el formato del Excel o el patrón del DOI | Medio | Lectura por la etiqueta "IPC total" y la fila de años, no por posición; error útil; copia guardada; caída a la meta con supuesto. |
| El informe de octubre sale y el año en curso queda casi cumplido | Bajo | El año t del proyecto usa el año calendario actual + t: el pronóstico del año en curso no se usa. |
| Mover el simulador a una pestaña rompe sus pruebas o enlaces | Bajo | Los tests de la página cubren las dos pestañas; las rutas POST no cambian. |

## Preguntas abiertas

Ninguna.
