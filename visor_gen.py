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

def parsear_linea(linea):
    # Formato nuevo: "PALABRA" (Conf: 0.99) - HH:MM:SS:mmm - [x1,y1,x2,y2] - file:///...
    patron = r'"(.*?)" \(Conf: ([\d.]+)\) - ([\d:.]+) - \[(\d+),(\d+),(\d+),(\d+)\] - (file:.*)'
    match = re.search(patron, linea)
    
    if match:
        return {
            "word": match.group(1),
            "conf": float(match.group(2)),
            "time": match.group(3),
            "box": {
                "x1": int(match.group(4)),
                "y1": int(match.group(5)),
                "x2": int(match.group(6)),
                "y2": int(match.group(7))
            },
            "src": match.group(8).strip()
        }
    return None

def generar_html(txt_input, html_output):
    print(f"📖 Leyendo: {txt_input}")
    
    data = []
    video_w, video_h = 1920, 1080 # Default fallback
    
    if os.path.exists(txt_input):
        with open(txt_input, "r", encoding="utf-8") as f:
            # Leer primera línea para buscar resolución
            header = f.readline()
            w_found, h_found = parsear_header(header)
            if w_found:
                video_w, video_h = w_found, h_found
                print(f"🖥️ Resolución detectada: {video_w}x{video_h}")
            
            # Leer el resto
            for line in f:
                parsed = parsear_linea(line)
                if parsed:
                    data.append(parsed)
    else:
        print("❌ Error: No se encuentra el archivo .txt")
        return

    print(f"✅ Se han procesado {len(data)} palabras.")
    
    json_data = json.dumps(data)
    json_dims = json.dumps({"w": video_w, "h": video_h})

    # --- HTML ---
    html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visor OCR PRO</title>
    <style>
        :root {{ --bg-dark: #1e1e1e; --bg-panel: #252526; --text-main: #d4d4d4; --accent: #007acc; --border: #3e3e42; --brace: #dcdcaa; }}
        body {{ margin: 0; font-family: 'Segoe UI', sans-serif; background: var(--bg-dark); color: var(--text-main); overflow: hidden; height: 100vh; display: flex; }}
        
        /* SIDEBAR */
        .sidebar {{ width: 420px; background: var(--bg-panel); border-right: 1px solid var(--border); display: flex; flex-direction: column; }}
        .controls {{ padding: 15px; background: #2d2d30; border-bottom: 1px solid var(--border); }}
        select {{ width: 100%; padding: 8px; background: #3c3c3c; color: white; border: 1px solid #555; }}
        
        .list-container {{ flex: 1; overflow-y: auto; }}
        .list-item {{ padding: 10px 15px; cursor: pointer; border-left: 3px solid transparent; display: flex; justify-content: space-between; position: relative; transition: 0.1s; }}
        .list-item:hover {{ background: #37373d; border-left-color: var(--accent); }}
        
        .word-text {{ font-size: 15px; font-weight: bold; color: #fff; display: block; }}
        .meta-info {{ font-size: 12px; color: #888; margin-top: 3px; }}
        .conf-badge {{ background: #333; padding: 2px 5px; border-radius: 3px; color: #4ec9b0; margin-right: 8px; }}

        /* LLAVES */
        .bracket {{ position: absolute; right: 10px; width: 10px; border-color: var(--brace); display: none; }}
        .g-start .bracket {{ display: block; height: 50%; top: 50%; border-top: 2px solid; border-right: 2px solid; border-top-right-radius: 6px; }}
        .g-mid .bracket {{ display: block; height: 100%; top: 0; border-right: 2px solid; }}
        .g-end .bracket {{ display: block; height: 50%; top: 0; border-bottom: 2px solid; border-right: 2px solid; border-bottom-right-radius: 6px; }}

        /* PREVIEW AREA */
        .preview-area {{ flex: 1; background: #111; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; }}
        
        /* Contenedor de la imagen recortada */
        .zoom-frame {{
            width: 90%; height: 90%; 
            position: relative; overflow: hidden; 
            box-shadow: 0 0 50px rgba(0,0,0,0.8);
            border: 1px solid #333;
            background: #000;
            display: flex; align-items: center; justify-content: center;
        }}
        
        #preview-img {{
            max-width: 100%; max-height: 100%;
            /* La magia del zoom ocurre aquí */
            transform-origin: center center;
            transition: transform 0.2s cubic-bezier(0.25, 0.46, 0.45, 0.94);
        }}
        
        .placeholder {{ color: #444; font-size: 1.5rem; }}

        /* MODAL */
        .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 999; justify-content: center; align-items: center; cursor: zoom-out; }}
        .modal img {{ max-width: 95%; max-height: 95%; box-shadow: 0 0 20px #000; border: 2px solid #555; }}
    </style>
</head>
<body>

<div class="sidebar">
    <div class="controls">
        <select id="sortSelect">
            <option value="time">Orden: Cronológico (Tiempo)</option>
            <option value="conf">Orden: Confianza (Mejor a peor)</option>
            <option value="alpha">Orden: Alfabético (A-Z)</option>
        </select>
    </div>
    <div class="list-container" id="list"></div>
</div>

<div class="preview-area">
    <div class="zoom-frame">
        <p class="placeholder" id="ph">Pasa el ratón por la lista</p>
        <img id="preview-img" src="">
    </div>
</div>

<div class="modal" id="modal">
    <img id="modal-img">
</div>

<script>
    const data = {json_data};
    const dims = {json_dims}; // {{w: 1920, h: 1080}}
    
    const listEl = document.getElementById('list');
    const sortEl = document.getElementById('sortSelect');
    const imgEl = document.getElementById('preview-img');
    const phEl = document.getElementById('ph');
    const modal = document.getElementById('modal');
    const modalImg = document.getElementById('modal-img');

    function render() {{
        listEl.innerHTML = '';
        const mode = sortEl.value;
        
        let sorted = [...data];
        if (mode === 'conf') sorted.sort((a,b) => b.conf - a.conf);
        if (mode === 'alpha') sorted.sort((a,b) => a.word.localeCompare(b.word));
        // time es default

        sorted.forEach((item, i) => {{
            const div = document.createElement('div');
            div.className = 'list-item';
            
            // Lógica de llaves
            if (mode === 'time') {{
                const p = sorted[i-1]; const n = sorted[i+1];
                const sameP = p && p.src === item.src;
                const sameN = n && n.src === item.src;
                if (!sameP && sameN) div.classList.add('g-start');
                else if (sameP && sameN) div.classList.add('g-mid');
                else if (sameP && !sameN) div.classList.add('g-end');
            }}

            div.innerHTML = `
                <div>
                    <span class="word-text">${{item.word}}</span>
                    <div class="meta-info">
                        <span class="conf-badge">${{Math.floor(item.conf*100)}}%</span> 
                        ${{item.time}}
                    </div>
                </div>
                <div class="bracket"></div>
            `;

            // --- LÓGICA DE ZOOM ---
            div.addEventListener('mouseenter', () => {{
                phEl.style.display = 'none';
                imgEl.style.display = 'block';
                imgEl.src = item.src;

                // 1. Calcular Centro de la palabra
                const boxW = item.box.x2 - item.box.x1;
                const boxH = item.box.y2 - item.box.y1;
                const centerX = item.box.x1 + (boxW / 2);
                const centerY = item.box.y1 + (boxH / 2);

                // 2. Convertir a Porcentajes (para CSS)
                const originX = (centerX / dims.w) * 100;
                const originY = (centerY / dims.h) * 100;

                // 3. Calcular Escala (Con Contexto)
                // Calculamos cuánto tendríamos que ampliar para que la palabra ocupe TODA la pantalla
                const scaleX = dims.w / boxW;
                const scaleY = dims.h / boxH;
                
                // Nos quedamos con la menor (para que quepa entera) y la reducimos
                // Multiplicamos por 0.3 para dejar mucho "aire" (Contexto)
                let scale = Math.min(scaleX, scaleY) * 0.35; 
                
                // Límites de seguridad (ni muy pequeño ni gigantesco)
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
    modal.addEventListener('click', () => modal.style.display = 'none');
    render();
</script>
</body>
</html>
    """

    with open(html_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"🚀 Visor generado: {html_output}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_txt", help="Ruta al txt")
    args = parser.parse_args()
    
    folder = os.path.dirname(args.input_txt)
    output_html = os.path.join(folder, "visor_resultados.html")
    
    generar_html(args.input_txt, output_html)