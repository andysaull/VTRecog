import os
import re
import argparse
import json

def parsear_header(linea):
    """Busca la resolución en la cabecera: RES: 1920x1080"""
    match = re.search(r'RES: (\d+)x(\d+)', linea)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None

def time_to_seconds(time_str):
    """Convierte HH:MM:SS:mmm a segundos (float)"""
    try:
        parts = time_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2])
        ms = int(parts[3])
        return (h * 3600) + (m * 60) + s + (ms / 1000.0)
    except:
        return 0.0

def parsear_linea(linea):
    # Formato: "PALABRA" (Conf: 0.99) - HH:MM:SS:mmm - [x1,y1,x2,y2] - file:///...
    patron = r'"(.*?)" \(Conf: ([\d.]+)\) - ([\d:.]+) - \[(\d+),(\d+),(\d+),(\d+)\] - (file:.*)'
    match = re.search(patron, linea)
    
    if match:
        time_str = match.group(3)
        return {
            "word": match.group(1),
            "conf": float(match.group(2)),
            "time": time_str,
            "seconds": time_to_seconds(time_str),
            "box": {
                "x1": int(match.group(4)),
                "y1": int(match.group(5)),
                "x2": int(match.group(6)),
                "y2": int(match.group(7))
            },
            "src": match.group(8).strip()
        }
    return None

def cargar_diccionario(ruta_diccionario):
    palabras = []
    if os.path.exists(ruta_diccionario):
        print(f"📚 Cargando diccionario: {ruta_diccionario}")
        with open(ruta_diccionario, "r", encoding="utf-8") as f:
            for linea in f:
                w = linea.strip().upper()
                if len(w) > 3: 
                    palabras.append(w)
        palabras.sort(key=len, reverse=True)
    else:
        print("⚠️ NO SE ENCONTRÓ diccionario_es.txt.")
        palabras = "HOLA ADIOS COCHE CASA".split()
    return palabras

def procesar_coincidencias(data, diccionario):
    print("🔍 Analizando español...")
    for item in data:
        original_word = item['word']
        upper_word = original_word.upper()
        item['hasSpanish'] = False
        item['displayHtml'] = original_word
        
        if len(upper_word) > 3:
            for dict_word in diccionario:
                if dict_word in upper_word:
                    item['hasSpanish'] = True
                    regex = re.compile(re.escape(dict_word), re.IGNORECASE)
                    item['displayHtml'] = regex.sub(r'<span class="highlight">\g<0></span>', original_word)
                    break
    return data

def generar_html(txt_input, video_path, html_output):
    print(f"📖 Leyendo reporte: {txt_input}")
    
    data = []
    video_w, video_h = 1920, 1080 
    
    if os.path.exists(txt_input):
        with open(txt_input, "r", encoding="utf-8") as f:
            header = f.readline()
            w_found, h_found = parsear_header(header)
            if w_found:
                video_w, video_h = w_found, h_found
            
            for line in f:
                parsed = parsear_linea(line)
                if parsed:
                    data.append(parsed)
    else:
        print("❌ Error: No se encuentra el TXT")
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    dicc_path = os.path.join(script_dir, "diccionario_es.txt")
    diccionario = cargar_diccionario(dicc_path)
    data = procesar_coincidencias(data, diccionario)
    
    abs_video_path = os.path.abspath(video_path).replace(os.sep, '/')
    video_src = f"file:///{abs_video_path}"

    json_data = json.dumps(data)
    json_dims = json.dumps({"w": video_w, "h": video_h})

    html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visor OCR Overlay</title>
    <style>
        :root {{ --bg-dark: #1e1e1e; --bg-panel: #252526; --text-main: #d4d4d4; --accent: #007acc; --border: #3e3e42; --brace: #dcdcaa; --highlight: #ff4d4d; }}
        body {{ margin: 0; font-family: 'Segoe UI', sans-serif; background: var(--bg-dark); color: var(--text-main); overflow: hidden; height: 100vh; display: flex; }}
        
        .sidebar {{ width: 450px; background: var(--bg-panel); border-right: 1px solid var(--border); display: flex; flex-direction: column; z-index: 50; }}
        
        .controls {{ padding: 15px; background: #2d2d30; border-bottom: 1px solid var(--border); }}
        .controls label {{ display: block; margin-top: 10px; font-size: 14px; cursor: pointer; }}
        select {{ width: 100%; padding: 8px; background: #3c3c3c; color: white; border: 1px solid #555; outline: none; }}
        
        .list-container {{ flex: 1; overflow-y: auto; }}
        .list-item {{ padding: 8px 15px; cursor: pointer; border-left: 3px solid transparent; display: flex; align-items: center; justify-content: space-between; position: relative; transition: 0.1s; border-bottom: 1px solid #333; }}
        .list-item:hover {{ background: #37373d; border-left-color: var(--accent); }}
        
        .word-content {{ flex: 1; }}
        .word-text {{ font-size: 15px; font-weight: bold; color: #fff; display: block; }}
        .meta-info {{ font-size: 12px; color: #888; margin-top: 3px; }}
        .conf-badge {{ background: #333; padding: 2px 5px; border-radius: 3px; color: #4ec9b0; margin-right: 8px; }}
        .highlight {{ color: var(--highlight); text-shadow: 0 0 10px rgba(255, 77, 77, 0.2); font-weight: 900; }}

        .play-btn {{
            background: #2d2d30; border: 1px solid #555; color: #fff;
            width: 30px; height: 30px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            margin-right: 10px; cursor: pointer; transition: 0.2s; font-size: 12px;
        }}
        .play-btn:hover {{ background: var(--accent); border-color: var(--accent); transform: scale(1.1); }}

        .bracket {{ position: absolute; right: 5px; width: 8px; border-color: var(--brace); display: none; opacity: 0.7; }}
        .g-start .bracket {{ display: block; height: 50%; top: 50%; border-top: 2px solid; border-right: 2px solid; border-top-right-radius: 6px; }}
        .g-mid .bracket {{ display: block; height: 100%; top: 0; border-right: 2px solid; }}
        .g-end .bracket {{ display: block; height: 50%; top: 0; border-bottom: 2px solid; border-right: 2px solid; border-bottom-right-radius: 6px; }}

        /* CONTENEDOR DERECHO */
        .right-panel {{ flex: 1; position: relative; background: #000; overflow: hidden; }}
        
        /* VIDEO FLOTANTE (Overlay) */
        .video-overlay {{
            position: absolute;
            top: 0;
            right: 0;
            width: 480px; /* Tamaño fijo razonable (1/4 de FHD) */
            height: auto;
            z-index: 100; /* Por encima de la foto */
            background: #000;
            border-bottom: 2px solid #333;
            border-left: 2px solid #333;
            box-shadow: -5px 5px 20px rgba(0,0,0,0.8);
            transition: opacity 0.3s;
            opacity: 0.8; /* Semi-transparente para ver debajo */
        }}
        .video-overlay:hover {{ opacity: 1; }} /* Opaco al usarlo */
        video {{ width: 100%; display: block; }}
        
        /* AREA DE ZOOM (Ahora ocupa todo el fondo) */
        .preview-area {{ width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }}
        
        /* Marco de la foto con márgenes */
        .zoom-frame {{ 
            width: 90%; height: 90%; 
            position: relative; overflow: hidden; 
            border: 1px solid #333; 
            background: #000; 
            display: flex; align-items: center; justify-content: center; 
        }}
        
        #preview-img {{ max-width: 100%; max-height: 100%; transform-origin: center center; transition: transform 0.2s; }}
        .placeholder {{ color: #444; font-size: 1.5rem; }}

        .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 999; justify-content: center; align-items: center; cursor: zoom-out; }}
        .modal img {{ max-width: 95%; max-height: 95%; box-shadow: 0 0 20px #000; border: 2px solid #555; }}
    </style>
</head>
<body>

<div class="sidebar">
    <div class="controls">
        <select id="sortSelect">
            <option value="time">Orden: Cronológico</option>
            <option value="conf">Orden: Confianza</option>
            <option value="alpha">Orden: Alfabético</option>
        </select>
        <label><input type="checkbox" id="spanishCheck" checked> Priorizar Español</label>
    </div>
    <div class="list-container" id="list"></div>
</div>

<div class="right-panel">
    <div class="video-overlay">
        <video id="mainVideo" controls>
            <source src="{video_src}" type="video/mp4">
            <source src="{video_src}" type="video/webm">
        </video>
    </div>

    <div class="preview-area">
        <div class="zoom-frame">
            <p class="placeholder" id="ph">Pasa el ratón por la lista</p>
            <img id="preview-img" src="">
        </div>
    </div>
</div>

<div class="modal" id="modal">
    <img id="modal-img">
</div>

<script>
    const data = {json_data};
    const dims = {json_dims};

    const listEl = document.getElementById('list');
    const sortEl = document.getElementById('sortSelect');
    const esCheck = document.getElementById('spanishCheck');
    const imgEl = document.getElementById('preview-img');
    const phEl = document.getElementById('ph');
    const modal = document.getElementById('modal');
    const modalImg = document.getElementById('modal-img');
    const video = document.getElementById('mainVideo');

    function playSegment(seconds) {{
        const start = Math.max(0, seconds - 0.5);
        const end = seconds + 0.5;
        video.currentTime = start;
        video.play();
        const stopListener = () => {{
            if (video.currentTime >= end) {{
                video.pause();
                video.removeEventListener('timeupdate', stopListener);
            }}
        }};
        video.removeEventListener('timeupdate', stopListener); 
        video.addEventListener('timeupdate', stopListener);
    }}

    function render() {{
        listEl.innerHTML = '';
        const mode = sortEl.value;
        const prioritizeEs = esCheck.checked;
        
        let sorted = [...data];
        
        sorted.sort((a, b) => {{
            if (prioritizeEs) {{
                if (a.hasSpanish && !b.hasSpanish) return -1;
                if (!a.hasSpanish && b.hasSpanish) return 1;
            }}
            if (mode === 'conf') return b.conf - a.conf;
            if (mode === 'alpha') return a.word.localeCompare(b.word);
            return 0; 
        }});

        sorted.forEach((item, i) => {{
            const div = document.createElement('div');
            div.className = 'list-item';
            
            const p = sorted[i-1]; const n = sorted[i+1];
            const sameP = p && p.src === item.src;
            const sameN = n && n.src === item.src;
            if (!sameP && sameN) div.classList.add('g-start');
            else if (sameP && sameN) div.classList.add('g-mid');
            else if (sameP && !sameN) div.classList.add('g-end');

            div.innerHTML = `
                <div class="play-btn" title="Ver clip">▶</div>
                <div class="word-content">
                    <span class="word-text">${{item.displayHtml}}</span>
                    <div class="meta-info">
                        <span class="conf-badge">${{Math.floor(item.conf*100)}}%</span> 
                        ${{item.time}}
                    </div>
                </div>
                <div class="bracket"></div>
            `;

            const btn = div.querySelector('.play-btn');
            btn.addEventListener('click', (e) => {{
                e.stopPropagation();
                playSegment(item.seconds);
            }});

            div.addEventListener('mouseenter', () => {{
                phEl.style.display = 'none';
                imgEl.style.display = 'block';
                imgEl.src = item.src;

                const boxW = item.box.x2 - item.box.x1;
                const boxH = item.box.y2 - item.box.y1;
                const centerX = item.box.x1 + (boxW / 2);
                const centerY = item.box.y1 + (boxH / 2);

                const originX = (centerX / dims.w) * 100;
                const originY = (centerY / dims.h) * 100;
                
                const scaleX = dims.w / boxW;
                const scaleY = dims.h / boxH;
                let scale = Math.min(scaleX, scaleY) * 0.35; 
                if (scale < 1) scale = 1; 
                if (scale > 5) scale = 5; 

                imgEl.style.transformOrigin = `${{originX}}% ${{originY}}%`;
                imgEl.style.transform = `scale(${{scale}})`;
            }});

            div.addEventListener('click', () => {{
                modal.style.display = 'flex';
                modalImg.src = item.src;
            }});

            listEl.appendChild(div);
        }});
    }}

    sortEl.addEventListener('change', render);
    esCheck.addEventListener('change', render);
    modal.addEventListener('click', () => modal.style.display = 'none');
    
    render();
</script>
</body>
</html>
    """

    with open(html_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"🚀 Visor Overlay generado en: {html_output}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_txt", help="Ruta al txt")
    parser.add_argument("--video", required=True, help="Ruta al video")
    args = parser.parse_args()
    
    folder = os.path.dirname(args.input_txt)
    output_html = os.path.join(folder, "visor_resultados.html")
    
    generar_html(args.input_txt, args.video, output_html)