# GRUPPE-REBAZA
hackathon
- Nombre

## Reproductor local

Genera el audio del guion preparado con `python -m src.audio --listener mara`.
Desde la raíz del repositorio, sirve el proyecto con:

```sh
python -m http.server 8000
```

Abre [el reproductor](http://localhost:8000/web/player.html). Cada pestaña carga
el audio y la transcripción del oyente cuando existen en `out/`. Para habilitar
el agente de voz, asigna su ID a `AGENT_ID` en `web/player.html`.
