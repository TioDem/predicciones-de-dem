# tablero de predicciones (Mundial 2026 · Liga MX · Champions · NBA)

Todo vive en este repo: GitHub Actions jala los partidos y cuotas una vez al
día, genera un parlay "seguro" y uno "arriesgado" con un modelo estadístico
simple, y GitHub Pages sirve el tablero. No hay servidor externo ni Streamlit.

## 1. Subir este repo a GitHub

Si aún no tienes el repo creado:

```bash
cd mtzbets-github
git init
git add .
git commit -m "init: tablero de predicciones"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/NOMBRE_REPO.git
git push -u origin main
```

(Reemplaza `TU_USUARIO/NOMBRE_REPO` por tu repo real. Puedes crear el repo
vacío primero en github.com/new, sin README, y luego correr lo de arriba.)

## 2. Agregar tu API key como Secret

En GitHub: **Settings → Secrets and variables → Actions → New repository secret**

- Nombre: `API_FOOTBALL_KEY`
- Valor: tu key de api-sports.io (la misma que usas en API-Football)

> **Importante para NBA:** la key es la misma cuenta, pero API-Football y
> API-Basketball son productos distintos dentro de api-sports.io. Ve a tu
> dashboard (dashboard.api-football.com) y activa el plan gratuito de
> **API-Basketball** también, o los partidos de NBA saldrán vacíos.

## 3. Activar permisos de escritura para Actions

**Settings → Actions → General → Workflow permissions** → selecciona
**"Read and write permissions"**. Esto permite que el workflow haga commit
del snapshot actualizado.

## 4. Activar GitHub Pages

**Settings → Pages → Build and deployment → Source: "GitHub Actions"**

(No selecciones una branch manualmente; el workflow ya incluye el job
`deploy-pages` que hace esto automático.)

## 5. Correr el workflow por primera vez

**Actions → Actualizar predicciones → Run workflow** (botón manual).
Esto va a:
1. Descargar partidos próximos + cuotas promedio + forma reciente
2. Generar `data/snapshot.json` con los parlays
3. Hacer commit del snapshot
4. Publicar el sitio en `https://TU_USUARIO.github.io/NOMBRE_REPO/`

Después de esto corre solo, todos los días a las 9am hora CDMX (cron en
`.github/workflows/update-predictions.yml` — ajústalo si quieres otro
horario, está en UTC).

## Cómo se generan los picks (v1, sin IA)

- **Probabilidad de mercado:** 1/cuota promedio, normalizada para quitar el
  margen de la casa (overround).
- **Forma reciente:** puntos de los últimos 5 partidos (W=3, D=1, L=0),
  normalizados.
- **Blend:** 65% cuota + 35% forma → probabilidad del modelo.
- **Value:** probabilidad del modelo − probabilidad implícita del mercado.
  Si es positivo, el modelo ve más chance de la que paga la cuota.
- **Parlay seguro:** patas con probabilidad de modelo ≥ 55%, máximo una
  pata por partido, ordenadas por confianza.
- **Parlay arriesgado:** patas con value ≥ 5% y probabilidad ≥ 35%,
  ordenadas por value.
- **No bet:** si ningún partido cumple el mínimo, el tablero lo dice
  explícitamente en vez de forzar un pick.

## Siguientes pasos posibles (v2)

- Reemplazar `build_football_snapshot()` / el blend de
  `generate_predictions.py` por tu sistema de consenso multi-modelo
  (Claude + GPT-4o + Gemini) que ya usas en el proyecto de Streamlit —
  la estructura de `all_legs` ya está pensada para eso, solo cambiarías
  cómo se calcula `model_prob`.
- Agregar goles esperados propios (xG) para el mercado Over/Under en vez
  de usar el mercado como proxy.
- Guardar histórico de aciertos por mercado para calibrar el modelo
  (como la sección "Calibración del modelo" de mtzbets).

## Aviso

Contenido informativo de research deportivo. No es asesoría financiera ni
garantiza resultados. Solo para mayores de 18 años. Juega con
responsabilidad.
