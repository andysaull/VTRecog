import os
import re
import argparse
import json

def parsear_linea(linea):
    # Formato esperado: "PALABRA" (Conf: 0.99) - HH:MM:SS:mmm - CUADRANTE - file:///...
    patron = r'"(.*?)" \(Conf: ([\d.]+)\) - ([\d:.]+) - (\d+) - (file:.*)'
    match = re.search(patron, linea)
    
    if match:
        return {
            "word": match.group(1),
            "conf": float(match.group(2)),
            "time": match.group(3),
            "quad": int(match.group(4)),
            "src": match.group(5).strip()
        }
    return None

def generar_html(txt_input, html_output):
    print(f"📖 Leyendo: {txt_input}")
    
    data = []
    if os.path.exists(txt_input):
        with open(txt_input, "r", encoding="utf-8") as f:
            for line in f:
                parsed = parsear_linea(line)
                if parsed:
                    data.append(parsed)
    else:
        print("❌ Error: No se encuentra el archivo .txt")
        return

    print(f"✅ Se han procesado {len(data)} palabras.")
    
    # Convertimos los datos a JSON para incrustarlos en el HTML
    json_data = json.dumps(data)

    # --- PLANTILLA HTML (CSS + JS + ESTRUCTURA) ---
    html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visor de Detecciones OCR</title>
    <style>
        :root {{
            --bg-dark: #1e1e1e;
            --bg-panel: #252526;
            --text-main: #d4d4d4;
            --accent: #007acc;
            --accent-hover: #005f9e;
            --border: #3e3e42;
            --brace-color: #dcdcaa;
        }}
        
        body {{
            margin: 0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            overflow: hidden;
            height: 100vh;
            display: flex;
        }}

        /* --- SIDEBAR (IZQUIERDA) --- */
        .sidebar {{
            width: 400px;
            background-color: var(--bg-panel);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            height: 100%;
        }}

        .controls {{
            padding: 15px;
            border-bottom: 1px solid var(--border);
            background: #2d2d30;
        }}

        select {{
            width: 100%;
            padding: 8px;
            background: #3c3c3c;
            color: white;
            border: 1px solid var(--border);
            border-radius: 4px;
            font-size: 14px;
            outline: none;
        }}

        .list-container {{
            flex: 1;
            overflow-y: auto;
            padding: 10px 0;
        }}

        .list-item {{
            padding: 8px 15px;
            cursor: pointer;
            border-left: 3px solid transparent;
            transition: background 0.2s;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: relative;
        }}

        .list-item:hover {{
            background-color: #37373d;
            border-left-color: var(--accent);
        }}
        
        .list-item.active {{
            background-color: #094771;
            border-left-color: #0099ff;
        }}

        .word-info {{
            display: flex;
            flex-direction: column;
        }}

        .word-text {{
            font-size: 16px;
            font-weight: 600;
            color: #fff;
        }}

        .meta-info {{
            font-size: 12px;
            color: #888;
            margin-top: 2px;
        }}

        .conf-badge {{
            background: #333;
            padding: 1px 5px;
            border-radius: 3px;
            color: #4ec9b0;
            margin-right: 5px;
        }}

        /* --- VISUALIZACIÓN DE LLAVES (Agrupación) --- */
        .bracket-indicator {{
            width: 10px;
            height: 100%;
            position: absolute;
            right: 10px;
            top: 0;
            display: none; /* Por defecto oculto */
        }}

        /* Solo mostramos la llave si estamos ordenados por tiempo */
        .group-single .bracket-indicator {{ display: none; }}
        
        .group-start .bracket-indicator {{
            display: block;
            border-top: 2px solid var(--brace-color);
            border-right: 2px solid var(--brace-color);
            border-top-right-radius: 6px;
            height: 50%;
            top: 50%;
        }}

        .group-middle .bracket-indicator {{
            display: block;
            border-right: 2px solid var(--brace-color);
        }}

        .group-end .bracket-indicator {{
            display: block;
            border-bottom: 2px solid var(--brace-color);
            border-right: 2px solid var(--brace-color);
            border-bottom-right-radius: 6px;
            height: 50%;
            top: 0;
        }}

        /* --- PREVIEW (DERECHA) --- */
        .preview-area {{
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            background-image: 
                linear-gradient(45deg, #222 25%, transparent 25%), 
                linear-gradient(-45deg, #222 25%, transparent 25%), 
                linear-gradient(45deg, transparent 75%, #222 75%), 
                linear-gradient(-45deg, transparent 75%, #222 75%);
            background-size: 20px 20px;
            background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
            overflow: hidden;
            position: relative;
        }}

        .zoom-container {{
            width: 90%;
            height: 90%;
            overflow: hidden; /* CROP */
            box-shadow: 0 0 20px rgba(0,0,0,0.5);
            border: 1px solid #444;
            position: relative;
            background: black;
            display: flex;
            justify-content: center;
            align-items: center;
        }}

        #preview-img {{
            max-width: 100%;
            max-height: 100%;
            transition: transform 0.2s ease-out;
            transform-origin: center center;
            display: none; /* Oculto hasta hover */
        }}
        
        .placeholder-text {{
            color: #555;
            font-size: 20px;
        }}

        /* --- MODAL (FULL SCREEN) --- */
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.9);
            justify-content: center;
            align-items: center;
        }}

        .modal-content {{
            max-width: 95%;
            max-height: 95%;
            box-shadow: 0 0 30px rgba(0,0,0,0.8);
            border: 2px solid #333;
        }}

    </style>
</head>
<body>

    <div class="sidebar">
        <div class="controls">
            <label style="font-size:12px; color:#aaa; margin-bottom:5px; display:block;">ORDENAR POR:</label>
            <select id="sortSelect">
                <option value="time">Tiempo (Cronológico)</option>
                <option value="conf">Confianza (Mayor a menor)</option>
                <option value="alpha">Alfabético (A-Z)</option>
            </select>
        </div>
        <div class="list-container" id="wordList">
            </div>
    </div>

    <div class="preview-area">
        <div class="zoom-container">
            <p class="placeholder-text" id="placeholder">Pasa el ratón por una palabra</p>
            <img id="preview-img" src="" alt="Frame Preview">
        </div>
    </div>

    <div class="modal" id="imageModal">
        <img class="modal-content" id="modal-img">
    </div>

    <script>
        // DATOS INCRUSTADOS DESDE PYTHON
        const rawData = {json_data};
        
        const listContainer = document.getElementById('wordList');
        const sortSelect = document.getElementById('sortSelect');
        const previewImg = document.getElementById('preview-img');
        const placeholder = document.getElementById('placeholder');
        const modal = document.getElementById('imageModal');
        const modalImg = document.getElementById('modal-img');

        // Mapeo de Cuadrantes (1-9) a Transform Origin CSS
        const quadMap = {{
            1: "0% 0%",    2: "50% 0%",    3: "100% 0%",
            4: "0% 50%",   5: "50% 50%",   6: "100% 50%",
            7: "0% 100%",  8: "50% 100%",  9: "100% 100%"
        }};

        function renderList() {{
            listContainer.innerHTML = '';
            const sortMode = sortSelect.value;
            
            // Ordenar datos
            let data = [...rawData];
            if (sortMode === 'time') {{
                // Ya vienen ordenados por defecto, pero nos aseguramos
                // (Asumimos que el orden del array original es temporal)
            }} else if (sortMode === 'conf') {{
                data.sort((a, b) => b.conf - a.conf);
            }} else if (sortMode === 'alpha') {{
                data.sort((a, b) => a.word.localeCompare(b.word));
            }}

            data.forEach((item, index) => {{
                const div = document.createElement('div');
                div.className = 'list-item';
                
                // --- LÓGICA DE AGRUPACIÓN (LLAVES) ---
                if (sortMode === 'time') {{
                    const prev = data[index - 1];
                    const next = data[index + 1];
                    const isSamePrev = prev && prev.src === item.src;
                    const isSameNext = next && next.src === item.src;

                    if (!isSamePrev && !isSameNext) {{
                        div.classList.add('group-single');
                    }} else if (!isSamePrev && isSameNext) {{
                        div.classList.add('group-start');
                    }} else if (isSamePrev && isSameNext) {{
                        div.classList.add('group-middle');
                    }} else if (isSamePrev && !isSameNext) {{
                        div.classList.add('group-end');
                    }}
                }} else {{
                    div.classList.add('group-single');
                }}

                div.innerHTML = `
                    <div class="word-info">
                        <span class="word-text">${{item.word}}</span>
                        <div class="meta-info">
                            <span class="conf-badge">${{(item.conf * 100).toFixed(0)}}%</span>
                            ${{item.time}}
                        </div>
                    </div>
                    <div class="bracket-indicator"></div>
                `;

                // --- EVENTOS ---
                
                // HOVER: Zoom Inteligente
                div.addEventListener('mouseenter', () => {{
                    placeholder.style.display = 'none';
                    previewImg.style.display = 'block';
                    previewImg.src = item.src;
                    
                    // Aplicar Zoom según cuadrante
                    const origin = quadMap[item.quad] || "50% 50%";
                    previewImg.style.transformOrigin = origin;
                    previewImg.style.transform = "scale(2.5)"; // ZOOM x2.5
                }});

                // CLICK: Modal
                div.addEventListener('click', () => {{
                    modal.style.display = 'flex';
                    modalImg.src = item.src;
                }});

                listContainer.appendChild(div);
            }});
        }}

        // Event Listeners Globales
        sortSelect.addEventListener('change', renderList);
        
        // Cerrar modal
        modal.addEventListener('click', () => {{
            modal.style.display = 'none';
        }});

        // Render inicial
        renderList();

    </script>
</body>
</html>
    """

    with open(html_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"🚀 ¡Éxito! Visor generado en: {html_output}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de Visor HTML para OCR")
    parser.add_argument("input_txt", help="Ruta al archivo registro_detectado.txt")
    
    args = parser.parse_args()
    
    # Deducir nombre de salida
    folder = os.path.dirname(args.input_txt)
    output_html = os.path.join(folder, "visor_resultados.html")
    
    generar_html(args.input_txt, output_html)