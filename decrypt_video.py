import argparse
import logging
import os
import sys
import time
from multiprocessing import Process, Manager
from typing import List, Tuple, Any

import cv2
import numpy as np
from paddleocr import PaddleOCR

# Silence PaddleOCR internal warnings
logging.getLogger("ppocr").setLevel(logging.ERROR)

# Configure basic logging for the script
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')


def calculate_timestamp(current_frame: int, fps: float) -> str:
    """
    Converts a given frame number into a formatted timestamp (HH:MM:SS:mmm).
    """
    total_seconds = current_frame / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds - int(total_seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}:{milliseconds:03}"


def get_bounding_box_coords(box: List[List[float]]) -> Tuple[int, int, int, int]:
    """
    Converts PaddleOCR's rotated bounding box into a straight rectangle [x1, y1, x2, y2].
    """
    xs = [pt[0] for pt in box]
    ys = [pt[1] for pt in box]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def process_video_segment(
    process_id: int, 
    video_path: str, 
    start_frame: int, 
    end_frame: int, 
    output_folder: str, 
    frame_skip: int, 
    min_confidence: float, 
    shared_results: Any
) -> None:
    """
    Worker function to process a specific segment of the video using PaddleOCR.
    """
    logging.info(f"Process {process_id} started: Frames {start_frame} -> {end_frame}")
    
    try:
        ocr = PaddleOCR(use_angle_cls=False, lang='es', use_gpu=True, show_log=False)
    except Exception as e:
        logging.error(f"Process {process_id} initialization failed (GPU Error): {e}")
        return

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    current_frame = start_frame
    frames_saved = 0
    seen_texts = set()

    while current_frame < end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        if current_frame % frame_skip == 0:
            try:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = ocr.ocr(frame_rgb, cls=False, rec=True)
            except Exception as e:
                logging.debug(f"OCR inference failed on frame {current_frame}: {e}")
                result = None

            has_new_text = False
            boxes_to_draw = []
            line_buffer = []

            if result:
                for line in result:
                    if not line:
                        continue
                    
                    for detection in line:
                        box = detection[0]
                        text_info = detection[1]
                        raw_text = text_info[0]
                        confidence = text_info[1]

                        if confidence < min_confidence:
                            continue 

                        clean_text = raw_text.strip().lower()
                        
                        if clean_text not in seen_texts:
                            has_new_text = True
                            seen_texts.add(clean_text)
                            
                            x1, y1, x2, y2 = get_bounding_box_coords(box)
                            timestamp = calculate_timestamp(current_frame, fps)
                            
                            img_filename = f"frame_{current_frame}.jpg"
                            abs_path = os.path.abspath(os.path.join(output_folder, img_filename))
                            file_link = f"file:///{abs_path.replace(os.sep, '/')}"
                            
                            log_line = f'"{raw_text}" (Conf: {confidence:.2f}) - {timestamp} - [{x1},{y1},{x2},{y2}] - {file_link}\n'
                            line_buffer.append((current_frame, log_line))

                        boxes_to_draw.append(box)

            if has_new_text:
                for box in boxes_to_draw:
                    np_box = np.array(box).astype(int)
                    cv2.polylines(frame, [np_box], isClosed=True, color=(0, 255, 0), thickness=2)
                
                filename = os.path.join(output_folder, f"frame_{current_frame}.jpg")
                cv2.imwrite(filename, frame)
                frames_saved += 1
                
                for line in line_buffer:
                    shared_results.append(line)

        current_frame += 1
        
        # Real-time progress feedback on the same line
        if (current_frame - start_frame) % 100 == 0:
            progress = ((current_frame - start_frame) / (end_frame - start_frame)) * 100
            sys.stdout.write(f"\r[Process {process_id}] Progress: {progress:.0f}%")
            sys.stdout.flush()

    cap.release()
    sys.stdout.write("\n")  # Clear line after progress finishes
    logging.info(f"Process {process_id} completed. Frames saved: {frames_saved}")


def multiprocess_video_ocr(
    video_path: str, 
    root_folder: str, 
    frame_skip: int, 
    num_processes: int, 
    min_conf_percent: int
) -> None:
    """
    Splits the video into segments and processes them in parallel to maximize performance.
    """
    logging.info(f"Starting High-Performance Mode | Confidence Filter: >{min_conf_percent}%")
    
    if not os.path.exists(video_path):
        logging.error("Video file not found.")
        return

    min_confidence = min_conf_percent / 100.0

    filename_without_ext = os.path.splitext(os.path.basename(video_path))[0]
    final_output_folder = os.path.join(root_folder, filename_without_ext)
    os.makedirs(final_output_folder, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logging.error("Failed to open video file.")
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    logging.info(f"Video Info: {video_width}x{video_height} | Total Frames: {total_frames} | Processes: {num_processes}")

    frames_per_process = total_frames // num_processes
    processes = []
    
    manager = Manager()
    shared_results = manager.list()
    start_time = time.time()

    # Launch processes
    for i in range(num_processes):
        start = i * frames_per_process
        end = (i + 1) * frames_per_process if i < num_processes - 1 else total_frames
        
        p = Process(
            target=process_video_segment, 
            args=(i+1, video_path, start, end, final_output_folder, frame_skip, min_confidence, shared_results)
        )
        p.start()
        processes.append(p)

    # Blocking wait for all child processes to finish
    for p in processes:
        p.join()

    # Merge results and generate the output text file
    if len(shared_results) > 0:
        logging.info("Merging process results...")
        
        sorted_results = list(shared_results)
        sorted_results.sort(key=lambda x: x[0])

        txt_path = os.path.join(final_output_folder, "detection_log.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"VIDEO_INFO: {filename_without_ext} | RES: {video_width}x{video_height}\n")
            f.write("DETECTED_WORD | TIMESTAMP | [X1,Y1,X2,Y2] | FRAME_LINK\n")
            f.write("-" * 80 + "\n")
            
            for item in sorted_results:
                f.write(item[1])

        total_time = time.time() - start_time
        logging.info("Processing finished successfully.")
        logging.info(f"Total time elapsed: {total_time:.2f} seconds")
        logging.info(f"Log generated at: {txt_path}")
    else:
        logging.warning("No detections found matching the criteria.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multiprocessed OCR Video Analysis Tool")
    parser.add_argument("video", help="Path to the source video file")
    parser.add_argument("--skip", type=int, default=5, help="Number of frames to skip between evaluations")
    parser.add_argument("--output", default="frames", help="Destination folder for saved frames")
    parser.add_argument("--processes", type=int, default=2, help="Number of concurrent processes (GPU parallel load)")
    parser.add_argument("--min-conf", type=int, default=70, help="Minimum text confidence threshold (%)")

    args = parser.parse_args()
    
    multiprocess_video_ocr(args.video, args.output, args.skip, args.processes, args.min_conf)