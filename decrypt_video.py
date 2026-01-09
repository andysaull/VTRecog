import cv2
import os
import time
import paddle
from paddleocr import PaddleOCR
import logging
import numpy as np
import argparse  # <--- Librería para argumentos
import sys

# Silenciar logs
logging.getLogger("ppocr").setLevel(logging.WARNING)

def calcular_tiempo(frame_actual, fps):
    total_segundos = frame_actual / fps
    horas = int(total_segundos // 3600)
    minutos = int((total_segundos % 3600) // 60)
    segundos = int(total_segundos % 60)
    milisegundos = int((total_segundos - int(total_segundos)) * 1000)
    return f"{horas:02}:{minutos:02}:{segundos:02}:{milisegundos:03}"

def obtener_cuadrante(box, width, height):
    x_center = (box[0][0] + box[2][0]) / 2
    y_center = (box[0][1] + box[2][1]) / 2
    col = min(int(x_center // (width / 3)), 2)
    row = min(int(y_center // (height / 3)), 2)
    return (row * 3) + col + 1

def procesar_video_final(input_video_path, root_folder="frames", frame_skip=5):
    print(f"\n🚀 INICIANDO PROCESAMIENTO: {os.path.basename(input_video_path)}")
    
    # Validar que el archivo existe
    if not os.path.exists(input_video_path):
        print(f"❌ Error: El archivo '{input_video_path}' no existe.")
        return

    # --- LOGICA DE CARPETAS ---
    filename_con_ext = os.path.basename(input_video_path)
    filename_sin_ext = os.path.splitext(filename_con_ext)[0]
    final_output_folder = os.path.join(root_folder, filename_sin_ext)
    
    if not os.path.exists(final_output_folder):
        os.makedirs(final_output_folder)
        print(f"📁 Carpeta creada: {final_output_folder}")
    else:
        print(f"📁 Carpeta existente: {final_output_folder}")

    # --- INICIO OCR ---
    try:
        # Configuración optimizada
        ocr = PaddleOCR(use_angle_cls=False, lang='es', use_gpu=True, show_log=False)
    except Exception as e:
        print(f"❌ Error crítico OCR: {e}")
        return

    cap = cv2.VideoCapture(input_video_path)
    if not cap.isOpened():
        print("❌ Error: No se puede leer el video (Codec o ruta inválida).")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    txt_path = os.path.join(final_output_folder, "registro_detectado.txt")
    log_file = open(txt_path, "w", encoding="utf-8")
    
    log_file.write(f"VIDEO: {filename_sin_ext}\n")
    log_file.write("PALABRA | TIEMPO | CUADRANTE | FRAME (Clickable)\n")
    log_file.write("-" * 80 + "\n")

    frame_count = 0
    saved_count = 0
    textos_vistos = set()
    start_time = time.time()

    print(f"ℹ️  Video: {width}x{height} | {total_frames} frames | Skip: {frame_skip}")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_skip == 0:
            try:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = ocr.ocr(frame_rgb, cls=False, rec=True)
            except:
                result = None

            frame_tiene_novedad = False
            cajas_para_pintar = []

            if result:
                for line in result:
                    if line:
                        for detection in line:
                            box = detection[0]
                            texto_raw = detection[1][0]
                            texto_limpio = texto_raw.strip().lower()
                            
                            if len(texto_limpio) > 1:
                                if texto_limpio not in textos_vistos:
                                    frame_tiene_novedad = True
                                    textos_vistos.add(texto_limpio)
                                    
                                    cuadrante = obtener_cuadrante(box, width, height)
                                    timestamp = calcular_tiempo(frame_count, fps)
                                    nombre_imagen = f"frame_{frame_count}.jpg"
                                    
                                    # Ruta absoluta para link
                                    ruta_absoluta = os.path.abspath(os.path.join(final_output_folder, nombre_imagen))
                                    link_clickable = f"file:///{ruta_absoluta.replace(os.sep, '/')}"

                                    linea = f'"{texto_raw}" - {timestamp} - {cuadrante} - {link_clickable}\n'
                                    log_file.write(linea)
                                    log_file.flush()

                                cajas_para_pintar.append(box)

            if frame_tiene_novedad:
                for box in cajas_para_pintar:
                    box = np.array(box).astype(int)
                    cv2.polylines(frame, [box], isClosed=True, color=(0, 255, 0), thickness=2)
                
                filename = os.path.join(final_output_folder, f"frame_{frame_count}.jpg")
                cv2.imwrite(filename, frame)
                saved_count += 1

            # Barra de progreso limpia
            progreso = (frame_count / total_frames) * 100
            print(f"⏳ {progreso:.1f}% | Frames Guardados: {saved_count}", end='\r')

        frame_count += 1

    cap.release()
    log_file.close()
    
    total_time = time.time() - start_time
    print(f"\n\n✅ PROCESO TERMINADO")
    print(f"📂 Resultados en: {final_output_folder}")
    print(f"⏱️  Tiempo: {total_time:.2f}s")

if __name__ == "__main__":
    # --- GESTIÓN DE ARGUMENTOS DE CONSOLA ---
    parser = argparse.ArgumentParser(description="Detector de texto en video usando GPU")
    
    # Argumento obligatorio: el video
    parser.add_argument("video", help="Ruta al archivo de video de entrada")
    
    # Argumentos opcionales (tienen valores por defecto)
    parser.add_argument("--skip", type=int, default=5, help="Saltar frames (Default: 5)")
    parser.add_argument("--output", default="frames", help="Carpeta raíz de salida (Default: 'frames')")

    args = parser.parse_args()

    # Ejecutar con los argumentos recibidos
    procesar_video_final(args.video, args.output, args.skip)