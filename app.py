import requests
import json
import re
import streamlit as st
from datetime import datetime
from openai import OpenAI
import urllib.parse

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

def get_post_via_proxy(post_id, include_comments=True, max_comments=15):
    """Obtiene el post usando un proxy para evitar bloqueos"""
    reddit_url = f"https://www.reddit.com/comments/{post_id}.json"
    
    # Método 1: Usar AllOrigins (proxy gratuito)
    proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(reddit_url)}"
    
    try:
        with st.spinner("🌐 Obteniendo post via proxy..."):
            response = requests.get(proxy_url, timeout=15)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    return process_reddit_data(data, include_comments, max_comments)
                except json.JSONDecodeError:
                    st.error("Error decodificando la respuesta. Intenta con otro post o usa el modo manual.")
                    return None
            else:
                return None
                
    except Exception as e:
        st.error(f"Error con proxy: {str(e)}")
        return None

def get_post_via_cors_proxy(post_id, include_comments=True, max_comments=15):
    """Método alternativo usando otro proxy"""
    reddit_url = f"https://www.reddit.com/comments/{post_id}.json"
    
    # Método 2: Usar corsproxy.io
    proxy_url = f"https://corsproxy.io/?{urllib.parse.quote(reddit_url)}"
    
    try:
        with st.spinner("🌐 Intentando método alternativo..."):
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(proxy_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                return process_reddit_data(data, include_comments, max_comments)
            else:
                return None
                
    except Exception:
        return None

def process_reddit_data(data, include_comments=True, max_comments=15):
    """Procesa los datos JSON de Reddit"""
    try:
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
    except Exception as e:
        st.error(f"Error procesando datos: {str(e)}")
        return None

def get_post_by_id(post_id, include_comments=True, max_comments=15):
    """Intenta obtener el post con varios métodos"""
    # Intentar con proxy primero
    result = get_post_via_proxy(post_id, include_comments, max_comments)
    
    if not result:
        # Si falla, intentar con proxy alternativo
        result = get_post_via_cors_proxy(post_id, include_comments, max_comments)
    
    if not result:
        st.error("""
        ❌ No se pudo obtener el post automáticamente.
        
        **Por favor usa la opción manual abajo:**
        1. Abre el post en Reddit
        2. Copia el título y contenido
        3. Pégalo en la sección "Entrada Manual"
        """)
    
    return result

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
Analiza posts de Reddit usando IA. Necesitas tu propia API Key de OpenAI.

🔧 **Nota**: Usamos proxies para evitar bloqueos de Reddit. Si falla, usa la entrada manual.
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
    ### 📖 Instrucciones:
    1. Ingresa tu API Key
    2. Pega URL del post
    3. Analiza y chatea
    4. Descarga resultados
    
    ### 🆘 Si falla la carga:
    Usa la opción manual para
    pegar el contenido directamente
    """)

# Tabs principales
tab1, tab2 = st.tabs(["📝 Analizar Post", "💬 Chat"])

with tab1:
    st.header("Analizar Post de Reddit")
    
    if not api_key:
        st.info("👆 Primero ingresa tu API Key en la barra lateral")
    else:
        # Opción automática
        st.subheader("🤖 Opción Automática")
        
        url = st.text_input("URL del post de Reddit:", 
                           placeholder="https://www.reddit.com/r/...")
        
        col1, col2 = st.columns(2)
        with col1:
            include_comments = st.checkbox("Incluir comentarios", value=True)
        with col2:
            max_comments = st.slider("Máx. comentarios", 5, 30, 15, 
                                    disabled=not include_comments)
        
        analysis_prompt = st.text_input("Aspecto a analizar (opcional):")
        
        if st.button("🔍 Analizar Post", type="primary", use_container_width=True):
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
                st.warning("Ingresa una URL")
        
        # Mostrar resultados
        if st.session_state.current_analysis:
            st.markdown("---")
            st.subheader("📊 Resultado del Análisis")
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.info(f"**{st.session_state.current_post['title']}**")
                st.caption(f"r/{st.session_state.current_post['subreddit']} • {st.session_state.current_post['score']} votos")
            with col2:
                txt_content = generate_txt_export(
                    st.session_state.current_post,
                    st.session_state.current_analysis,
                    st.session_state.chat_history
                )
                st.download_button(
                    label="📥 Descargar",
                    data=txt_content,
                    file_name=f"reddit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
            
            st.markdown(st.session_state.current_analysis)
        
        # Opción manual
        st.markdown("---")
        with st.expander("✍️ Entrada Manual (si la automática falla)"):
            st.markdown("""
            **Cómo usar:**
            1. Abre el post en Reddit
            2. Copia el título y contenido (incluye comentarios si quieres)
            3. Pégalo aquí abajo
            """)
            
            manual_title = st.text_input("Título del post:")
            manual_subreddit = st.text_input("Subreddit:", placeholder="AskReddit")
            manual_content = st.text_area("Contenido completo:", height=300)
            
            if st.button("📝 Analizar Contenido Manual", use_container_width=True):
                if manual_title and manual_content:
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
                    st.session_state.current_post_id = f"manual_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    st.session_state.chat_history = []
                    st.success("✅ Contenido analizado")
                    st.rerun()
                else:
                    st.warning("Completa título y contenido")

with tab2:
    st.header("💬 Chat sobre el Post")
    
    if not api_key:
        st.info("👆 Primero ingresa tu API Key")
    elif not st.session_state.current_post_id:
        st.info("📝 Primero analiza un post")
    else:
        # Título del post actual
        st.markdown(f"### {st.session_state.current_post['title']}")
        st.caption(f"r/{st.session_state.current_post['subreddit']}")
        
        # Chat container
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.chat_history:
                if "user" in msg:
                    with st.chat_message("user"):
                        st.write(msg['user'])
                elif "assistant" in msg:
                    with st.chat_message("assistant"):
                        st.write(msg['assistant'])
        
        # Input
        user_input = st.chat_input("Pregunta sobre el post...")
        
        if user_input:
            st.session_state.chat_history.append({"user": user_input})
            
            with st.spinner("Pensando..."):
                try:
                    prompt = f"""
Contexto: {st.session_state.current_post['content']}

Análisis previo: {st.session_state.current_analysis}

Pregunta: {user_input}

Responde basándote solo en la información disponible.
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
        
        # Controles
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Limpiar chat", use_container_width=True):
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
                    label="📥 Descargar todo",
                    data=txt_content,
                    file_name=f"reddit_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )

# Footer
st.markdown("---")
st.caption("🚀 Powered by OpenAI GPT-4 Mini | [GitHub](https://github.com/tu-usuario/reddit-analyzer)")
