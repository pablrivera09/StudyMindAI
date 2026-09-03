import os
import re
import json
from datetime import date
import streamlit as st
from google import genai
from pypdf import PdfReader
from docx import Document

st.set_page_config(page_title="StudyMindAI", page_icon="🧠", layout="wide")
APP_VERSION = "StudyMindAI 2.0 · Interactiva"
MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    st.error("⚠️ Falta GEMINI_API_KEY. Configúrala en el terminal antes de ejecutar la app.")
    st.stop()
client = genai.Client(api_key=API_KEY)

st.markdown("""
<style>
.main-title{font-size:42px;font-weight:800;color:#6C63FF}.subtitle{font-size:20px}
.game-card{padding:18px;border-radius:14px;border:1px solid rgba(128,128,128,.25);margin-bottom:12px}
</style>
""", unsafe_allow_html=True)


def leer_archivo(archivo):
    nombre = archivo.name.lower(); texto = ""
    try:
        if nombre.endswith(".pdf"):
            lector = PdfReader(archivo)
            for pagina in lector.pages:
                texto += pagina.extract_text() or ""
        elif nombre.endswith(".txt"):
            texto = archivo.read().decode("utf-8")
        elif nombre.endswith(".docx"):
            doc = Document(archivo)
            texto = "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        st.error(f"❌ No se pudo leer {archivo.name}: {e}")
    return texto.strip()


def apuntes_texto(limite=50000):
    partes = [f"===== {a['nombre']} =====\n{a['contenido']}" for a in st.session_state.apuntes if a.get("contenido", "").strip()]
    texto = "\n\n".join(partes)
    return texto[:limite] + ("\n\n[Apuntes recortados para mantener rapidez.]" if len(texto) > limite else "")


def reciente(lista, n=12):
    return lista[-n:]


def memoria_texto():
    return "\n".join(f"[{m['asistente']}] {m['rol']}: {m['texto']}" for m in reciente(st.session_state.memoria_estudio, 16))


def llamar(prompt, streaming=False, placeholder=None):
    import time
    ultimo_error = None
    for modelo in MODELS:
        for intento in range(2):
            try:
                if streaming:
                    total = ""
                    for chunk in client.models.generate_content_stream(model=modelo, contents=prompt):
                        parte = getattr(chunk, "text", None)
                        if parte:
                            total += parte
                            placeholder.markdown(total)
                    return total.strip()
                respuesta = client.models.generate_content(model=modelo, contents=prompt)
                return (respuesta.text or "").strip()
            except Exception as e:
                ultimo_error = e
                if "503" in str(e) or "429" in str(e) or "UNAVAILABLE" in str(e):
                    if intento == 0:
                        time.sleep(2)
                    continue
                break
    if placeholder: placeholder.empty()
    st.error(f"❌ Gemini no está disponible ahora mismo. Se probaron varios modelos.\n\nDetalle: {ultimo_error}")

def llamar_json(prompt):
    """Pide JSON a Gemini y lo convierte en un diccionario de Python."""
    respuesta = llamar(prompt)

    if not respuesta:
        return None

    texto = respuesta.strip()

    # Quitar bloques ```json ... ```
    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?\s*", "", texto, flags=re.I)
        texto = re.sub(r"\s*```$", "", texto)

    try:
        return json.loads(texto)

    except json.JSONDecodeError:
        # Intentar encontrar el objeto JSON dentro de la respuesta
        inicio = texto.find("{")
        fin = texto.rfind("}")

        if inicio != -1 and fin > inicio:
            try:
                return json.loads(texto[inicio:fin + 1])
            except json.JSONDecodeError:
                pass

    st.error(
        "❌ Gemini no devolvió las preguntas en un formato válido. "
        "Pulsa de nuevo para intentarlo."
    )

    return None

def guardar_memoria(asistente, rol, texto):
    st.session_state.memoria_estudio.append({"asistente": asistente, "rol": rol, "texto": texto})
    st.session_state.memoria_estudio = st.session_state.memoria_estudio[-40:]


def puntos(n):
    st.session_state.puntos += n
    st.session_state.partidas += 1


def nueva_racha():
    st.session_state.racha += 1
    st.session_state.mejor_racha = max(st.session_state.mejor_racha, st.session_state.racha)


def generar_preguntas(cantidad, tipo="quiz"):
    if tipo == "quiz":
        instrucciones = f"""Crea exactamente {cantidad} preguntas tipo test basadas EXCLUSIVAMENTE en los apuntes.
Cada pregunta debe tener 4 opciones A, B, C y D y una sola respuesta correcta.
Devuelve SOLO JSON válido, sin markdown, con esta estructura:
{{"preguntas":[{{"pregunta":"...","opciones":{{"A":"...","B":"...","C":"...","D":"..."}},"correcta":"A","explicacion":"..."}}]}}
No inventes temas que no aparezcan en los apuntes."""
    else:
        instrucciones = f"""Crea exactamente {cantidad} preguntas tipo test de dificultad progresiva basadas EXCLUSIVAMENTE en los apuntes.
Devuelve SOLO JSON válido, sin markdown, con esta estructura:
{{"preguntas":[{{"pregunta":"...","opciones":{{"A":"...","B":"...","C":"...","D":"..."}},"correcta":"A","explicacion":"..."}}]}}
La pregunta 1 debe ser fácil y la última bastante difícil. No inventes temas."""
    return llamar_json(instrucciones + "\n\nAPUNTES:\n" + apuntes_texto())


for k, v in {
    "memoria_estudio": [], "apuntes": [], "chat_profesor": [], "chat_companero": [],
    "puntos": 0, "partidas": 0, "racha": 0, "mejor_racha": 0,
    "quiz_data": [], "quiz_index": 0, "quiz_score": 0, "quiz_finished": False,
    "reto_data": [], "reto_index": 0, "reto_score": 0, "reto_feedback": "",
    "batalla_data": [], "batalla_index": 0, "batalla_score": 0, "batalla_finished": False,
    "tarjetas": [], "tarjeta": 0, "mostrar_tarjeta": False,
    "plan": "", "plan_asignatura": "", "plan_fecha": None
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.sidebar.title("🧠 StudyMindAI")
st.sidebar.caption(APP_VERSION)
st.sidebar.markdown("---")
pagina = st.sidebar.radio("MENÚ", ["🏠 Inicio", "💬 Chats", "🎮 Juegos", "📅 Próximo examen", "📚 Mis apuntes", "📊 Mi progreso"])
st.sidebar.markdown("---")
st.sidebar.metric("🏆 Puntos", st.session_state.puntos)
st.sidebar.metric("🔥 Racha", st.session_state.racha)
st.sidebar.markdown("---")
st.sidebar.caption("👤 Creador: **Pablo Rivera**")

if pagina == "🏠 Inicio":
    st.markdown('<div class="main-title">🧠 StudyMindAI</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Tu centro de estudio inteligente</div>', unsafe_allow_html=True)
    st.info("👋 Estudia con tus apuntes, habla con tu profesor o compañero y aprende jugando.")
    a, b, c = st.columns(3)
    a.metric("📚 Apuntes", len(st.session_state.apuntes))
    b.metric("💬 Mensajes", len(st.session_state.chat_profesor) + len(st.session_state.chat_companero))
    c.metric("🏆 Puntos", st.session_state.puntos)

elif pagina == "💬 Chats":
    st.title("💬 Chats")
    modo = st.radio("¿Con quién quieres estudiar?", ["👨‍🏫 Profesor", "🤝 Compañero"], horizontal=True)
    profesor = modo == "👨‍🏫 Profesor"
    if profesor:
        st.subheader("👨‍🏫 Profesor virtual")
        instrucciones = """Eres el profesor virtual de StudyMindAI. Enseña de forma clara, paso a paso y adaptada al alumno. Usa ejemplos y preguntas breves para comprobar comprensión. No des siempre la respuesta directamente si es un ejercicio. Puedes usar la memoria compartida con el compañero. Sé natural, paciente y directo."""
        historial = st.session_state.chat_profesor; nombre = "Profesor"
    else:
        st.subheader("🤝 Compañero de estudio")
        instrucciones = """Eres el compañero virtual de estudio de StudyMindAI. Sé cercano, natural y motivador. Estudia junto al usuario, haz preguntas, propone pequeños retos y celebra aciertos. Puedes usar la memoria compartida con el profesor. No inventes conversaciones anteriores."""
        historial = st.session_state.chat_companero; nombre = "Compañero"
    for m in historial:
        with st.chat_message(m["rol"]):
            st.markdown(m["texto"])
    pregunta = st.chat_input("Escribe tu pregunta...")
    if pregunta:
        historial.append({"rol": "user", "texto": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)
        contexto = "\n".join(f"{m['rol']}: {m['texto']}" for m in reciente(historial))
        prompt = f"""{instrucciones}

REGLAS:
- Responde en español.
- Mantén el contexto.
- Usa los apuntes cuando sean relevantes.
- Si algo no está en los apuntes, dilo claramente; puedes aportar conocimiento general distinguiéndolo.
- No inventes datos ni conversaciones.

CONVERSACIÓN RECIENTE:
{contexto}

MEMORIA COMPARTIDA:
{memoria_texto()}

APUNTES:
{apuntes_texto() or 'No hay apuntes cargados.'}

MENSAJE ACTUAL:
{pregunta}"""
        with st.chat_message("assistant"):
            ph = st.empty(); texto = llamar(prompt, True, ph)
        if texto:
            historial.append({"rol": "assistant", "texto": texto})
            guardar_memoria(nombre, "user", pregunta); guardar_memoria(nombre, "assistant", texto)

elif pagina == "🎮 Juegos":
    st.title("🎮 Juegos interactivos")
    if not st.session_state.apuntes:
        st.warning("📚 Sube primero tus apuntes en «Mis apuntes».")
    t1, t2, t3, t4, t5 = st.tabs(["🧠 Quiz", "⚡ Reto rápido", "🃏 Tarjetas", "🏆 Batalla", "🔥 Racha"])

    with t1:
        st.subheader("🧠 Quiz interactivo")
        if not st.session_state.quiz_data:
            if st.button("🎲 Empezar quiz", key="quiz_gen", disabled=not st.session_state.apuntes):
                with st.spinner("🧠 Preparando preguntas..."):
                    data = generar_preguntas(5, "quiz")
                if data and data.get("preguntas"):
                    st.session_state.quiz_data = data["preguntas"][:5]
                    st.session_state.quiz_index = 0
                    st.session_state.quiz_score = 0
                    st.session_state.quiz_finished = False
                    st.rerun()
        else:
            if st.session_state.quiz_finished:
                st.success(f"🎉 Quiz terminado: {st.session_state.quiz_score}/{len(st.session_state.quiz_data)} correctas")
                st.metric("🏆 Puntos ganados", st.session_state.quiz_score * 5)
                if st.button("🔄 Jugar otro quiz", key="quiz_again"):
                    st.session_state.quiz_data = []
                    st.session_state.quiz_index = 0
                    st.session_state.quiz_score = 0
                    st.session_state.quiz_finished = False
                    st.rerun()
            else:
                i = st.session_state.quiz_index
                q = st.session_state.quiz_data[i]
                st.progress((i + 1) / len(st.session_state.quiz_data))
                st.caption(f"Pregunta {i + 1} de {len(st.session_state.quiz_data)} · Aciertos: {st.session_state.quiz_score}")
                st.markdown(f"### ❓ {q['pregunta']}")
                opcion = st.radio("Elige una respuesta:", list(q["opciones"].keys()), format_func=lambda x: f"{x}) {q['opciones'][x]}", key=f"quiz_answer_{i}")
                if st.button("✅ Comprobar", key=f"quiz_check_{i}"):
                    if opcion == q["correcta"]:
                        st.session_state.quiz_score += 1
                        st.success("🎉 ¡Correcto! +5 puntos")
                        puntos(5)
                    else:
                        st.error(f"❌ No es correcto. La respuesta era {q['correcta']}: {q['opciones'][q['correcta']]}")
                    st.info(q.get("explicacion", ""))
                    if i + 1 < len(st.session_state.quiz_data):
                        st.session_state.quiz_index += 1
                        st.rerun()
                    else:
                        st.session_state.quiz_finished = True
                        nueva_racha()
                        st.rerun()

    with t2:
        st.subheader("⚡ Reto rápido")
        if not st.session_state.reto_data:
            if st.button("⚡ Empezar reto", key="reto_gen", disabled=not st.session_state.apuntes):
                prompt = f"""Crea exactamente 5 preguntas cortas para responder con una frase, basadas EXCLUSIVAMENTE en estos apuntes. Devuelve SOLO JSON válido: {{\"preguntas\":[{{\"pregunta\":\"...\"}}]}}.\n\nAPUNTES:\n{apuntes_texto()}"""
                with st.spinner("⚡ Preparando reto..."):
                    data = llamar_json(prompt)
                if data and data.get("preguntas"):
                    st.session_state.reto_data = data["preguntas"][:5]
                    st.session_state.reto_index = 0
                    st.session_state.reto_score = 0
                    st.session_state.reto_feedback = ""
                    st.rerun()
        else:
            i = st.session_state.reto_index
            if i >= len(st.session_state.reto_data):
                st.success(f"🏁 Reto terminado: {st.session_state.reto_score}/5 evaluadas correctamente.")
                if st.button("🔄 Otro reto", key="reto_again"):
                    st.session_state.reto_data = []
                    st.rerun()
            else:
                st.progress(i / len(st.session_state.reto_data))
                st.caption(f"Pregunta {i + 1} de {len(st.session_state.reto_data)}")
                st.markdown(f"### ❓ {st.session_state.reto_data[i]['pregunta']}")
                respuesta = st.text_input("✍️ Tu respuesta", key=f"reto_answer_{i}")
                if st.button("🧑‍🏫 Corregir respuesta", key=f"reto_check_{i}"):
                    if not respuesta.strip():
                        st.warning("Escribe una respuesta primero.")
                    else:
                        prompt = f"""Corrige la respuesta del alumno según estos apuntes. Devuelve SOLO JSON válido: {{\"correcta\":true/false,\"puntuacion\":0-1,\"feedback\":\"explicación breve\"}}. Sé justo: acepta respuestas equivalentes.\n\nAPUNTES:\n{apuntes_texto()}\n\nPREGUNTA:\n{st.session_state.reto_data[i]['pregunta']}\n\nRESPUESTA DEL ALUMNO:\n{respuesta}"""
                        with st.spinner("🧑‍🏫 Corrigiendo..."):
                            result = llamar_json(prompt)
                        if result:
                            if result.get("correcta"):
                                st.session_state.reto_score += 1
                                puntos(5)
                                st.success("🎉 ¡Correcto! +5 puntos")
                            else:
                                st.warning("❌ No del todo.")
                            st.info(result.get("feedback", ""))
                            st.session_state.reto_index += 1
                            if st.session_state.reto_index >= len(st.session_state.reto_data):
                                nueva_racha()
                            st.rerun()

    with t3:
        st.subheader("🃏 Tarjetas de memoria")
        if st.button("🃏 Crear tarjetas", key="cards_gen", disabled=not st.session_state.apuntes):
            prompt = f"Crea 8 tarjetas usando EXCLUSIVAMENTE estos apuntes. Formato exacto: PREGUNTA: ...\\nRESPUESTA: ...\\nNo numeres ni añadas introducción.\\n\\nAPUNTES:\\n{apuntes_texto()}"
            with st.spinner("🃏 Creando tarjetas..."):
                raw = llamar(prompt)
            cards = []
            if raw:
                for q, a in re.findall(r"PREGUNTA\s*:\s*(.*?)\s*RESPUESTA\s*:\s*(.*?)(?=\s*PREGUNTA\s*:|$)", raw, re.I | re.S):
                    if q.strip() and a.strip():
                        cards.append({"pregunta": q.strip(), "respuesta": a.strip()})
            st.session_state.tarjetas = cards
            st.session_state.tarjeta = 0
            st.session_state.mostrar_tarjeta = False
            st.rerun()
        if st.session_state.tarjetas:
            i = st.session_state.tarjeta; card = st.session_state.tarjetas[i]
            st.progress((i + 1) / len(st.session_state.tarjetas)); st.caption(f"Tarjeta {i + 1} de {len(st.session_state.tarjetas)}")
            st.markdown("### ❓ Pregunta"); st.write(card["pregunta"])
            if st.session_state.mostrar_tarjeta:
                st.success(card["respuesta"])
                if st.button("🧠 Lo sabía", key=f"know{i}"):
                    puntos(3); st.session_state.tarjeta = min(i + 1, len(st.session_state.tarjetas) - 1); st.session_state.mostrar_tarjeta = False; st.rerun()
            elif st.button("👀 Mostrar respuesta", key=f"show{i}"):
                st.session_state.mostrar_tarjeta = True; st.rerun()
            x, y = st.columns(2)
            with x:
                if st.button("⬅️ Anterior", disabled=i == 0, key=f"prev{i}"):
                    st.session_state.tarjeta -= 1; st.session_state.mostrar_tarjeta = False; st.rerun()
            with y:
                if st.button("➡️ Siguiente", disabled=i == len(st.session_state.tarjetas) - 1, key=f"next{i}"):
                    st.session_state.tarjeta += 1; st.session_state.mostrar_tarjeta = False; st.rerun()

    with t4:
        st.subheader("🏆 Batalla interactiva")
        if not st.session_state.batalla_data:
            if st.button("🏆 Empezar batalla", key="battle_gen", disabled=not st.session_state.apuntes):
                with st.spinner("🏆 Preparando batalla..."):
                    data = generar_preguntas(10, "batalla")
                if data and data.get("preguntas"):
                    st.session_state.batalla_data = data["preguntas"][:10]
                    st.session_state.batalla_index = 0
                    st.session_state.batalla_score = 0
                    st.session_state.batalla_finished = False
                    st.rerun()
        else:
            if st.session_state.batalla_finished:
                st.success(f"🏆 Batalla terminada: {st.session_state.batalla_score}/{len(st.session_state.batalla_data)} correctas")
                if st.button("🔄 Nueva batalla", key="battle_again"):
                    st.session_state.batalla_data = []
                    st.rerun()
            else:
                i = st.session_state.batalla_index; q = st.session_state.batalla_data[i]
                st.progress((i + 1) / len(st.session_state.batalla_data))
                st.caption(f"Ronda {i + 1} de {len(st.session_state.batalla_data)} · Puntuación: {st.session_state.batalla_score}")
                st.markdown(f"### ⚔️ {q['pregunta']}")
                opcion = st.radio("Elige:", list(q["opciones"].keys()), format_func=lambda x: f"{x}) {q['opciones'][x]}", key=f"battle_answer_{i}")
                if st.button("⚔️ Atacar / Comprobar", key=f"battle_check_{i}"):
                    if opcion == q["correcta"]:
                        st.session_state.batalla_score += 1
                        puntos(8)
                        st.success("💥 ¡Golpe directo! +8 puntos")
                    else:
                        st.error(f"💀 Fallaste. Era {q['correcta']}: {q['opciones'][q['correcta']]}")
                    st.info(q.get("explicacion", ""))
                    if i + 1 < len(st.session_state.batalla_data):
                        st.session_state.batalla_index += 1
                        st.rerun()
                    else:
                        st.session_state.batalla_finished = True
                        nueva_racha()
                        st.rerun()

    with t5:
        st.subheader("🔥 Racha de estudio")
        st.metric("Racha actual", f"{st.session_state.racha} 🔥")
        st.metric("Mejor racha", f"{st.session_state.mejor_racha} 🔥")
        if st.button("🔥 Registrar sesión", key="session_done"):
            puntos(5); nueva_racha(); st.success("🔥 +5 puntos")

elif pagina == "📅 Próximo examen":
    st.title("📅 Preparar mi próximo examen")
    st.write("El plan se genera con la fecha del examen, tu objetivo y los temas que aparecen en tus apuntes.")
    asignatura = st.text_input("📚 Asignatura", placeholder="Ejemplo: Historia")
    fecha = st.date_input("📅 Fecha del examen", min_value=date.today())
    nota = st.slider("🎯 Nota objetivo", 0.0, 10.0, 8.0, 0.5)
    if st.button("🚀 CREAR MI PLAN DE ESTUDIO", use_container_width=True, type="primary"):
        if not asignatura.strip():
            st.warning("✍️ Escribe la asignatura.")
        elif not st.session_state.apuntes:
            st.warning("📚 Sube primero tus apuntes en «Mis apuntes». El plan usa esos contenidos.")
        else:
            dias = (fecha - date.today()).days
            if dias < 0:
                st.error("❌ La fecha del examen no puede estar en el pasado.")
            else:
                prompt = f"""Eres un planificador de estudio. Crea un plan CONCRETO y realizable para un alumno.
Asignatura: {asignatura.strip()}
Hoy: {date.today().isoformat()}
Examen: {fecha.isoformat()}
Días disponibles: {dias}
Nota objetivo: {nota}/10

Usa exclusivamente los temas y contenidos presentes en los apuntes. NO inventes temas.
Si hay varios temas, repártelos de forma equilibrada.
Cada día debe incluir: tema, qué estudiar, una tarea práctica y un repaso breve.
Incluye días de repaso acumulativo antes del examen.
Si quedan 0 días, indica que debe hacer una sesión intensiva hoy.
Termina con una estrategia para el día anterior y el día del examen.
Escribe en español, con encabezados claros y sin introducciones innecesarias.

APUNTES:
{apuntes_texto()}"""
                with st.spinner("🧠 Analizando tus apuntes y creando el plan..."):
                    plan_nuevo = llamar(prompt)
                if plan_nuevo:
                    st.session_state.plan = plan_nuevo
                    st.session_state.plan_asignatura = asignatura.strip()
                    st.session_state.plan_fecha = fecha
                    st.success("✅ Plan creado correctamente.")
    if st.session_state.plan:
        st.divider()
        st.subheader(f"📋 Plan de estudio: {st.session_state.plan_asignatura}")
        st.caption(f"Examen: {st.session_state.plan_fecha}")
        st.markdown(st.session_state.plan)

elif pagina == "📚 Mis apuntes":
    st.title("📚 Mis apuntes")
    st.write("Estos apuntes se usan en chats, juegos y planes de estudio.")
    archivos = st.file_uploader("📎 Selecciona tus apuntes", type=["pdf", "txt", "docx"], accept_multiple_files=True)
    if archivos:
        nuevos = 0
        for archivo in archivos:
            if not any(a["nombre"] == archivo.name for a in st.session_state.apuntes):
                texto = leer_archivo(archivo)
                if texto:
                    st.session_state.apuntes.append({"nombre": archivo.name, "contenido": texto}); nuevos += 1
        if nuevos:
            st.success(f"✅ {nuevos} archivo(s) añadido(s).")
    for i, a in enumerate(st.session_state.apuntes):
        with st.expander(f"📄 {a['nombre']}"):
            st.write(a["contenido"])
            if st.button("🗑️ Eliminar", key=f"del{i}"):
                st.session_state.apuntes.pop(i); st.rerun()
    if not st.session_state.apuntes:
        st.info("Todavía no tienes apuntes guardados. 📚")

elif pagina == "👤 Creador":
    st.title("👤 Creador")
    st.markdown("## Pablo Rivera")
    st.write("Creador de StudyMindAI 🧠")

elif pagina == "📊 Mi progreso":
    st.title("📊 Mi progreso")
    a, b, c = st.columns(3)
    a.metric("🏆 Puntos", st.session_state.puntos)
    b.metric("🎮 Partidas", st.session_state.partidas)
    c.metric("🔥 Mejor racha", st.session_state.mejor_racha)
    st.write(f"📚 Apuntes: **{len(st.session_state.apuntes)}**")
    st.write(f"💬 Mensajes profesor: **{len(st.session_state.chat_profesor)}**")
    st.write(f"🤝 Mensajes compañero: **{len(st.session_state.chat_companero)}**")
