import onnxruntime as ort
import numpy as np
import gc
import cv2
import time
import win32api
import win32con
import pandas as pd
from utils.general import (cv2, non_max_suppression, xyxy2xywh)
import torch

# Could be do with
# from config import *
# But we are writing it out for clarity for new devs
from config import aaMovementAmp, useMask, maskHeight, maskWidth, aaQuitKey, confidence, headshot_mode, cpsDisplay, visuals, onnxChoice, centerOfScreen
import gameSelection

def main():
    # External Function for running the game selection menu (gameSelection.py)
    print("Initializing game capture...")
    camera, cWidth, cHeight = gameSelection.gameSelection()
    
    if camera is None or cWidth is None or cHeight is None:
        print("ERROR: Failed to initialize game capture. Please check the error messages above.")
        return

    print("Game capture initialized successfully!")

    # Used for forcing garbage collection
    count = 0
    sTime = time.time()
    gc_counter = 0

    # Choosing the correct ONNX Provider based on config.py
    onnxProvider = ""
    if onnxChoice == 1:
        onnxProvider = "CPUExecutionProvider"
    elif onnxChoice == 2:
        onnxProvider = "DmlExecutionProvider"
    elif onnxChoice == 3:
        import cupy as cp
        onnxProvider = "CUDAExecutionProvider"

    # Optimize ONNX session
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.enable_mem_pattern = True
    so.enable_cpu_mem_arena = True
    if onnxChoice == 3:  # NVIDIA GPU optimizations
        so.intra_op_num_threads = 0  # Let CUDA handle threading
    else:  # CPU/AMD optimizations
        so.intra_op_num_threads = 4  # Adjust based on your CPU cores
    
    ort_sess = ort.InferenceSession('yolov5s320Half.onnx', sess_options=so, providers=[onnxProvider])

    # Pre-allocate arrays for better performance
    center_screen = np.array([cWidth, cHeight])
    last_mid_coord = None

    # Main loop Quit if Q is pressed
    while win32api.GetAsyncKeyState(ord(aaQuitKey)) == 0:
        # Getting Frame
        npImg = camera.get_latest_frame()
        if npImg is None:
            continue

        npImg = np.asarray(npImg)

        if useMask:
            npImg[-maskHeight:, :maskWidth, :] = 0

        # If Nvidia, do this
        if onnxChoice == 3:
            # Normalizing Data
            im = torch.from_numpy(npImg).to('cuda')
            if im.shape[2] == 4:
                im = im[:, :, :3]  # Remove alpha channel
            im = torch.movedim(im, 2, 0)
            im = im.half()
            im /= 255
            if len(im.shape) == 3:
                im = im[None]
        # If AMD or CPU, do this
        else:
            im = npImg[None]
            if im.shape[3] == 4:
                im = im[:, :, :, :3]  # Remove alpha channel
            im = im / 255
            im = im.astype(np.half)
            im = np.moveaxis(im, 3, 1)

        # Run inference
        if onnxChoice == 3:
            outputs = ort_sess.run(None, {'images': cp.asnumpy(im)})
        else:
            outputs = ort_sess.run(None, {'images': im})

        im = torch.from_numpy(outputs[0]).to('cpu')
        pred = non_max_suppression(im, confidence, confidence, 0, False, max_det=5)  # Reduced max_det for performance

        # Process detections
        if len(pred) > 0 and len(pred[0]) > 0:
            det = pred[0]
            gn = torch.tensor(im.shape)[[0, 0, 0, 0]]
            
            # Convert detections to normalized coordinates
            targets = [(xyxy2xywh(torch.tensor(xyxy).view(1, 4)) / gn).view(-1).tolist() + [float(conf)] 
                      for *xyxy, conf, cls in det]

            if targets:
                targets = pd.DataFrame(
                    targets, columns=['current_mid_x', 'current_mid_y', 'width', "height", "confidence"])

                if centerOfScreen:
                    # Vectorized distance calculation
                    targets["dist_from_center"] = np.sqrt(
                        (targets.current_mid_x - center_screen[0])**2 + 
                        (targets.current_mid_y - center_screen[1])**2)
                    targets = targets.nsmallest(1, "dist_from_center")

                # Get target coordinates
                target = targets.iloc[0]
                xMid, yMid = target.current_mid_x, target.current_mid_y
                
                # Calculate aim point
                headshot_offset = target.height * (0.38 if headshot_mode else 0.2)
                mouseMove = [xMid - cWidth, (yMid - headshot_offset) - cHeight]

                # Move mouse if CAPS LOCK is on
                if win32api.GetKeyState(0x14):
                    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 
                        int(mouseMove[0] * aaMovementAmp), 
                        int(mouseMove[1] * aaMovementAmp), 0, 0)
                
                last_mid_coord = [xMid, yMid]
        else:
            last_mid_coord = None

        # CPS Counter
        count += 1
        if (time.time() - sTime) > 1:
            if cpsDisplay:
                print("CPS: {}".format(count))
            count = 0
            sTime = time.time()
            
            # Periodic garbage collection
            gc_counter += 1
            if gc_counter >= 30:  # Run GC every 30 seconds
                gc.collect()
                gc_counter = 0

    camera.stop()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exception(e)
        print(str(e))
        