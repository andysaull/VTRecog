import argparse
import json
import logging
import os
import re
import time
from multiprocessing import Pool, cpu_count
from typing import List, Tuple, Dict, Any, Optional

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# Pre-compile regular expressions for performance
HEADER_REGEX = re.compile(r'RES: (\d+)x(\d+)')
LINE_REGEX = re.compile(r'"(.*?)" \(Conf: ([\d.]+)\) - ([\d:.]+) - \[(\d+),(\d+),(\d+),(\d+)\] - (file:.*)')


def parse_header(line: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Extracts video resolution from the header line.
    """
    match = HEADER_REGEX.search(line)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def time_to_seconds(time_str: str) -> float:
    """
    Converts a timestamp string (HH:MM:SS:mmm) to total seconds.
    """
    try:
        parts = time_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2])
        ms = int(parts[3])
        return (h * 3600) + (m * 60) + s + (ms / 1000.0)
    except (ValueError, IndexError):
        logging.warning(f"Failed to parse time string: {time_str}")
        return 0.0


def parse_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line into a structured dictionary.
    """
    match = LINE_REGEX.search(line)
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


def load_dictionary(dictionary_path: str) -> List[str]:
    """
    Loads a list of target words from a text file, sorted by length descending.
    """
    words = []
    if os.path.exists(dictionary_path):
        logging.info(f"Loading dictionary from: {dictionary_path}")
        with open(dictionary_path, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().upper()
                if len(w) > 1: 
                    words.append(w)
        words.sort(key=len, reverse=True)
    else:
        logging.warning("Dictionary file not found. Falling back to default list.")
        words = ["HELLO", "BYE", "CAR", "HOUSE"]
    return words


def process_data_chunk(chunk_data: List[Dict[str, Any]], dictionary: List[str]) -> List[Dict[str, Any]]:
    """
    Worker function to process a subset of OCR data, identifying target words.
    """
    processed_chunk = []
    
    for item in chunk_data:
        original_word = item['word']
        upper_word = original_word.upper()
        item['hasTargetLanguage'] = False
        item['displayHtml'] = original_word
        
        if len(upper_word) > 1:
            for dict_word in dictionary:
                if dict_word in upper_word:
                    item['hasTargetLanguage'] = True
                    # Highlight the found word using regex
                    regex = re.compile(re.escape(dict_word), re.IGNORECASE)
                    item['displayHtml'] = regex.sub(r'<span class="highlight">\g<0></span>', original_word)
                    break
        
        processed_chunk.append(item)
        
    return processed_chunk


def generate_multiprocess_html(txt_input: str, video_path: str, html_output: str) -> None:
    """
    Main function to read OCR logs, process them in parallel, and generate an interactive HTML viewer.
    """
    logging.info(f"Reading report: {txt_input}")
    
    raw_data = []
    video_w, video_h = 1920, 1080 
    
    if not os.path.exists(txt_input):
        logging.error("Input TXT file not found.")
        return

    with open(txt_input, "r", encoding="utf-8") as f:
        header = f.readline()
        w_found, h_found = parse_header(header)
        if w_found and h_found:
            video_w, video_h = w_found, h_found
        
        for line in f:
            parsed = parse_line(line)
            if parsed:
                raw_data.append(parsed)

    total_words = len(raw_data)
    logging.info(f"Total detected words: {total_words}")

    # Load Dictionary
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dicc_path = os.path.join(script_dir, "diccionario_es.txt")
    dictionary = load_dictionary(dicc_path)
    logging.info(f"Dictionary loaded with {len(dictionary)} terms.")

    # Multiprocessing setup
    num_cores = cpu_count()
    logging.info(f"Starting parallel analysis using {num_cores} CPU cores...")
    
    start_time = time.time()
    
    if total_words > 0:
        chunk_size = (total_words // num_cores) + 1
        chunks = [raw_data[i:i + chunk_size] for i in range(0, total_words, chunk_size)]
        pool_args = [(chunk, dictionary) for chunk in chunks]
        
        with Pool(processes=num_cores) as pool:
            results = pool.starmap(process_data_chunk, pool_args)
        
        final_data = [item for sublist in results for item in sublist]
    else:
        final_data = []
    
    elapsed = time.time() - start_time
    logging.info(f"Analysis completed in {elapsed:.2f} seconds.")

    # Prepare paths and data for HTML
    abs_video_path = os.path.abspath(video_path).replace(os.sep, '/')
    video_src = f"file:///{abs_video_path}"

    json_data = json.dumps(final_data)
    json_dims = json.dumps({"w": video_w, "h": video_h})

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Final OCR Viewer</title>
    <style>
        :root {{ --bg-dark: #1e1e1e; --bg-panel: #252526; --text-main: #d4d4d4; --accent: #007acc; --border: #3e3e42; --brace: #dcdcaa; --highlight: #ff4d4d; }}
        body {{ margin: 0; font-family: 'Segoe UI', sans-serif; background: var(--bg-dark); color: var(--text-main); overflow: hidden; height: 100vh; display: flex; }}
        
        .sidebar {{ width: 520px; background: var(--bg-panel); border-right: 1px solid var(--border); display: flex; flex-direction: column; z-index: 50; }}
        
        /* CONTROLS */
        .controls {{ padding: 15px; background: #2d2d30; border-bottom: 1px solid var(--border); box-shadow: 0 2px 5px rgba(0,0,0,0.2); }}
        .control-group {{ margin-bottom: 12px; }}
        .control-label {{ display: block; margin-bottom: 5px; font-size: 13px; color: #aaa; font-weight: 600; }}
        
        .checkbox-label {{ display: flex; align-items: center; cursor: pointer; font-size: 14px; user-select: none; margin-bottom: 5px; }}
        .checkbox-label input {{ margin-right: 8px; }}
        
        select {{ width: 100%; padding: 6px; background: #3c3c3c; color: white; border: 1px solid #555; outline: none; border-radius: 4px; }}
        
        /* NUMERIC INPUTS & BUTTON */
        .range-inputs {{ display: flex; gap: 5px; align-items: center; }}
        .range-inputs input {{ width: 60px; background: #3c3c3c; color: white; border: 1px solid #555; padding: 4px; text-align: center; }}
        .range-inputs span {{ color: #888; }}
        
        .btn-update {{ 
            width: 100%; margin-top: 8px; padding: 6px; 
            background: var(--accent); color: white; border: none; border-radius: 4px; 
            cursor: pointer; font-weight: bold; transition: background 0.2s;
        }}
        .btn-update:hover {{ background: #005a9e; }}
        .btn-update:active {{ transform: translateY(1px); }}

        .list-container {{ flex: 1; overflow-y: auto; padding-bottom: 20px; }}
        
        .list-item {{ 
            padding: 8px 15px; cursor: pointer; border-left: 3px solid transparent; 
            display: flex; align-items: center; justify-content: space-between; 
            position: relative; transition: 0.1s; border-bottom: 1px solid #333;
        }}
        .list-item:nth-child(odd) {{ background-color: rgba(255,255,255,0.02); }}
        .list-item:nth-child(even) {{ background-color: rgba(0,0,0,0.1); }}
        .list-item:hover {{ background-color: #37373d !important; border-left-color: var(--accent); }}

        /* GROUPING */
        .group-wrapper {{
            margin: 6px 4px; background-color: #202022; border: 2px solid #555;
            border-left: 6px solid #dcdcaa; border-radius: 4px;
            box-shadow: 2px 2px 8px rgba(0,0,0,0.4); overflow: hidden; transition: all 0.2s;
        }}
        .group-wrapper .list-item:last-child {{ border-bottom: none; }}
        .group-header {{ background-color: #2a2a2d; font-weight: bold; }}
        .group-children {{ display: none; background: #181818; }}
        .group-children .list-item {{ padding-left: 25px; border-bottom: 1px solid #2a2a2a; font-size: 0.95em; color: #bbb; }}
        
        .expand-btn {{
            cursor: pointer; padding: 4px 8px; font-size: 12px; color: #aaa;
            display: flex; align-items: center; gap: 5px;
            background: rgba(0,0,0,0.3); border-radius: 4px; margin-left: 5px;
        }}
        .expand-btn:hover {{ color: #fff; background: rgba(255,255,255,0.1); }}
        .arrow {{ transition: transform 0.2s; display: inline-block; }}
        .count-badge {{ background: #007acc; color: white; border-radius: 10px; padding: 0 6px; font-size: 10px; font-weight: bold; }}
        .expanded .arrow {{ transform: rotate(180deg); }}
        .expanded + .group-children {{ display: block; }}

        /* ACTIONS */
        .actions {{ display: flex; gap: 5px; margin-right: 10px; min-width: 60px; }}
        .icon-btn {{
            background: #2d2d30; border: 1px solid #555; color: #fff;
            width: 24px; height: 24px; border-radius: 4px;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; transition: 0.2s; font-size: 12px; user-select: none;
        }}
        .icon-btn:hover {{ background: var(--accent); border-color: var(--accent); }}
        .copied {{ background: #4ec9b0 !important; color: #000 !important; }}

        .word-content {{ flex: 1; min-width: 0; }}
        .word-text {{ font-size: 14px; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .meta-info {{ font-size: 11px; color: #888; margin-top: 2px; }}
        .conf-badge {{ background: #333; padding: 1px 4px; border-radius: 3px; color: #4ec9b0; margin-right: 8px; }}
        .highlight {{ color: var(--highlight); text-shadow: 0 0 10px rgba(255, 77, 77, 0.2); font-weight: 900; }}

        .bracket {{ position: absolute; right: 2px; width: 6px; border-color: var(--brace); display: none; opacity: 0.7; }}
        .g-start .bracket {{ display: block; height: 50%; top: 50%; border-top: 2px solid; border-right: 2px solid; border-top-right-radius: 6px; }}
        .g-mid .bracket {{ display: block; height: 100%; top: 0; border-right: 2px solid; }}
        .g-end .bracket {{ display: block; height: 50%; top: 0; border-bottom: 2px solid; border-right: 2px solid; border-bottom-right-radius: 6px; }}

        .right-panel {{ flex: 1; position: relative; background: #000; overflow: hidden; }}
        .video-overlay {{
            position: absolute; top: 0; right: 0; width: 480px; z-index: 100;
            background: #000; border-bottom: 2px solid #333; border-left: 2px solid #333;
            box-shadow: -5px 5px 20px rgba(0,0,0,0.8); opacity: 0.9; transition: opacity 0.3s;
        }}
        .video-overlay:hover {{ opacity: 1; }}
        video {{ width: 100%; display: block; }}
        .preview-area {{ width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }}
        .zoom-frame {{ width: 90%; height: 90%; position: relative; overflow: hidden; border: 1px solid #333; background: #000; display: flex; align-items: center; justify-content: center; }}
        #preview-img {{ max-width: 100%; max-height: 100%; transform-origin: center center; transition: transform 0.2s; }}
        .placeholder {{ color: #444; font-size: 1.5rem; }}

        .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 999; justify-content: center; align-items: center; cursor: zoom-out; }}
        .modal img {{ max-width: 95%; max-height: 95%; box-shadow: 0 0 20px #000; border: 2px solid #555; }}
    </style>
</head>
<body>

<div class="sidebar">
    <div class="controls">
        <div class="control-group">
            <span class="control-label">SORTING</span>
            <select id="sortSelect">
                <option value="time">Chronological (Time)</option>
                <option value="conf">Confidence</option>
                <option value="alpha">Alphabetical</option>
            </select>
        </div>
        
        <div class="control-group">
            <span class="control-label">OPTIONS</span>
            <label class="checkbox-label">
                <input type="checkbox" id="languageCheck" checked> Prioritize Target Language
            </label>
            <label class="checkbox-label">
                <input type="checkbox" id="groupCheck"> Lexical Grouping
            </label>
            <label class="checkbox-label">
                <input type="checkbox" id="noSpaceCheck"> <strong>Hide Phrases</strong> (with spaces)
            </label>
        </div>

        <div class="control-group">
            <span class="control-label">CONFIDENCE RANGE (%)</span>
            <div class="range-inputs">
                <input type="number" id="confMin" value="0" min="0" max="100" placeholder="Min">
                <span>-</span>
                <input type="number" id="confMax" value="100" min="0" max="100" placeholder="Max">
            </div>
            <button id="btnUpdateConf" class="btn-update">Update Filter</button>
        </div>
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
            <p class="placeholder" id="ph">Hover over the list</p>
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
    
    // Checkboxes
    const langCheck = document.getElementById('languageCheck');
    const grCheck = document.getElementById('groupCheck');
    const noSpaceCheck = document.getElementById('noSpaceCheck');
    
    // Confidence Range
    const confMinInput = document.getElementById('confMin');
    const confMaxInput = document.getElementById('confMax');
    const btnUpdate = document.getElementById('btnUpdateConf');

    const imgEl = document.getElementById('preview-img');
    const phEl = document.getElementById('ph');
    const modal = document.getElementById('modal');
    const modalImg = document.getElementById('modal-img');
    const video = document.getElementById('mainVideo');

    function levenshtein(a, b) {{
        if (a.length === 0) return b.length;
        if (b.length === 0) return a.length;
        const matrix = [];
        for (let i = 0; i <= b.length; i++) matrix[i] = [i];
        for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
        for (let i = 1; i <= b.length; i++) {{
            for (let j = 1; j <= a.length; j++) {{
                if (b.charAt(i - 1) === a.charAt(j - 1)) matrix[i][j] = matrix[i - 1][j - 1];
                else matrix[i][j] = Math.min(matrix[i - 1][j - 1] + 1, Math.min(matrix[i][j - 1] + 1, matrix[i - 1][j] + 1));
            }}
        }}
        return matrix[b.length][a.length];
    }}

    function areWordsSimilar(w1, w2) {{
        w1 = w1.toUpperCase(); w2 = w2.toUpperCase();
        if (w1 === w2) return true;
        const maxLen = Math.max(w1.length, w2.length);
        if (maxLen === 0) return true;
        const dist = levenshtein(w1, w2);
        const similarity = 1 - (dist / maxLen);
        let threshold = 0.8; 
        if (maxLen > 10) threshold = 0.7;
        return similarity >= threshold;
    }}

    function groupData(items) {{
        const groups = [];
        const processedIndices = new Set();
        for (let i = 0; i < items.length; i++) {{
            if (processedIndices.has(i)) continue;
            const leader = items[i];
            const group = {{ leader: leader, children: [] }};
            processedIndices.add(i);
            for (let j = i + 1; j < items.length; j++) {{
                if (processedIndices.has(j)) continue;
                const candidate = items[j];
                if (areWordsSimilar(leader.word, candidate.word)) {{
                    group.children.push(candidate);
                    processedIndices.add(j);
                }}
            }}
            groups.push(group);
        }}
        return groups;
    }}

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

    function copyMetadata(item, btnElement) {{
        const text = `"${{item.word}}" (Conf: ${{item.conf.toFixed(2)}}) - ${{item.time}} - [${{item.box.x1}},${{item.box.y1}},${{item.box.x2}},${{item.box.y2}}] - ${{item.src}}`;
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try {{
            document.execCommand("copy");
            const originalText = btnElement.innerText;
            btnElement.innerText = "✓";
            btnElement.classList.add("copied");
            setTimeout(() => {{ btnElement.innerText = originalText; btnElement.classList.remove("copied"); }}, 1000);
        }} catch (e) {{}}
        document.body.removeChild(ta);
    }}

    function createItemDOM(item) {{
        const div = document.createElement('div');
        div.className = 'list-item';
        div.innerHTML = `
            <div class="actions">
                <div class="icon-btn play-btn" title="View clip">▶</div>
                <div class="icon-btn copy-btn" title="Copy">📋</div>
            </div>
            <div class="word-content">
                <span class="word-text">${{item.displayHtml}}</span>
                <div class="meta-info">
                    <span class="conf-badge">${{Math.floor(item.conf*100)}}%</span> 
                    ${{item.time}}
                </div>
            </div>
            <div class="bracket"></div>
        `;
        div.querySelector('.play-btn').addEventListener('click', (e) => {{ e.stopPropagation(); playSegment(item.seconds); }});
        div.querySelector('.copy-btn').addEventListener('click', (e) => {{ e.stopPropagation(); copyMetadata(item, div.querySelector('.copy-btn')); }});
        div.addEventListener('mouseenter', () => {{
            phEl.style.display = 'none'; imgEl.style.display = 'block'; imgEl.src = item.src;
            const boxW = item.box.x2 - item.box.x1;
            const boxH = item.box.y2 - item.box.y1;
            const centerX = item.box.x1 + (boxW / 2);
            const centerY = item.box.y1 + (boxH / 2);
            const originX = (centerX / dims.w) * 100;
            const originY = (centerY / dims.h) * 100;
            const scaleX = dims.w / boxW; const scaleY = dims.h / boxH;
            let scale = Math.min(scaleX, scaleY) * 0.35; 
            if (scale < 1) scale = 1; if (scale > 5) scale = 5; 
            imgEl.style.transformOrigin = `${{originX}}% ${{originY}}%`;
            imgEl.style.transform = `scale(${{scale}})`;
        }});
        div.addEventListener('click', () => {{ modal.style.display = 'flex'; modalImg.src = item.src; }});
        return div;
    }}

    function render() {{
        listEl.innerHTML = '';
        const mode = sortEl.value;
        const prioritizeLang = langCheck.checked;
        const grouping = grCheck.checked;
        
        // --- FILTERS ---
        const hideSpaces = noSpaceCheck.checked;
        
        let minVal = parseFloat(confMinInput.value);
        let maxVal = parseFloat(confMaxInput.value);
        
        if (isNaN(minVal)) minVal = 0;
        if (isNaN(maxVal)) maxVal = 100;
        
        const minConf = minVal / 100;
        const maxConf = maxVal / 100;
        
        // Filter data
        let filtered = data.filter(item => {{
            if (hideSpaces && item.word.includes(' ')) return false;
            if (item.conf < minConf || item.conf > maxConf) return false;
            return true;
        }});
        
        let sorted = [...filtered];
        
        sorted.sort((a, b) => {{
            if (prioritizeLang) {{
                if (a.hasTargetLanguage && !b.hasTargetLanguage) return -1;
                if (!a.hasTargetLanguage && b.hasTargetLanguage) return 1;
            }}
            
            if (mode === 'time') {{
                if (Math.abs(a.seconds - b.seconds) > 0.001) return a.seconds - b.seconds;
                return b.conf - a.conf;
            }}
            
            if (mode === 'conf') {{
                if (Math.abs(a.conf - b.conf) > 0.001) return b.conf - a.conf;
                return a.seconds - b.seconds;
            }}
            
            if (mode === 'alpha') {{
                const cmp = a.word.localeCompare(b.word);
                if (cmp !== 0) return cmp;
                return a.seconds - b.seconds;
            }}
            return 0;
        }});

        if (grouping) {{
            const groups = groupData(sorted);
            groups.forEach(group => {{
                if (group.children.length > 0) {{
                    const wrapper = document.createElement('div');
                    wrapper.className = 'group-wrapper';

                    const leaderDiv = createItemDOM(group.leader);
                    leaderDiv.classList.add('group-header');

                    const expandDiv = document.createElement('div');
                    expandDiv.className = 'expand-btn';
                    expandDiv.innerHTML = `<span class="count-badge">+${{group.children.length}}</span> <span class="arrow">▼</span>`;
                    leaderDiv.querySelector('.word-content').appendChild(expandDiv);

                    const childrenContainer = document.createElement('div');
                    childrenContainer.className = 'group-children';
                    group.children.forEach(child => childrenContainer.appendChild(createItemDOM(child)));

                    expandDiv.addEventListener('click', (e) => {{
                        e.stopPropagation();
                        leaderDiv.classList.toggle('expanded');
                    }});

                    wrapper.appendChild(leaderDiv);
                    wrapper.appendChild(childrenContainer);
                    listEl.appendChild(wrapper);
                }} else {{
                    listEl.appendChild(createItemDOM(group.leader));
                }}
            }});
        }} else {{
            sorted.forEach((item, i) => {{
                const div = createItemDOM(item);
                if (mode === 'time' && !prioritizeLang) {{
                    const p = sorted[i-1]; const n = sorted[i+1];
                    const sameP = p && p.src === item.src;
                    const sameN = n && n.src === item.src;
                    if (!sameP && sameN) div.classList.add('g-start');
                    else if (sameP && sameN) div.classList.add('g-mid');
                    else if (sameP && !sameN) div.classList.add('g-end');
                }}
                listEl.appendChild(div);
            }});
        }}
    }}

    // Event Listeners
    sortEl.addEventListener('change', render);
    langCheck.addEventListener('change', render);
    grCheck.addEventListener('change', render);
    noSpaceCheck.addEventListener('change', render);
    
    // Update Filter Button
    btnUpdate.addEventListener('click', render);

    modal.addEventListener('click', () => modal.style.display = 'none');
    render();
</script>
</body>
</html>
    """
    
    try:
        with open(html_output, "w", encoding="utf-8") as f:
            f.write(html_content)
        logging.info(f"Final Viewer successfully generated at: {html_output}")
    except IOError as e:
        logging.error(f"Failed to write HTML file: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multiprocessed HTML Viewer Generator for OCR Logs")
    parser.add_argument("input_txt", help="Path to the input text log file")
    parser.add_argument("--video", required=True, help="Path to the source video file")
    args = parser.parse_args()
    
    folder_path = os.path.dirname(args.input_txt)
    output_html_path = os.path.join(folder_path, "results_viewer.html")
    
    generate_multiprocess_html(args.input_txt, args.video, output_html_path)