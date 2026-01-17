import cv2
import os
import time
import paddle
from paddleocr import PaddleOCR
import logging
import numpy as np
import argparse
import sys
from multiprocessing import Process, Manager
from difflib import SequenceMatcher

# Silenciar logs
logging.getLogger("ppocr").setLevel(logging.WARNING)

def calcular_tiempo(frame_actual, fps):
    total_segundos = frame_actual / fps
    horas = int(total_segundos // 3600)
    minutos = int((total_segundos % 3600) // 60)
    segundos = int(total_segundos % 60)
    milisegundos = int((total_segundos - int(total_segundos)) * 1000)
    return f"{horas:02}:{minutos:02}:{segundos:02}:{milisegundos:03}"

def obtener_caja_coords(box):
    """
    Convierte la caja rotada de Paddle en un rectángulo recto [x1, y1, x2, y2]
    """
    xs = [pt[0] for pt in box]
    ys = [pt[1] for pt in box]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))

def son_similares(a, b, umbral=0.8):
    return SequenceMatcher(None, a, b).ratio() > umbral

def boxes_cercanas(box1, box2, threshold=50):
    c1_x = (box1[0][0] + box1[2][0]) / 2
    c1_y = (box1[0][1] + box1[2][1]) / 2
    c2_x = (box2[0][0] + box2[2][0]) / 2
    c2_y = (box2[0][1] + box2[2][1]) / 2
    distancia = ((c1_x - c2_x)**2 + (c1_y - c2_y)**2)**0.5
    return distancia < threshold

def esta_en_cache_difuso(texto_nuevo, cache_set):
    if texto_nuevo in cache_set:
        return True
    if len(texto_nuevo) > 3:
        for guardada in cache_set:
            if son_similares(texto_nuevo, guardada, 0.85):
                return True
    return False

# --- WORKER ---
def worker_segmento(id_proceso, video_path, start_frame, end_frame, output_folder, frame_skip, min_conf_float, patience, lista_resultados_compartida):
    print(f"🔹 [Proceso {id_proceso}] Iniciado.")
    
    try:
        ocr = PaddleOCR(use_angle_cls=False, lang='es', use_gpu=True, show_log=False)
    except Exception as e:
        print(f"❌ [Proceso {id_proceso}] Error GPU: {e}")
        return

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    current_frame = start_frame
    local_saved = 0
    textos_locales = set()
    candidatos_previos = []

    while current_frame < end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        if current_frame % frame_skip == 0:
            try:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = ocr.ocr(frame_rgb, cls=False, rec=True)
            except:
                result = None

            candidatos_actuales = []
            frame_para_guardar = False
            cajas_finales = []
            lineas_buffer = []

            if result:
                for line in result:
                    if line:
                        for detection in line:
                            box = detection[0]
                            texto_raw = detection[1][0]
                            confianza = detection[1][1]

                            if confianza < min_conf_float:
                                continue 
                            
                            texto_limpio = texto_raw.strip().lower()
                            if len(texto_limpio) < 2 or not any(c.isalpha() for c in texto_limpio):
                                continue

                            candidato = {
                                'texto': texto_limpio,
                                'texto_raw': texto_raw,
                                'box': box,
                                'confianza': confianza,
                                'match_found': False
                            }
                            candidatos_actuales.append(candidato)

            # Lógica de Persistencia
            next_generation_candidates = []
            for cand in candidatos_actuales:
                matched = False
                for prev in candidatos_previos:
                    if boxes_cercanas(cand['box'], prev['box']):
                        if son_similares(cand['texto'], prev['texto']):
                            prev['count'] += 1
                            prev['match_found'] = True
                            prev['box'] = cand['box']
                            prev['texto'] = cand['texto'] 
                            matched = True
                            
                            if prev['count'] == patience:
                                if not esta_en_cache_difuso(cand['texto'], textos_locales):
                                    textos_locales.add(cand['texto'])
                                    
                                    frame_para_guardar = True
                                    cajas_finales.append(cand['box'])
                                    
                                    cuadrante = obtener_cuadrante(cand['box'], width, height)
                                    timestamp = calcular_tiempo(current_frame, fps)
                                    nombre_img = f"frame_{current_frame}.jpg"
                                    ruta_abs = os.path.abspath(os.path.join(output_folder, nombre_img))
                                    link = f"file:///{ruta_abs.replace(os.sep, '/')}"
                                    
                                    linea = f'"{cand["texto_raw"]}" (Conf: {cand["confianza"]:.2f}) - {timestamp} - {cuadrante} - {link}\n'
                                    lineas_buffer.append((current_frame, linea))

                            next_generation_candidates.append(prev)
                            break
                
                if not matched:
                    cand['count'] = 0
                    next_generation_candidates.append(cand)
            
            candidatos_previos = next_generation_candidates

            if frame_para_guardar:
                for box in cajas_finales:
                    box = np.array(box).astype(int)
                    cv2.polylines(frame, [box], isClosed=True, color=(0, 255, 0), thickness=2)
                
                filename = os.path.join(output_folder, f"frame_{current_frame}.jpg")
                cv2.imwrite(filename, frame)
                local_saved += 1
                
                for l in lineas_buffer:
                    lista_resultados_compartida.append(l)

        current_frame += 1
        
        if (current_frame - start_frame) % 100 == 0:
            progreso = ((current_frame - start_frame) / (end_frame - start_frame)) * 100
            print(f"⚙️  [Proc {id_proceso}] {progreso:.0f}%", end='\r')

    cap.release()
    print(f"✅ [Proceso {id_proceso}] Terminado. Guardados: {local_saved}")


def procesar_multiprocess(video_path, root_folder, frame_skip, num_procesos, min_conf_percent, patience):
    print(f"\n🚀 PROCESANDO: {os.path.basename(video_path)}")
    print(f"   Config: Confianza > {min_conf_percent}% | Estabilidad: {patience}")
    
    if not os.path.exists(video_path):
        print("❌ Video no encontrado")
        return

    min_conf_float = min_conf_percent / 100.0

    filename_sin_ext = os.path.splitext(os.path.basename(video_path))[0]
    final_output_folder = os.path.join(root_folder, filename_sin_ext)
    if not os.path.exists(final_output_folder):
        os.makedirs(final_output_folder)

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # Datos para el visor HTML
    video_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    frames_por_proceso = total_frames // num_procesos
    procesos = []
    
    manager = Manager()
    lista_resultados = manager.list()
    start_time = time.time()

    # --- INICIO SEGURO DE PROCESOS ---
    try:
        for i in range(num_procesos):
            start = i * frames_por_proceso
            end = (i + 1) * frames_por_proceso if i < num_procesos - 1 else total_frames
            
            p = Process(target=worker_segmento, args=(i+1, video_path, start, end, final_output_folder, frame_skip, min_conf_float, patience, lista_resultados))
            p.start()
            procesos.append(p)

        # Esperamos a que terminen
        for p in procesos:
            p.join()

    except KeyboardInterrupt:
        print("\n\n🛑 DETENIENDO... (Limpiando GPU)")
    
    finally:
        # ESTE BLOQUE ASEGURA QUE LA GPU SE LIBERE SIEMPRE
        for p in procesos:
            if p.is_alive():
                p.terminate()
                p.join()
        print("🧹 Procesos GPU limpiados correctamente.")

    # --- FUSIÓN (Solo si terminamos bien) ---
    if len(lista_resultados) > 0:
        print("\n📦 Fusionando resultados...")
        resultados_ordenados = list(lista_resultados)
        resultados_ordenados.sort(key=lambda x: x[0])

        txt_path = os.path.join(final_output_folder, "registro_detectado.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"VIDEO: {filename_sin_ext}\n")
            f.write("PALABRA | TIEMPO | CUADRANTE | FRAME (Clickable)\n")
            f.write("-" * 80 + "\n")
            
            for item in resultados_ordenados:
                f.write(item[1])

        total_time = time.time() - start_time
        print(f"\n✅ TODO LISTO.")
        print(f"⏱️  Tiempo total: {total_time:.2f}s")
    else:
        print("\n⚠️ No se encontraron resultados o se canceló antes de tiempo.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Ruta video")
    parser.add_argument("--skip", type=int, default=5, help="Saltar frames")
    parser.add_argument("--output", default="frames", help="Output folder")
    parser.add_argument("--procesos", type=int, default=2, help="Num Procesos")
    parser.add_argument("--min-conf", type=int, default=70, help="Confianza min %")
    parser.add_argument("--patience", type=int, default=1, help="Estabilidad (0=Off, 1=Normal, 2=Alta)")

    args = parser.parse_args()
    
    # IMPORTANTE: En Windows esto debe estar protegido por el if main
    procesar_multiprocess(args.video, args.output, args.skip, args.procesos, args.min_conf, args.patience)