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

# --- WORKER ---
def worker_segmento(id_proceso, video_path, start_frame, end_frame, output_folder, frame_skip, min_conf_float, lista_resultados_compartida):
    print(f"🔹 [Proceso {id_proceso}] Iniciado: Frames {start_frame} -> {end_frame}")
    
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

            frame_tiene_novedad = False
            cajas_para_pintar = []
            lineas_buffer = []

            if result:
                for line in result:
                    if line:
                        for detection in line:
                            box = detection[0]
                            texto_info = detection[1]
                            texto_raw = texto_info[0]
                            confianza = texto_info[1]

                            if confianza < min_conf_float:
                                continue 

                            texto_limpio = texto_raw.strip().lower()
                            
                            if len(texto_limpio) > 1:
                                if texto_limpio not in textos_locales:
                                    frame_tiene_novedad = True
                                    textos_locales.add(texto_limpio)
                                    
                                    # Coordenadas exactas para el Zoom
                                    x1, y1, x2, y2 = obtener_caja_coords(box)
                                    
                                    timestamp = calcular_tiempo(current_frame, fps)
                                    nombre_img = f"frame_{current_frame}.jpg"
                                    ruta_abs = os.path.abspath(os.path.join(output_folder, nombre_img))
                                    link = f"file:///{ruta_abs.replace(os.sep, '/')}"
                                    
                                    # Formato con coordenadas [x1,y1,x2,y2]
                                    linea_txt = f'"{texto_raw}" (Conf: {confianza:.2f}) - {timestamp} - [{x1},{y1},{x2},{y2}] - {link}\n'
                                    lineas_buffer.append((current_frame, linea_txt))

                                cajas_para_pintar.append(box)

            if frame_tiene_novedad:
                for box in cajas_para_pintar:
                    box = np.array(box).astype(int)
                    cv2.polylines(frame, [box], isClosed=True, color=(0, 255, 0), thickness=2)
                
                filename = os.path.join(output_folder, f"frame_{current_frame}.jpg")
                cv2.imwrite(filename, frame)
                local_saved += 1
                
                for l in lineas_buffer:
                    lista_resultados_compartida.append(l)

        current_frame += 1
        
        # Feedback sin pausas
        if (current_frame - start_frame) % 100 == 0:
            progreso = ((current_frame - start_frame) / (end_frame - start_frame)) * 100
            print(f"⚙️  [Proc {id_proceso}] {progreso:.0f}%", end='\r')

    cap.release()
    print(f"✅ [Proceso {id_proceso}] Fin. Guardados: {local_saved}")


def procesar_multiprocess(video_path, root_folder, frame_skip, num_procesos, min_conf_percent):
    print(f"\n🚀 MODO MAX PERFORMANCE | Filtro Confianza: >{min_conf_percent}%")
    
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

    print(f"ℹ️  Video: {video_w}x{video_h} | Frames: {total_frames} | Procesos: {num_procesos}")

    frames_por_proceso = total_frames // num_procesos
    procesos = []
    
    manager = Manager()
    lista_resultados = manager.list()
    start_time = time.time()

    # --- LANZAMIENTO DE PROCESOS ---
    for i in range(num_procesos):
        start = i * frames_por_proceso
        end = (i + 1) * frames_por_proceso if i < num_procesos - 1 else total_frames
        
        p = Process(target=worker_segmento, args=(i+1, video_path, start, end, final_output_folder, frame_skip, min_conf_float, lista_resultados))
        p.start()
        procesos.append(p)

    # --- ESPERA BLOQUEANTE (SIN SLEEP) ---
    # Esto es lo más rápido posible. El padre duerme hasta que los hijos acaban.
    for p in procesos:
        p.join()

    # --- FUSIÓN Y GENERACIÓN DE TXT ---
    if len(lista_resultados) > 0:
        print("\n📦 Fusionando resultados...")
        resultados_ordenados = list(lista_resultados)
        resultados_ordenados.sort(key=lambda x: x[0])

        txt_path = os.path.join(final_output_folder, "registro_detectado.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            # Cabecera con resolución para el HTML
            f.write(f"VIDEO_INFO: {filename_sin_ext} | RES: {video_w}x{video_h}\n")
            f.write("PALABRA | TIEMPO | [X1,Y1,X2,Y2] | FRAME\n")
            f.write("-" * 80 + "\n")
            
            for item in resultados_ordenados:
                f.write(item[1])

        total_time = time.time() - start_time
        print(f"\n✅ TODO LISTO.")
        print(f"⏱️  Tiempo total: {total_time:.2f}s")
        print(f"📄 Log generado: {txt_path}")
    else:
        print("\n⚠️ No se encontraron detecciones.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Ruta video")
    parser.add_argument("--skip", type=int, default=5, help="Saltar frames")
    parser.add_argument("--output", default="frames", help="Output folder")
    parser.add_argument("--procesos", type=int, default=2, help="Num Procesos (Carga GPU)")
    parser.add_argument("--min-conf", type=int, default=70, help="Confianza mínima %")

    args = parser.parse_args()
    
    procesar_multiprocess(args.video, args.output, args.skip, args.procesos, args.min_conf)