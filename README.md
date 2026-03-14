# Video Text Recognition

Python scripts to detect words in a video and easily navigate through them on a generated HTML page.

## Features

- Exports the frame containing detected text with a highlight around the text.
- Lists all found words along with their details.
- Generates an HTML page where you can filter words, view the frames associated with each word, and watch the video fragment where the frame is located.

## Pre-requirements

- NVidia GPU with latest drivers

## How to install all the tools (Instructions for Windows (sry linux but it should work there too))

1. Install Python 3.10.x
2. Install CUDA Toolkit 11.8 [From here](https://developer.nvidia.com/cuda-11-8-0-download-archive)
3. Install CUDNN 8.9.7 [From here](https://developer.nvidia.com/rdp/cudnn-archive)
   - Unzip the file
   - Copy the directories (bin, include & lib) to your CUDA installation path (e.g: C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8)
4. Copy the `zlibwapi.dll` to C:\Windows\System32 and C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin
5. Open and activate python virtual environment:

   `python -m venv .venv`

   `.\.venv\Scripts\activate`
   
6. Install Python libraries:

   `python -m pip install paddlepaddle-gpu==2.6.1.post117 -f https://www.paddlepaddle.org.cn/whl/windows/mkl/avx/stable.html`
   
   `pip install "paddleocr>=2.7.0.0,<2.8.0.0" protobuf==3.20.2`
   
   `pip install "opencv-python-headless<4.11" "opencv-python<4.11" "opencv-contrib-python<4.11"`
   
   `pip install "numpy<2.0"`

## How to use

### Detection of words in a video:
`python .\decrypt_video.py <path/to/your/video> --output <path/to/save/frames> --skip N --processes P --min-conf C`

where
- N: is the number of frames that will be skipped during text detection. (e.g: if you want to detect text every second and your video is 30fps: N=30)
- P: number of processes to divide the video frames and parallelize the work on the GPU (e.g: 1000 frames and using P=4, will put 4 processes with 250 frames each)
  *Check your GPU use and run more processes if it's not close to 100%*
- C: percentage of minimum confidence to store a frame or not (low number will detect every thing that looks like a text. High number detects only perfect texts.)

When the script is finished, it will generate all the frames where text is detected and a .txt with all the information.

### Generate an HTML with all the words
`python .\visor_gen.py <path/to/frames/>detection_log.txt --video <path/to/video>`

This will generate a webpage in the <path/to/frames> folder.

## Mentions

Spanish dictionary from: https://github.com/JorgeDuenasLerin/diccionario-espanol-txt
