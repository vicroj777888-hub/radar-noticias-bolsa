# ==========================================
# RADAR DE NOTICIAS - INTELIGENCIA DE MERCADO
# App independiente del Radar de Francotirador
# Fuentes gratuitas + analisis IA con Gemini (gratis)
# ==========================================

import streamlit as st
import pandas as pd
import yfinance as yf
import feedparser
import requests
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime

ALTA = "\u25B2"
BAJA = "\u25BC"
NEU = "\u25CF"

TICKERS = ['F', 'T', 'PFE', 'VALE', 'AAL', 'BAC', 'USO', 'SOFI', 'CCL', 'NFLX']

st.set_page_config(page_title="Radar de Noticias", layout="wide")

# ==========================================
# CLAVE GEMINI (gratis)
# ==========================================

def obtener_key_gemini():
    try:
        k = st.secrets['GEMINI_API_KEY']
        if k:
            return k
    except Exception:
        pass
    return os.environ.get('GEMINI_API_KEY', '')

# ==========================================
# FUENTES DE NOTICIAS GRATUITAS
# ==========================================

@st.cache_data(ttl=1800)
def noticias_yfinance(ticker):
    out = []
    try:
        t = yf.Ticker(ticker)
        items = t.news or []
        for it in items[:10]:
            c = it.get('content', it)
            title = c.get('title')
            if not title:
                continue
            url_obj = c.get('canonicalUrl') or {}
            out.append({
                'titulo': title,
                'fuente': c.get('provider') or c.get('publisher') or 'Yahoo Finance',
                'link': url_obj.get('url') or c.get('link') or ''
            })
    except Exception:
        pass
    return out

@st.cache_data(ttl=1800)
def noticias_rss(url, fuente_default):
    out = []
    try:
        d = feedparser.parse(url)
        for e in d.entries[:10]:
            src = e.get('source', {})
            out.append({
                'titulo': e.get('title', ''),
                'fuente': src.get('title', fuente_default) if isinstance(src, dict) else fuente_default,
                'link': e.get('link', '')
            })
    except Exception:
        pass
    return out

@st.cache_data(ttl=1800)
def noticias_sec(ticker):
    """Documentos oficiales 8-K de SEC EDGAR (negociaciones, fusiones, contratos)"""
    out = []
    try:
        url = ('https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=' + ticker +
               '&type=8-K&dateb=&owner=include&count=5&output=atom')
        headers = {'User-Agent': 'Radar Noticias DSS / notificaciones@dss-trading.com'}
        r = requests.get(url, headers=headers, timeout=20)
        ns = '{http://www.w3.org/2005/Atom}'
        root = ET.fromstring(r.text)
        for entry in root.findall(ns + 'entry')[:5]:
            title = entry.findtext(ns + 'title', '')
            link_el = entry.find(ns + 'link')
            link = link_el.get('href', '') if link_el is not None else ''
            if title:
                out.append({'titulo': title, 'fuente': 'SEC EDGAR (8-K)', 'link': link})
    except Exception:
        pass
    return out

def todas_las_noticias(ticker):
    vistas = set()
    todas = []
    fuentes = []
    fuentes += noticias_yfinance(ticker)
    fuentes += noticias_rss('https://news.google.com/rss/search?q=' + ticker + '+stock&hl=en-US&gl=US&ceid=US:en', 'Google News')
    fuentes += noticias_rss('https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss00001&q=' + ticker, 'CNBC')
    fuentes += noticias_sec(ticker)
    for n in fuentes:
        clave = n['titulo'].lower().strip()
        if clave and clave not in vistas:
            vistas.add(clave)
            todas.append(n)
    return todas[:20]

# ==========================================
# RESPALDO SIN IA (palabras clave)
# ==========================================

BULL = ['upgrade', 'merger', 'acquisition', 'record', 'growth', 'contract', 'partnership',
        'approval', 'surge', 'rally', 'jumps', 'beats', 'raises', 'buyback', 'strong', 'deal']
BEAR = ['downgrade', 'lawsuit', 'layoff', 'debt', 'default', 'recall', 'fraud', 'investigation',
        'drops', 'falls', 'sinks', 'plunge', 'cuts', 'weak', 'warning', 'loss', 'strike']

def veredicto_keyword(noticias):
    s = 0
    for n in noticias:
        low = n['titulo'].lower()
        s += sum(1 for w in BULL if w in low)
        s -= sum(1 for w in BEAR if w in low)
    if s > 0:
        return 'ALCISTA', s
    if s < 0:
        return 'BAJISTA', s
    return 'NEUTRO', s

# ==========================================
# ANALISIS CON GEMINI (gratis)
# ==========================================

MODELOS = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-flash-latest']

def limpiar_json(txt):
    txt = txt.strip()
    fence = chr(96) * 3
    if txt.startswith(fence):
        txt = txt.replace(fence, '')
        if txt.startswith('json'):
            txt = txt[4:]
    return txt.strip()

@st.cache_data(ttl=3600)
def analisis_gemini(ticker, key):
    """Pide a Gemini resumen en espanol + veredicto + enfoque en opciones"""
    if not key:
        return None
    noticias = todas_las_noticias(ticker)
    if not noticias:
        return None

    lista = "\n".join(["- " + n['titulo'] + " (" + n['fuente'] + ")" for n in noticias])
    sec = "\n".join(["- " + n['titulo'] for n in noticias if n['fuente'].startswith('SEC')]) or "- sin documentos recientes"

    prompt = "Eres un analista financiero experto en bolsa de EE.UU. y opciones OTM.\n"
    prompt += "Empresa: " + ticker + "\n\n"
    prompt += "NOTICIAS RECIENTES (titular | fuente):\n" + lista + "\n\n"
    prompt += "DOCUMENTOS OFICIALES SEC (8-K):\n" + sec + "\n\n"
    prompt += """Responde UNICAMENTE con este JSON valido, en espanol:
{
 "resumen": "resumen de 3-4 frases de la situacion actual de la empresa",
 "eventos": ["negociaciones, fusiones, contratos, demandas u otros eventos detectados"],
 "alcistas": ["razones concretas de posible subida"],
 "bajistas": ["razones concretas de posible baja"],
 "veredicto": "ALCISTA o BAJISTA o NEUTRO",
 "confianza": 75,
 "opciones": "conclusion de 2-3 frases para operar opciones OTM de esta empresa: que lado favorece (CALL / PUT / esperar) y por que",
 "titulares_traducidos": ["traduccion al espanol de los 5 titulares mas importantes"]
}"""

    for modelo in MODELOS:
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + modelo + ':generateContent?key=' + key
        body = {
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'temperature': 0.4, 'responseMimeType': 'application/json'}
        }
        try:
            r = requests.post(url, json=body, timeout=60)
            if r.status_code == 200:
                txt = r.json()['candidates'][0]['content']['parts'][0]['text']
                return json.loads(limpiar_json(txt))
        except Exception:
            pass
        time.sleep(2)
    return None

# ==========================================
# INTERFAZ
# ==========================================

st.title("RADAR DE NOTICIAS - INTELIGENCIA DE MERCADO")
st.caption("Fuentes gratuitas: Yahoo Finance, Google News, CNBC y SEC EDGAR | Analisis IA: Gemini (gratis)")

KEY = obtener_key_gemini()
if not KEY:
    st.warning("Sin clave GEMINI_API_KEY. La app mostrara las noticias y un sentimiento basico. Agrega la clave gratis en Streamlit Cloud -> Secrets para activar el analisis IA completo.")

st.divider()

# ---------- vista general de las 10 ----------
st.subheader("Vista general (10 empresas)")

with st.spinner("Recopilando noticias de las 10 empresas..."):
    filas = []
    for tk in TICKERS:
        notis = todas_las_noticias(tk)
        v, s = veredicto_keyword(notis)
        filas.append({
            'Ticker': tk,
            'Titulares': len(notis),
            'Sentimiento rapido': (ALTA + ' ' if v == 'ALCISTA' else BAJA + ' ' if v == 'BAJISTA' else NEU + ' ') + v,
            'Puntaje': s
        })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

st.caption("Selecciona una empresa abajo para el analisis completo con IA (resumen, eventos y enfoque en opciones).")

# ---------- panel lateral ----------
st.sidebar.header("Panel")
ticker_sel = st.sidebar.selectbox("Empresa a analizar con IA", TICKERS)
if st.sidebar.button("Recargar todo"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Como usar esta app:**\n"
    "1. Mira el veredicto IA y la confianza.\n"
    "2. Lee el enfoque en opciones OTM.\n"
    "3. Confirma el MOMENTO de entrada en el Radar de Francotirador.\n"
    "4. Nunca operes solo por noticia: espera vela formada."
)

# ---------- analisis completo de la empresa elegida ----------
st.divider()
st.subheader("Analisis completo: " + ticker_sel)

noticias_sel = todas_las_noticias(ticker_sel)
if not noticias_sel:
    st.info("No se encontraron noticias recientes de " + ticker_sel + ".")
else:
    with st.spinner("Gemini esta leyendo y traduciendo las noticias de " + ticker_sel + "..."):
        ia = analisis_gemini(ticker_sel, KEY)

    if ia:
        ver = str(ia.get('veredicto', 'NEUTRO')).upper()
        conf = ia.get('confianza', 0)
        if 'ALCISTA' in ver:
            st.success(ALTA + " VEREDICTO IA: ALCISTA | Confianza: " + str(conf) + "%")
        elif 'BAJISTA' in ver:
            st.error(BAJA + " VEREDICTO IA: BAJISTA | Confianza: " + str(conf) + "%")
        else:
            st.info(NEU + " VEREDICTO IA: NEUTRO | Confianza: " + str(conf) + "%")

        st.markdown("**Resumen economico:** " + str(ia.get('resumen', '')))

        st.info("**ENFOQUE EN OPCIONES OTM:** " + str(ia.get('opciones', '')))

        ev = ia.get('eventos', [])
        if ev:
            st.markdown("**Eventos corporativos detectados (negociaciones, fusiones, contratos...):**")
            for e in ev:
                st.markdown("- " + str(e))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Razones de subida:**")
            for e in ia.get('alcistas', []) or ['-']:
                st.markdown("- " + str(e))
        with c2:
            st.markdown("**Razones de baja:**")
            for e in ia.get('bajistas', []) or ['-']:
                st.markdown("- " + str(e))

        tt = ia.get('titulares_traducidos', [])
        if tt:
            st.markdown("**Titulares clave traducidos:**")
            for e in tt:
                st.markdown("- " + str(e))
    else:
        v, s = veredicto_keyword(noticias_sel)
        st.info("Analisis IA no disponible. Sentimiento rapido por palabras clave: " + v + " (puntaje " + str(s) + ").")

    with st.expander("Ver las " + str(len(noticias_sel)) + " noticias originales con enlace"):
        for n in noticias_sel:
            if n['link']:
                st.markdown("- [" + n['fuente'] + "](" + n['link'] + "): " + n['titulo'])
            else:
                st.markdown("- " + n['fuente'] + ": " + n['titulo'])
