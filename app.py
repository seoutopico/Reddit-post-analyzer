import os
import requests
import json
import re
import streamlit as st
from datetime import datetime
from openai import OpenAI
import time

# Configuración de la página
st.set_page_config(
    page_title="Reddit Post Analyzer - Demo",
    page_icon="📊",
    layout="wide"
)

# Estado inicial
if "current_post_id" not in st.session_state:
    st.session_state.current_post_id = None
if "current_post" not in st.session_state:
    st.session_state.current_post = None
if "current_analysis" not in st.session_state:
    st.session_state.current_analysis = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Funciones principales
def extract_post_id_from_url(url):
    """Extrae el ID del post de una URL de Reddit"""
    patterns = [
        r'reddit\.com/r/[^/]+/comments/([a-z0-9]+)',
        r'redd\.it/([a-z0-9]+)',
        r'/comments/([a-z0-9]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_post_by_id(post_id, include_comments=True, max_comments=15):
    """Obtiene el contenido del post de Reddit con múltiples métodos de fallback"""
    
    # Lista de endpoints a intentar
    endpoints = [
        f"https://old.reddit.com/comments/{post_id}.json",
        f"https://www.reddit.com/comments/{post_id}.json",
        f"https://reddit.com/comments/{post_id}.json"
    ]
    
    # Headers variados para evitar detección
    headers_list = [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        },
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Accept": "*/*"
        },
        {
            "User-Agent": "PostAnalyzer/1.0 (Educational Purpose)",
            "Accept": "application/json"
        }
    ]
    
    last_error = None
    
    for endpoint in endpoints:
        for headers in headers_list:
            try:
                with st.spinner(f"🌐 Intentando obtener post... ({endpoints.index(endpoint)+1}/{len(endpoints)})"):
                    # Pequeña pausa para evitar rate limiting
                    time.sleep(1)
                    
                    res = requests.get(
                        endpoint, 
                        headers=headers, 
                        timeout=10,
                        allow_redirects=True
                    )
                    
                    if res.status_code == 200:
                        data = res.json()
                        
                        # Procesar los datos
                        post_data = data[0]["data"]["children"][0]["data"]
                        subreddit = post_data.get("subreddit", "")
                        score = post_data.get("score", 0)
                        
                        post_content = f"""
TÍTULO: {post_data.get('title', '')}
CONTENIDO: {post_data.get('selftext', 'Sin contenido adicional')}
SCORE: {score} votos
COMENTARIOS: {post_data.get('num_comments', 0)} comentarios
URL: https://reddit.com{post_data.get('permalink', '')}
SUBREDDIT: r/{subreddit}
"""
                        
                        if include_comments and len(data) > 1:
                            comments_data = data[1]["data"]["children"]
                            comment_section = "\n\nCOMENTARIOS PRINCIPALES:\n"
                            comment_count = 0
                            
                            for comment in comments_data:
                                if comment.get("kind") != "t1":
                                    continue
                                comment_data = comment.get("data", {})
                                comment_body = comment_data.get("body", "")
                                comment_score = comment_data.get("score", 0)
                                
                                if comment_body and comment_body not in ["[deleted]", "[removed]"]:
                                    comment_section += f"\n--- COMENTARIO {comment_count + 1} (Score: {comment_score}) ---\n"
                                    comment_section += f"{comment_body}\n"
                                    comment_count += 1
                                
                                if comment_count >= max_comments:
                                    break
                            
                            if comment_count > 0:
                                post_content += comment_section
                            else:
                                post_content += "\n\nNo hay comentarios disponibles."
                        
                        return {
                            'title': post_data.get('title', ''),
                            'content': post_content,
                            'score': score,
                            'url': f"https://reddit.com{post_data.get('permalink', '')}",
                            'subreddit': subreddit
                        }
                    
                    elif res.status_code == 429:
                        last_error = "Rate limit alcanzado. Espera un momento antes de intentar de nuevo."
                        time.sleep(5)
                    else:
                        last_error = f"Error {res.status_code}: {res.reason}"
                        
            except requests.exceptions.Timeout:
                last_error = "Tiempo de espera agotado"
            except requests.exceptions.ConnectionError:
                last_error = "Error de conexión"
            except Exception as e:
                last_error = str(e)
    
    # Si todos los intentos fallan
    st.error(f"""
    ❌ No se pudo obtener el post de Reddit.
    
    **Posibles razones:**
    - Reddit está bloqueando las solicitudes desde servidores cloud
    - El post no existe o fue eliminado
    - Problemas de conectividad
    
    **Solución alternativa:**
    1. Copia el contenido del post manualmente
    2. Pégalo en el campo de texto alternativo abajo
    
    Último error: {last_error}
    """)
    return None

def analyze_post(client, post_content, analysis_prompt=""):
    """Analiza el contenido del post usando OpenAI"""
    if not analysis_prompt:
        analysis_prompt = "Identifica y resume los subtemas principales"
    
    with st.spinner("🤖 Analizando contenido..."):
        try:
            prompt = f"""
Analiza este texto de Reddit y responde:

1. ¿Cuál es el tema principal? (en 5-10 palabras)
2. ¿Hay una pregunta principal? (sí/no y cuál)
3. Lista los subtemas detectados con un titular y resumen en bullets

El análisis debe centrarse en: {analysis_prompt}

CONTENIDO:
{post_content}
"""
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"❌ Error en análisis: {str(e)}"

def generate_txt_export(post_data, analysis, chat_history):
    """Genera contenido TXT para descargar"""
    content = f"""════════════════════════════════════════════════
ANÁLISIS DE POST DE REDDIT
Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
════════════════════════════════════════════════

📌 POST ORIGINAL
----------------
Título: {post_data['title']}
Subreddit: r/{post_data['subreddit']}
URL: {post_data['url']}
Score: {post_data['score']} votos

📝 CONTENIDO COMPLETO:
{post_data['content']}

🔍 ANÁLISIS:
{analysis}
"""
    
    if chat_history:
        content += "\n\n💬 HISTORIAL DE CHAT:\n"
        content += "=" * 40 + "\n"
        for msg in chat_history:
            if "user" in msg:
                content += f"\n👤 Usuario: {msg['user']}\n"
            elif "assistant" in msg:
                content += f"\n🤖 Asistente: {msg['assistant']}\n"
            content += "-" * 40
    
    return content

# INTERFAZ PRINCIPAL
st.title("📊 Reddit Post Analyzer - Demo")
st.markdown("""
Esta es una versión demo para analizar posts de Reddit usando IA.
Necesitas tu propia API Key de OpenAI para usarla.

⚠️ **Nota**: Si Reddit bloquea el acceso, puedes pegar el contenido manualmente.
""")

# Sidebar para API Key
with st.sidebar:
    st.header("⚙️ Configuración")
    api_key = st.text_input(
        "API Key de OpenAI:",
        type="password",
        help="Obtén tu API key en https://platform.openai.com/api-keys"
    )
    
    if api_key:
        client = OpenAI(api_key=api_key)
        st.success("✅ API Key configurada")
    else:
        st.warning("⚠️ Ingresa tu API Key para continuar")
    
    st.markdown("---")
    st.markdown("""
    ### 📖 Cómo usar:
    1. Ingresa tu API Key de OpenAI
    2. Pega la URL de un post de Reddit
    3. Analiza el contenido
    4. Chatea con el análisis
    5. Descarga el resultado en TXT
    
    ### 🔧 Solución de problemas:
    Si Reddit bloquea el acceso, puedes:
    - Usar el modo manual (pegar contenido)
    - Ejecutar la app localmente
    - Intentar más tarde
    """)

# Tabs principales
tab1, tab2 = st.tabs(["📝 Analizar Post", "💬 Chat"])

with tab1:
    st.header("Analizar Post de Reddit")
    
    if not api_key:
        st.info("👆 Primero ingresa tu API Key en la barra lateral")
    else:
        # Opción 1: URL automática
        st.subheader("Opción 1: Obtener automáticamente")
        col1, col2 = st.columns([1, 1])
        
        with col1:
            url = st.text_input("URL del post de Reddit:")
            include_comments = st.checkbox("Incluir comentarios", value=True)
            max_comments = st.slider(
                "Número de comentarios", 
                5, 30, 15,
                disabled=not include_comments
            )
            analysis_prompt = st.text_input(
                "Aspecto específico a analizar (opcional):"
            )
            
            if st.button("🔍 Analizar Post", type="primary"):
                if url:
                    post_id = extract_post_id_from_url(url)
                    if post_id:
                        post = get_post_by_id(post_id, include_comments, max_comments)
                        if post:
                            analysis = analyze_post(client, post['content'], analysis_prompt)
                            st.session_state.current_post = post
                            st.session_state.current_analysis = analysis
                            st.session_state.current_post_id = post_id
                            st.session_state.chat_history = []
                            st.success("✅ Post analizado correctamente")
                            st.balloons()
                    else:
                        st.error("URL no válida")
                else:
                    st.warning("Por favor, ingresa una URL")
        
        with col2:
            if st.session_state.current_analysis:
                st.subheader("📊 Resultado del Análisis")
                st.info(f"**Título**: {st.session_state.current_post['title']}")
                st.info(f"**Subreddit**: r/{st.session_state.current_post['subreddit']}")
                st.markdown(st.session_state.current_analysis)
                
                # Botón de descarga
                txt_content = generate_txt_export(
                    st.session_state.current_post,
                    st.session_state.current_analysis,
                    st.session_state.chat_history
                )
                st.download_button(
                    label="📥 Descargar análisis (TXT)",
                    data=txt_content,
                    file_name=f"reddit_{st.session_state.current_post_id}_{datetime.now().strftime('%Y%m%d')}.txt",
                    mime="text/plain"
                )
        
        # Opción 2: Entrada manual
        st.markdown("---")
        st.subheader("Opción 2: Entrada manual (si la automática falla)")
        
        with st.expander("📝 Pegar contenido manualmente"):
            manual_title = st.text_input("Título del post:")
            manual_subreddit = st.text_input("Subreddit (ej: AskReddit):")
            manual_content = st.text_area(
                "Contenido del post (incluye comentarios si quieres):",
                height=300,
                help="Copia y pega el contenido completo del post aquí"
            )
            
            if st.button("🔍 Analizar contenido manual"):
                if manual_title and manual_content:
                    # Crear estructura de post manual
                    post = {
                        'title': manual_title,
                        'content': manual_content,
                        'score': 0,
                        'url': 'Entrada manual',
                        'subreddit': manual_subreddit or 'unknown'
                    }
                    
                    analysis = analyze_post(client, manual_content, analysis_prompt)
                    st.session_state.current_post = post
                    st.session_state.current_analysis = analysis
                    st.session_state.current_post_id = "manual_" + datetime.now().strftime('%Y%m%d%H%M%S')
                    st.session_state.chat_history = []
                    st.success("✅ Contenido analizado correctamente")
                else:
                    st.warning("Por favor, completa al menos el título y contenido")

with tab2:
    st.header("Chat sobre el Post")
    
    if not api_key:
        st.info("👆 Primero ingresa tu API Key en la barra lateral")
    elif not st.session_state.current_post_id:
        st.info("📝 Primero analiza un post en la pestaña anterior")
    else:
        st.subheader(f"💬 {st.session_state.current_post['title']}")
        
        # Mostrar historial de chat
        for msg in st.session_state.chat_history:
            if "user" in msg:
                with st.chat_message("user"):
                    st.write(msg['user'])
            elif "assistant" in msg:
                with st.chat_message("assistant"):
                    st.write(msg['assistant'])
        
        # Input de chat
        user_input = st.chat_input("Escribe tu pregunta sobre el post...")
        
        if user_input:
            # Agregar mensaje del usuario
            st.session_state.chat_history.append({"user": user_input})
            
            # Generar respuesta
            with st.spinner("Pensando..."):
                try:
                    prompt = f"""
Contexto del post:
{st.session_state.current_post['content']}

Análisis previo:
{st.session_state.current_analysis}

Pregunta del usuario: {user_input}

Responde basándote únicamente en la información del post.
"""
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=1000,
                        temperature=0.3
                    )
                    answer = response.choices[0].message.content
                    st.session_state.chat_history.append({"assistant": answer})
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        # Botones de control
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Limpiar chat"):
                st.session_state.chat_history = []
                st.rerun()
        
        with col2:
            if st.session_state.chat_history:
                txt_content = generate_txt_export(
                    st.session_state.current_post,
                    st.session_state.current_analysis,
                    st.session_state.chat_history
                )
                st.download_button(
                    label="📥 Descargar conversación completa",
                    data=txt_content,
                    file_name=f"reddit_chat_{st.session_state.current_post_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>🔗 <a href='https://github.com/tu-usuario/reddit-analyzer'>GitHub</a> | 
    ⚡ Powered by OpenAI GPT-4 | 
    🚀 Built with Streamlit</p>
    <p style='font-size: 0.8em; color: gray;'>
    Si Reddit bloquea el acceso, usa la opción manual o ejecuta localmente
    </p>
</div>
""", unsafe_allow_html=True)
